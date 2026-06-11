<?php

namespace App\Jobs;

use App\Models\Application;
use App\Models\Faq;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Facades\Log;

class ProcessFaqPipeline implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    public int $timeout = 900;
    public int $tries   = 3;

    public function __construct(private readonly string $action = 'sync') {}

    public function handle(): void
    {
        $this->syncAndIndexAllApplications();
    }

    // ----------------------------------------------------------------
    // Boucle principale
    // ----------------------------------------------------------------

    private function syncAndIndexAllApplications(): void
    {
        $extractDir = rtrim((string) config('services.extract.extract_dir', base_path('../../extract/app')), '/');
        $faqDir     = rtrim((string) config('services.extract.faq_dir', $extractDir . '/faq'), '/');
        $backendUrl = rtrim((string) config('services.backend.url', 'http://127.0.0.1:8000'), '/');

        if (!is_dir($faqDir)) {
            mkdir($faqDir, 0775, true);
        }

        // On cible toutes les applications qui ont au moins un item FAQ en base,
        // sans distinction manuel/faq — la colonne is_faq n'existe plus.
        $applications = Application::whereHas('faqItems')->get();

        if ($applications->isEmpty()) {
            Log::info('[FAQ Pipeline] Aucune application avec des items FAQ à synchroniser.');
            return;
        }

        foreach ($applications as $app) {
            $this->processOneApplication($app, $faqDir, $backendUrl);
        }
    }

    // ----------------------------------------------------------------
    // Traitement d'une application
    // ----------------------------------------------------------------

    private function processOneApplication(
        Application $app,
        string      $faqDir,
        string      $backendUrl
    ): void {
        $slug = $this->appNameToFaqSlug($app->name);

        try {
            // Étape 1 : récupérer les items depuis la base
            $items = Faq::where('application_id', $app->id)
                ->get()
                ->map(fn($i) => $i->toFaqArray())
                ->values()
                ->all();

            if (empty($items)) {
                Log::info('[FAQ Pipeline] Aucun item pour cette application', ['app' => $app->name]);
                return;
            }

            // Étape 2 : régénérer le fichier JSON sur disque
            $filePath = $faqDir . '/' . $slug . '.json';
            $this->writeFaqFile($filePath, $items);

            Log::debug('[FAQ Pipeline] Fichier régénéré', [
                'app'        => $app->name,
                'slug'       => $slug,
                'file'       => $filePath,
                'item_count' => count($items),
            ]);

            // Étape 3 : indexation via le backend Python
            // On envoie le slug — le backend résout la collection réelle :
            //   - {slug}_2levels_cleaned si le manuel existe  → merge
            //   - {slug} sinon                                → crée/réutilise
            $realCollection = $this->indexViaBackend($backendUrl, $slug, $items, $app);

            // Étape 4 : sauvegarder la collection réelle en base
            if ($realCollection && $realCollection !== $app->qdrant_collection) {
                $app->update(['qdrant_collection' => $realCollection]);
                Log::info('[FAQ Pipeline] Collection mise à jour en base', [
                    'app'        => $app->name,
                    'collection' => $realCollection,
                ]);
            }

        } catch (\Throwable $e) {
            Log::error('[FAQ Pipeline] Erreur traitement application', [
                'app_id' => $app->id,
                'app'    => $app->name,
                'error'  => $e->getMessage(),
            ]);
        }
    }

    // ----------------------------------------------------------------
    // Indexation via le backend Python
    // ----------------------------------------------------------------

    private function indexViaBackend(
        string      $backendUrl,
        string      $slug,
        array       $items,
        Application $app
    ): ?string {
        $endpoint = $backendUrl . '/api/faq/index';
        $payload  = json_encode([
            'collection' => $slug,
            'items'      => $items,
        ]);

        try {
            $client   = new \GuzzleHttp\Client(['timeout' => 300]);
            $response = $client->post($endpoint, [
                'headers' => ['Content-Type' => 'application/json'],
                'body'    => $payload,
            ]);
            $data = json_decode((string) $response->getBody(), true);

            if (!empty($data['success']) || $response->getStatusCode() < 300) {
                $realCollection = $data['collection'] ?? $slug;
                Log::info('[FAQ Pipeline] Indexation réussie', [
                    'app'                => $app->name,
                    'slug'               => $slug,
                    'collection'         => $realCollection,
                    'merged_into_manual' => $data['merged_into_manual'] ?? false,
                    'items'              => count($items),
                ]);
                return $realCollection;
            }

            Log::warning('[FAQ Pipeline] Réponse non-succès du backend', [
                'app'    => $app->name,
                'status' => $response->getStatusCode(),
                'body'   => $data,
            ]);

        } catch (\Throwable $e) {
            Log::warning('[FAQ Pipeline] Backend inaccessible, fallback admin endpoint', [
                'app'   => $app->name,
                'error' => $e->getMessage(),
            ]);
        }

        return $this->indexViaAdminFallback($backendUrl, $slug, $items, $app);
    }

    private function indexViaAdminFallback(
        string      $backendUrl,
        string      $slug,
        array       $items,
        Application $app
    ): ?string {
        $endpoint = $backendUrl . '/api/admin/faq/' . urlencode($slug);
        $payload  = json_encode(['items' => $items]);

        try {
            $client   = new \GuzzleHttp\Client(['timeout' => 300]);
            $response = $client->put($endpoint, [
                'headers' => ['Content-Type' => 'application/json'],
                'body'    => $payload,
            ]);
            $data = json_decode((string) $response->getBody(), true);

            if (!empty($data['success']) || $response->getStatusCode() < 300) {
                $realCollection = $data['collection'] ?? $slug;
                Log::info('[FAQ Pipeline] Indexation réussie (fallback admin)', [
                    'app'        => $app->name,
                    'collection' => $realCollection,
                ]);
                return $realCollection;
            }

            Log::warning('[FAQ Pipeline] Fallback admin non-succès', [
                'app'    => $app->name,
                'status' => $response->getStatusCode(),
                'body'   => $data,
            ]);

        } catch (\Throwable $e) {
            Log::error('[FAQ Pipeline] Backend complètement inaccessible', [
                'app'   => $app->name,
                'error' => $e->getMessage(),
            ]);
        }

        return null;
    }

    // ----------------------------------------------------------------
    // Écriture robuste du fichier JSON FAQ
    // ----------------------------------------------------------------

    private function writeFaqFile(string $filePath, array $items): void
    {
        $dir = dirname($filePath);
        if (!is_dir($dir)) {
            mkdir($dir, 0775, true);
        }

        if (file_exists($filePath) && !is_writable($filePath)) {
            @chmod($filePath, 0664);
        }

        $result = file_put_contents(
            $filePath,
            json_encode(['items' => $items], JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE)
        );

        if ($result === false) {
            throw new \RuntimeException("Impossible d'écrire dans {$filePath}. Vérifiez les permissions.");
        }
    }

    // ----------------------------------------------------------------
    // Slug — identique à AdminController
    // ----------------------------------------------------------------

    private function appNameToFaqSlug(string $appName): string
    {
        $value = trim(mb_strtolower($appName));
        $out   = '';
        foreach (mb_str_split($value) as $ch) {
            if (ctype_alnum($ch)) {
                $out .= $ch;
            } elseif (in_array($ch, [' ', '-', '.', '_'], true)) {
                $out .= '_';
            }
        }
        $slug = trim($out, '_');
        while (str_contains($slug, '__')) {
            $slug = str_replace('__', '_', $slug);
        }
        return $slug !== '' ? $slug : 'app';
    }
}
