<?php

namespace App\Jobs;

use App\Models\Manual;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Str;
use Symfony\Component\Process\Process;
use Illuminate\Support\Facades\Log;


class ProcessManualPipeline implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    public int $timeout = 1800;
    public int $tries   = 1;

    public function __construct(private readonly int $manualId) {}

    public function handle(): void
    {
        $manual = Manual::with('application')->find($this->manualId);

        if (!$manual) {
            Log::warning("[Pipeline] Manuel #{$this->manualId} introuvable.");
            return;
        }

        // ── Chemins ───────────────────────────────────────────────────
        $pythonBin  = (string) config('services.extract.python_bin',  'python3');
        $extractDir = rtrim((string) config('services.extract.extract_dir',  base_path('../../extract/app')), '/');
        $manualsDir = rtrim((string) config('services.extract.manuals_dir',  $extractDir . '/manuels'), '/');
        $jsonDir    = rtrim((string) config('services.extract.json_dir',     $extractDir . '/json'), '/');
        $timeout    = (int) config('services.extract.timeout', 1800);
        $apiUrl     = rtrim((string) config('services.chatbot.api_url', 'http://127.0.0.1:8000'), '/');

        // ── Résoudre les chemins réels (suivre les symlinks) ──────────
        $realExtractDir = realpath($extractDir) ?: $extractDir;
        $realManualsDir = realpath($manualsDir) ?: $manualsDir;
        $realJsonDir    = realpath($jsonDir)    ?: $jsonDir;

        // ── Fichier PDF ───────────────────────────────────────────────
        $pdfFileName = $manual->file_path;
        $pdfPath     = $this->absolutePath($pdfFileName, $realManualsDir);

        if (!is_file($pdfPath)) {
            $this->markFailed($manual, "[Extraction] PDF introuvable : {$pdfPath}");
            return;
        }

        $baseName = pathinfo($pdfFileName, PATHINFO_FILENAME);

        // ── Convention de nommage ─────────────────────────────────────
        // Étape 1 (extraction)  →  {baseName}_2levels.json
        // Étape 2 (cleaning)    →  {baseName}_2levels_cleaned.json
        // Collection Qdrant     →  {baseName}_2levels_cleaned
        $jsonRaw        = $realJsonDir . '/' . $baseName . '_2levels.json';
        $jsonClean      = $realJsonDir . '/' . $baseName . '_2levels_cleaned.json';
        $collectionName = $baseName . '_2levels_cleaned';

        Log::info("[Pipeline] Démarrage", [
            'manual_id'  => $manual->id,
            'pdf'        => $pdfPath,
            'base_name'  => $baseName,
            'json_raw'   => $jsonRaw,
            'json_clean' => $jsonClean,
            'collection' => $collectionName,
        ]);

        // ══════════════════════════════════════════════════════════════
        // ÉTAPE 1 : Extraction PDF → {baseName}_2levels.json
        //
        // Si follows_internal_template = true  → extractor_level_2.py
        // Si follows_internal_template = false → extractor_docling_level_2.py
        // ══════════════════════════════════════════════════════════════
        $useInternalTemplate = (bool) ($manual->follows_internal_template ?? true);

        // CORRECTION : cast explicite en bool pour éviter que la valeur DB
        // (entier 0/1) soit mal interprétée
        $useInternalTemplate = filter_var($useInternalTemplate, FILTER_VALIDATE_BOOLEAN);

        $extractScriptName = $useInternalTemplate
            ? 'extractor_level_2.py'
            : 'extractor_docling_level_2.py';

        $extractScript = $realExtractDir . '/' . $extractScriptName;

        Log::info("[Pipeline] Étape 1 : extraction PDF → {$jsonRaw}", [
            'extractor'                  => $extractScriptName,
            'follows_internal_template'  => $useInternalTemplate,
        ]);

        if (!is_file($extractScript)) {
            $this->markFailed($manual, "[Extraction] Script introuvable : {$extractScript}");
            return;
        }

        $process1 = new Process([$pythonBin, $extractScript, $pdfPath]);
        $process1->setTimeout($timeout);
        $process1->setWorkingDirectory($realExtractDir);

        try {
            $process1->mustRun();
        } catch (\Exception $e) {
            $this->markFailed($manual, '[Extraction] ' . mb_substr($e->getMessage(), 0, 2000), $process1);
            return;
        }

        if (!is_file($jsonRaw)) {
            $this->markFailed($manual, "[Extraction] Fichier JSON brut non créé : {$jsonRaw}");
            return;
        }

        Log::info("[Pipeline] Étape 1 OK", ['json_raw' => $jsonRaw]);

        // ══════════════════════════════════════════════════════════════
        // ÉTAPE 2 : Nettoyage {baseName}_2levels.json → {baseName}_2levels_cleaned.json
        // ══════════════════════════════════════════════════════════════
        $cleanScript = $realExtractDir . '/clean_data.py';

        if (!is_file($cleanScript)) {
            $this->markFailed($manual, "[Nettoyage] Script introuvable : {$cleanScript}");
            return;
        }

        $process2 = new Process([$pythonBin, $cleanScript, $jsonRaw, $jsonClean]);
        $process2->setTimeout($timeout);
        $process2->setWorkingDirectory($realExtractDir);

        Log::info("[Pipeline] Étape 2 : nettoyage {$jsonRaw} → {$jsonClean}");

        try {
            $process2->mustRun();
        } catch (\Exception $e) {
            $this->markFailed($manual, '[Nettoyage] ' . mb_substr($e->getMessage(), 0, 2000), $process2);
            return;
        }

        if (!is_file($jsonClean)) {
            $this->markFailed($manual, "[Nettoyage] Fichier JSON nettoyé non créé : {$jsonClean}");
            return;
        }

        Log::info("[Pipeline] Étape 2 OK", ['json_clean' => $jsonClean]);

        // ══════════════════════════════════════════════════════════════
        // ÉTAPE 3 : Indexation dans Qdrant via l'API Python
        // POST http://127.0.0.1:8000/api/index
        // Body : { "json_path": "…_2levels_cleaned.json", "collection": "…_2levels_cleaned" }
        // ══════════════════════════════════════════════════════════════
        Log::info("[Pipeline] Étape 3 : indexation Qdrant", [
            'collection' => $collectionName,
            'api'        => $apiUrl,
        ]);

        $indexed = $this->indexInQdrant($apiUrl, $jsonClean, $collectionName, $manual);

        if (!$indexed) {
            return; // markFailed déjà appelé dans indexInQdrant
        }

        // ── Tout s'est bien passé → marquer comme indexé ─────────────
        $manual->update([
            'status'            => 'indexed',
            'cleaned_json_path' => $jsonClean,
            'processing_error'  => null,
        ]);

        if ($manual->application) {
            $manual->application->update([
                'qdrant_collection' => $collectionName,
            ]);
        }

        Log::info("[Pipeline] Pipeline complet ✓", [
            'manual_id'  => $manual->id,
            'collection' => $collectionName,
        ]);
    }

    // ──────────────────────────────────────────────────────────────────
    // Indexation via l'API Python (avec retry)
    // ──────────────────────────────────────────────────────────────────

    private function indexInQdrant(
        string $apiUrl,
        string $jsonCleanPath,
        string $collectionName,
        Manual $manual
    ): bool {
        $endpoint = $apiUrl . '/api/index';
        $payload  = json_encode([
            'json_path'  => $jsonCleanPath,
            'collection' => $collectionName,
        ]);

        $maxAttempts = 3;
        $lastError   = '';

        for ($attempt = 1; $attempt <= $maxAttempts; $attempt++) {
            try {
                $context = stream_context_create([
                    'http' => [
                        'method'  => 'POST',
                        'header'  => "Content-Type: application/json\r\nContent-Length: " . strlen($payload) . "\r\n",
                        'content' => $payload,
                        'timeout' => 1800,
                    ],
                ]);

                $response = @file_get_contents($endpoint, false, $context);

                if ($response === false) {
                    $lastError = "Impossible de contacter l'API Python ({$endpoint})";
                    Log::warning("[Pipeline] Tentative {$attempt}/{$maxAttempts} : {$lastError}");
                    sleep(5);
                    continue;
                }

                $data = json_decode($response, true);

                if (isset($data['success']) && $data['success']) {
                    Log::info("[Pipeline] Étape 3 OK", ['collection' => $collectionName]);
                    return true;
                }

                $lastError = $data['error'] ?? "Réponse inattendue de l'API Python";
                Log::warning("[Pipeline] Tentative {$attempt}/{$maxAttempts} : {$lastError}");
                sleep(5);

            } catch (\Exception $e) {
                $lastError = $e->getMessage();
                Log::warning("[Pipeline] Tentative {$attempt}/{$maxAttempts} exception : {$lastError}");
                sleep(5);
            }
        }

        $this->markFailed($manual, "[Indexation Qdrant] {$lastError}");
        return false;
    }

    // ──────────────────────────────────────────────────────────────────
    // HELPERS
    // ──────────────────────────────────────────────────────────────────

    private function markFailed(Manual $manual, string $message, ?Process $process = null): void
    {
        $manual->update([
            'status'           => 'failed',
            'processing_error' => $message,
        ]);

        $context = ['manual_id' => $manual->id, 'error' => $message];

        if ($process) {
            $context['stdout'] = mb_substr($process->getOutput(),      0, 1000);
            $context['stderr'] = mb_substr($process->getErrorOutput(), 0, 1000);
        }

        Log::error("[Pipeline] Échec", $context);
    }

    private function absolutePath(string $filePath, string $baseDir): string
    {
        return Str::startsWith($filePath, '/')
            ? $filePath
            : rtrim($baseDir, '/') . '/' . ltrim($filePath, '/');
    }
}
