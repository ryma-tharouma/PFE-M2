<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Jobs\ProcessFaqPipeline;
use App\Jobs\ProcessManualPipeline;
use App\Models\Application;
use App\Models\Conversation;
use App\Models\Manual;
use App\Models\Message;
use App\Models\Ticket;
use App\Models\User;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Str;

class AdminController extends Controller
{
    // ──────────────────────────────────────────────────────────────────
    // DASHBOARD
    // ──────────────────────────────────────────────────────────────────
    public function index()
    {
        $totalRequests   = Message::where('role', 'user')->count();
        $requestsToday   = Message::where('role', 'user')->whereDate('created_at', today())->count();
        $totalTickets    = Ticket::count();
        $totalManuals    = Manual::count();
        $totalUsers      = User::count();
        $activeUsersWeek = User::whereNotNull('last_login_at')
            ->where('last_login_at', '>=', now()->subDays(7))->count();
        $activeToday     = User::whereDate('last_login_at', today())->count();
        $adminCount      = User::where('is_admin', true)->count();

        $dayAvg              = $totalRequests > 0 ? max(1, $totalRequests / 30) : 1;
        $requestsTodayPct    = min(100, (int) round(($requestsToday / $dayAvg) * 100));
        $activeUsersPct      = $totalUsers > 0 ? min(100, (int) round(($activeUsersWeek / $totalUsers) * 100)) : 0;
        $manualsIndexedCount = Manual::where('status', 'indexed')->count();
        $manualsIndexedPct   = $totalManuals > 0 ? (int) round(($manualsIndexedCount / $totalManuals) * 100) : 0;
        $activeUsersDayPct   = $totalUsers > 0 ? min(100, (int) round(($activeToday / $totalUsers) * 100)) : 0;

        $requestsByApp = Message::query()
            ->join('conversations', 'messages.conversation_id', '=', 'conversations.id')
            ->join('applications', 'conversations.application_id', '=', 'applications.id')
            ->where('messages.role', 'user')
            ->selectRaw('applications.name as app_name, count(*) as total')
            ->groupBy('applications.name')
            ->orderByDesc('total')
            ->get()
            ->map(function ($row) use ($totalRequests) {
                $row->percentage = $totalRequests > 0
                    ? (int) round(($row->total / $totalRequests) * 100)
                    : 0;
                return $row;
            });

        $requestsByDept = Message::query()
            ->join('conversations', 'messages.conversation_id', '=', 'conversations.id')
            ->join('users', 'conversations.user_id', '=', 'users.id')
            ->where('messages.role', 'user')
            ->whereNotNull('users.department')
            ->selectRaw('users.department, count(*) as total')
            ->groupBy('users.department')
            ->orderByDesc('total')
            ->get()
            ->map(function ($row) use ($totalRequests) {
                $row->percentage = $totalRequests > 0
                    ? (int) round(($row->total / $totalRequests) * 100)
                    : 0;
                return $row;
            });

        $requestsByHourRaw = Message::where('role', 'user')
            ->whereDate('created_at', today())
            ->selectRaw('EXTRACT(HOUR FROM created_at)::int as hour, count(*) as total')
            ->groupBy('hour')
            ->orderBy('hour')
            ->pluck('total', 'hour');

        $requestsByHour = [];
        for ($h = 0; $h < 24; $h++) {
            $requestsByHour[$h] = $requestsByHourRaw[$h] ?? 0;
        }
        $hourMax = max(1, max($requestsByHour));

        $usersByDept = User::whereNotNull('department')
            ->selectRaw('department, count(*) as total')
            ->groupBy('department')
            ->orderByDesc('total')
            ->get();
        $deptMax     = $usersByDept->max('total') ?: 1;
        $usersByDept = $usersByDept->map(function ($row) use ($deptMax) {
            $row->percentage = (int) round(($row->total / $deptMax) * 100);
            return $row;
        });

        $users = User::select('users.*')
            ->addSelect([
                'requests_count' => Message::selectRaw('count(*)')
                    ->join('conversations', 'messages.conversation_id', '=', 'conversations.id')
                    ->whereColumn('conversations.user_id', 'users.id')
                    ->where('messages.role', 'user'),
            ])
            ->orderByDesc('last_login_at')
            ->get();

        $ticketsByPriority = Ticket::selectRaw('priority, count(*) as total')
            ->groupBy('priority')
            ->orderByDesc('total')
            ->get();

        $ticketsByStatus = Ticket::selectRaw(
            "COALESCE(glpi_status, 'Envoyé') as status, count(*) as total"
        )
            ->groupBy('glpi_status')
            ->orderByDesc('total')
            ->get();

        $stats = [
            'requests_today'      => $requestsToday,
            'requests_total'      => $totalRequests,
            'requests_today_pct'  => $requestsTodayPct,
            'tickets_total'       => $totalTickets,
            'manuals_count'       => $totalManuals,
            'manuals_indexed'     => $manualsIndexedCount,
            'manuals_indexed_pct' => $manualsIndexedPct,
            'manuals_processing'  => Manual::where('status', 'processing')->count(),
            'manuals_failed'      => Manual::where('status', 'failed')->count(),
            'total_users'         => $totalUsers,
            'active_users'        => $activeUsersWeek,
            'active_users_pct'    => $activeUsersPct,
            'active_today'        => $activeToday,
            'active_today_pct'    => $activeUsersDayPct,
            'admin_count'         => $adminCount,
            'requests_by_app'     => $requestsByApp,
            'requests_by_dept'    => $requestsByDept,
            'requests_by_hour'    => $requestsByHour,
            'hour_max'            => $hourMax,
            'tickets_by_priority' => $ticketsByPriority,
            'tickets_by_status'   => $ticketsByStatus,
            'users_by_dept'       => $usersByDept,
        ];

        $manuals      = Manual::with('application')->orderByDesc('created_at')->paginate(20);
        $tickets      = Ticket::with('user')->orderByDesc('created_at')->paginate(20);

        // Applications manuels (is_faq = false)
        $applications = Application::where('is_faq', false)
            ->orderBy('name')
            ->get();

        // Applications avec collection Qdrant pour les chats
        $chatApplications = Application::whereNotNull('qdrant_collection')
            ->orderBy('name')
            ->get();

        $faqList = $this->listFaqFiles();

        return view('admin.dashboard', compact(
            'stats', 'manuals', 'tickets', 'applications', 'chatApplications', 'users', 'faqList'
        ));
    }

    // ──────────────────────────────────────────────────────────────────
    // HELPERS FAQ DIR
    // ──────────────────────────────────────────────────────────────────

    private function getFaqDir(): string
    {
        $extractDir = rtrim((string) config('services.extract.extract_dir', base_path('../../extract/app')), '/');
        return rtrim((string) config('services.extract.faq_dir', $extractDir . '/faq'), '/');
    }

    /**
     * Convertit un nom d'application en slug de fichier FAQ.
     * Le slug est le nom exact, en minuscules, espaces → underscores.
     * "Parc Auto v2" → "parc_auto_v2"
     * Les noms sont uniques en BDD donc les slugs le sont aussi.
     */
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
            // les autres caractères sont ignorés
        }
        $slug = trim($out, '_');
        // collapse double underscores
        while (str_contains($slug, '__')) {
            $slug = str_replace('__', '_', $slug);
        }
        return $slug !== '' ? $slug : 'app';
    }

    /**
     * Retourne le chemin absolu du fichier FAQ JSON pour une application.
     * Convention: {faq_dir}/{slug}.json
     */
    private function getFaqFilePath(string $appIdentifier): string
    {
        if (is_numeric($appIdentifier)) {
            $app  = Application::find((int) $appIdentifier);
            $slug = $app ? $this->appNameToFaqSlug($app->name) : $appIdentifier;
        } else {
            $slug = $this->appNameToFaqSlug($appIdentifier);
        }
        return $this->getFaqDir() . '/' . $slug . '.json';
    }

    /**
     * Liste tous les fichiers FAQ existants sur le disque.
     */
    private function listFaqFiles(): array
    {
        $faqDir = $this->getFaqDir();
        if (!is_dir($faqDir)) return [];

        $files  = glob($faqDir . '/*.json') ?: [];
        $result = [];

        foreach ($files as $file) {
            try {
                $raw   = file_get_contents($file);
                $data  = json_decode($raw, true) ?: [];
                $items = $data['items'] ?? $data;
                $items = is_array($items) ? $items : [];

                $slug    = pathinfo($file, PATHINFO_FILENAME);
                $appName = str_replace('_', ' ', $slug);

                // Retrouver l'application FAQ en BDD (is_faq = true, nom exact via slug)
                $application = Application::where('is_faq', true)
                    ->whereRaw('LOWER(REPLACE(REPLACE(name, \' \', \'_\'), \'-\', \'_\')) = ?', [strtolower($slug)])
                    ->first();

                // Récupérer la version du dernier manuel indexé pour cette application (si elle existe aussi en tant que manuel)
                $manualVersion = null;
                if ($application) {
                    // Chercher une application manuel du même nom de base
                    $manualApp = Application::where('is_faq', false)
                        ->whereRaw('LOWER(name) = ?', [strtolower($application->name)])
                        ->first();
                    if ($manualApp) {
                        $latestManual = Manual::where('application_id', $manualApp->id)
                            ->where('status', 'indexed')
                            ->latest('created_at')
                            ->first();
                        $manualVersion = $latestManual?->version;
                    }
                }

                $result[] = [
                    'slug'       => $slug,
                    'file'       => $file,
                    'app_name'   => $application ? $application->name : ucwords($appName),
                    'app_id'     => $application?->id,
                    'version'    => $manualVersion ?? null,
                    'item_count' => count($items),
                    'updated_at' => date('d/m/Y', filemtime($file)),
                ];
            } catch (\Throwable $e) {
                Log::warning('[AdminController] Erreur lecture FAQ', ['file' => $file, 'error' => $e->getMessage()]);
            }
        }

        usort($result, fn($a, $b) => filemtime($b['file']) <=> filemtime($a['file']));
        return $result;
    }

    // ──────────────────────────────────────────────────────────────────
    // CRUD MANUELS
    // ──────────────────────────────────────────────────────────────────

    /**
     * Vérifie si une application/version existe déjà.
     * Règle : le nom est strictement unique (is_faq=false).
     * La version est portée par le nom saisi par l'admin (ex: "SAP v2").
     */
    public function checkAppVersion(Request $request): JsonResponse
    {
        $appName = trim($request->input('app_name', ''));
        $version = $this->normalizeManualVersion($request->input('version', '1.0'));

        if (!$appName) {
            return response()->json(['exists' => false]);
        }

        // Recherche exacte (insensible à la casse)
        $application = Application::where('is_faq', false)
            ->whereRaw('LOWER(name) = ?', [strtolower($appName)])
            ->first();

        if (!$application) {
            return response()->json(['exists' => false]);
        }

        // L'application existe → vérifier la version
        $existingManual = Manual::where('application_id', $application->id)
            ->whereRaw("LOWER(COALESCE(version, '1.0')) = ?", [strtolower($version)])
            ->first();

        if ($existingManual) {
            return response()->json([
                'exists'             => true,
                'conflict'           => 'same_version',
                'app_name'           => $application->name,
                'version'            => $version,
                'existing_manual_id' => $existingManual->id,
            ]);
        }

        $otherManual = Manual::where('application_id', $application->id)
            ->whereRaw("LOWER(COALESCE(version, '1.0')) <> ?", [strtolower($version)])
            ->orderByDesc('created_at')
            ->first();

        if ($otherManual) {
            return response()->json([
                'exists'             => true,
                'conflict'           => 'diff_version',
                'app_name'           => $application->name,
                'existing_version'   => $this->normalizeManualVersion($otherManual->version),
                'existing_manual_id' => $otherManual->id,
            ]);
        }

        return response()->json(['exists' => false]);
    }

    public function storeManual(Request $request): JsonResponse
    {
        $maxKb = (int) config('services.extract.max_upload_kb', 512000);

        if (!$request->hasFile('file') && $request->isMethod('post')) {
            return response()->json(['success' => false, 'message' => 'Fichier trop volumineux.'], 422);
        }

        $request->validate([
            'name'                => ['required', 'string', 'max:255'],
            'app_name'            => ['required', 'string', 'max:255'],
            'version'             => ['nullable', 'string', 'max:20'],
            'file'                => ['required', 'file', 'mimes:pdf', "max:{$maxKb}"],
            'conflict_resolution' => ['nullable', 'in:complementary,contradictory'],
            'existing_manual_id'  => ['nullable', 'integer', 'exists:manuals,id'],
        ]);

        $appName    = trim($request->input('app_name'));
        $version    = $this->normalizeManualVersion($request->input('version', '1.0'));
        $resolution = $request->input('conflict_resolution');

        // Recherche exacte (is_faq = false)
        $application = Application::where('is_faq', false)
            ->whereRaw('LOWER(name) = ?', [strtolower($appName)])
            ->first();

        if ($application) {
            // Vérifier doublon même version
            $sameVersionManual = Manual::where('application_id', $application->id)
                ->whereRaw("LOWER(COALESCE(version, '1.0')) = ?", [strtolower($version)])
                ->first();

            if ($sameVersionManual) {
                return response()->json([
                    'success'            => false,
                    'conflict'           => 'same_version',
                    'app_name'           => $application->name,
                    'version'            => $version,
                    'message'            => "L'application '{$application->name}' avec la version '{$version}' existe déjà.",
                ], 409);
            }

            // Version différente sans résolution choisie
            $otherVersionManual = Manual::where('application_id', $application->id)
                ->whereRaw("LOWER(COALESCE(version, '1.0')) <> ?", [strtolower($version)])
                ->orderByDesc('created_at')
                ->first();

            if ($otherVersionManual && !$resolution) {
                return response()->json([
                    'success'            => false,
                    'exists'             => true,
                    'conflict'           => 'diff_version',
                    'app_name'           => $application->name,
                    'existing_version'   => $this->normalizeManualVersion($otherVersionManual->version),
                    'existing_manual_id' => $otherVersionManual->id,
                    'message'            => 'Une version différente existe déjà. Choisissez complémentaire ou contradictoire.',
                ], 409);
            }
        }

        // RESOLUTION 1 : Complémentaire — fusionner les PDFs
        if ($resolution === 'complementary' && $application) {
            return $this->handleComplementaryManual($request, $appName, $application, $version);
        }

        // RESOLUTION 2 : Contradictoire — le nom fourni par l'admin EST le nouveau nom
        // L'admin doit avoir saisi un nom différent (ex: "SAP v2") dans le champ app_name
        // On refuse si ce nom existe déjà (is_faq=false)
        if ($resolution === 'contradictory') {
            // Le nom contradictoire = appName (déjà saisi par l'admin, potentiellement différent)
            // On crée simplement une nouvelle application avec ce nom exact
            $existingNew = Application::where('is_faq', false)
                ->whereRaw('LOWER(name) = ?', [strtolower($appName)])
                ->first();

            if ($existingNew && $existingNew->id !== $application?->id) {
                return response()->json([
                    'success'  => false,
                    'conflict' => 'same_version',
                    'app_name' => $appName,
                    'version'  => $version,
                    'message'  => "Le nom d'application '{$appName}' existe déjà.",
                ], 409);
            }

            // Si même application, on crée quand même un manuel dessus
            // (cas où l'admin a changé d'avis et veut juste un nouveau manuel)
            $application = $application ?? Application::create(['name' => $appName, 'is_faq' => false]);
        }

        // Cas normal : créer ou récupérer l'application et créer le manuel
        if (!$application) {
            $application = Application::create(['name' => $appName, 'is_faq' => false]);
        }

        $fileName = $this->buildPdfFileName($request->input('name'));
        $this->storeManualPdf($request, $fileName);

        $manual = Manual::create([
            'name'           => $request->input('name'),
            'application_id' => $application->id,
            'version'        => $version,
            'file_path'      => $fileName,
            'status'         => 'processing',
        ]);

        ProcessManualPipeline::dispatch($manual->id);

        return response()->json(['success' => true, 'manual' => $manual->fresh('application')]);
    }

    private function handleComplementaryManual(
        Request $request,
        string $appName,
        Application $application,
        string $newVersion
    ): JsonResponse {
        $existingManualId = $request->input('existing_manual_id');
        $existingManual   = $existingManualId
            ? Manual::find($existingManualId)
            : Manual::where('application_id', $application->id)->orderByDesc('created_at')->first();

        if (!$existingManual) {
            return response()->json(['success' => false, 'message' => 'Manuel existant non trouvé.'], 404);
        }

        $manualsDir   = $this->getManualsDir();
        $existingPath = $this->absolutePath($existingManual->file_path, $manualsDir);

        if (!file_exists($existingPath)) {
            return response()->json(['success' => false, 'message' => 'Fichier manuel existant introuvable.'], 404);
        }

        // Stocker le nouveau PDF temporairement
        $tempDir      = sys_get_temp_dir();
        $tempFileName = 'new_pdf_' . uniqid() . '.pdf';
        $request->file('file')->move($tempDir, $tempFileName);
        $tempNewPdfPath = $tempDir . '/' . $tempFileName;

        // Fusionner
        $mergedFileName = $this->buildMergedPdfFileName($existingManual->file_path);
        $mergedPath     = $manualsDir . '/' . $mergedFileName;

        try {
            $this->mergePdfFiles($existingPath, $tempNewPdfPath, $mergedPath);
        } catch (\Exception $e) {
            Log::error('[AdminController] Erreur fusion PDF', ['error' => $e->getMessage()]);
            if (file_exists($tempNewPdfPath)) @unlink($tempNewPdfPath);
            return response()->json(['success' => false, 'message' => 'Erreur pendant la fusion des PDFs.'], 500);
        }

        if (file_exists($tempNewPdfPath)) @unlink($tempNewPdfPath);

        $oldCleanedJsonPath = $existingManual->cleaned_json_path;

        DB::transaction(function () use ($existingManual, $mergedFileName, $newVersion) {
            $this->deleteManualPdf($existingManual->file_path);
            $existingManual->update([
                'file_path'         => $mergedFileName,
                'status'            => 'processing',
                'processing_error'  => null,
                'cleaned_json_path' => null,
                'version'           => $newVersion,
            ]);
            // Le nom de l'application ne change PAS dans le cas complémentaire
        });

        // Supprimer les données Qdrant et les fichiers JSON de l'ancien index
        if ($oldCleanedJsonPath) {
            $oldCollection = $this->collectionNameFromCleanedPath($oldCleanedJsonPath);
            if ($oldCollection) {
                $this->deleteQdrantCollection($oldCollection);
            }
            $this->deleteJsonFiles($oldCleanedJsonPath);
        }

        ProcessManualPipeline::dispatch($existingManual->id)->afterCommit();

        Log::info('[AdminController] PDF fusionné avec succès', [
            'manual_id'     => $existingManual->id,
            'merged_file'   => $mergedFileName,
            'new_version'   => $newVersion,
        ]);

        return response()->json([
            'success' => true,
            'message' => 'PDF fusionné avec succès, réindexation en cours',
            'manual'  => $existingManual->fresh('application'),
        ]);
    }

    public function showManual(int $id): JsonResponse
    {
        $manual = Manual::with('application')->findOrFail($id);
        return response()->json(array_merge($manual->toArray(), [
            'app_name' => $manual->application->name ?? '',
        ]));
    }

    public function updateManual(Request $request, int $id): JsonResponse
    {
        $manual = Manual::findOrFail($id);
        $maxKb  = (int) config('services.extract.max_upload_kb', 512000);

        $request->validate([
            'name'     => ['required', 'string', 'max:255'],
            'app_name' => ['required', 'string', 'max:255'],
            'version'  => ['nullable', 'string', 'max:20'],
            'file'     => ['nullable', 'file', 'mimes:pdf', "max:{$maxKb}"],
        ]);

        $appName     = trim($request->input('app_name'));
        $application = $this->findOrCreateManualApplication($appName);

        $updateData = [
            'name'           => $request->input('name'),
            'application_id' => $application->id,
            'version'        => $request->input('version', $manual->version),
        ];

        if ($request->hasFile('file')) {
            if ($manual->cleaned_json_path) {
                $oldCollection = $this->collectionNameFromCleanedPath($manual->cleaned_json_path);
                if ($oldCollection) {
                    $this->deleteQdrantCollection($oldCollection);
                }
                $this->deleteJsonFiles($manual->cleaned_json_path);
            }

            $this->deleteManualPdf($manual->file_path);
            $fileName = $this->buildPdfFileName($request->input('name'));
            $this->storeManualPdf($request, $fileName);

            $updateData['file_path']         = $fileName;
            $updateData['status']            = 'processing';
            $updateData['processing_error']  = null;
            $updateData['cleaned_json_path'] = null;

            ProcessManualPipeline::dispatch($manual->id);
        }

        $manual->update($updateData);

        return response()->json(['success' => true]);
    }

    public function destroyManual(int $id): JsonResponse
    {
        $manual = Manual::with('application')->findOrFail($id);

        Log::info('[AdminController] Suppression du manuel', [
            'manual_id'         => $manual->id,
            'name'              => $manual->name,
            'file_path'         => $manual->file_path,
            'cleaned_json_path' => $manual->cleaned_json_path,
        ]);

        $extractDir = rtrim((string) config('services.extract.extract_dir', base_path('../../extract/app')), '/');
        $jsonDir    = rtrim((string) config('services.extract.json_dir', $extractDir . '/json'), '/');

        if ($manual->cleaned_json_path) {
            $collection = $this->collectionNameFromCleanedPath($manual->cleaned_json_path);
            if ($collection) {
                $this->deleteQdrantCollection($collection);

                $qdrantDataDir       = rtrim((string) config('services.qdrant.data_dir', base_path('../../prod/qdrant_data')), '/');
                $qdrantCollectionDir = $qdrantDataDir . '/collection/' . $collection;
                $this->deleteDirectory($qdrantCollectionDir);

                $metaPath = $qdrantDataDir . '/meta.json';
                if (is_file($metaPath)) {
                    try {
                        $meta = json_decode(file_get_contents($metaPath), true) ?: [];
                        if (isset($meta['collections']) && is_array($meta['collections'])) {
                            $changed = false;
                            foreach ($meta['collections'] as $k => $c) {
                                if (is_array($c) && ($c['name'] ?? '') === $collection) {
                                    unset($meta['collections'][$k]);
                                    $changed = true;
                                }
                            }
                            if ($changed) {
                                $meta['collections'] = array_values($meta['collections']);
                                @file_put_contents($metaPath, json_encode($meta, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
                            }
                        }
                    } catch (\Throwable $e) {
                        Log::warning('[AdminController] Impossible de mettre à jour meta.json', ['error' => $e->getMessage()]);
                    }
                }
            }

            $this->deleteJsonFiles($manual->cleaned_json_path);

            $cleanedFilename = basename($manual->cleaned_json_path);
            $baseName        = preg_replace('/_2levels_cleaned\.json$/', '', $cleanedFilename);
            if ($baseName) {
                $imagesDir = $jsonDir . '/images/' . $baseName;
                $this->deleteDirectory($imagesDir);

                $extractLogsDir = rtrim($extractDir . '/logs/extractor', '/');
                if (is_dir($extractLogsDir)) {
                    foreach (glob($extractLogsDir . '/' . $baseName . '*.log') as $f) {
                        $this->deleteFile($f);
                    }
                }
            }
        } else {
            $this->deleteJsonFilesByPdfName($manual->file_path);

            $baseName = pathinfo($manual->file_path, PATHINFO_FILENAME);
            if ($baseName) {
                $imagesDir = $jsonDir . '/images/' . $baseName;
                $this->deleteDirectory($imagesDir);

                $extractLogsDir = rtrim($extractDir . '/logs/extractor', '/');
                if (is_dir($extractLogsDir)) {
                    foreach (glob($extractLogsDir . '/' . $baseName . '*.log') as $f) {
                        $this->deleteFile($f);
                    }
                }
            }
        }

        $this->deleteManualPdf($manual->file_path);

        $deletedMessages = Message::where('manual_id', $manual->id)->delete();
        if ($deletedMessages > 0) {
            Log::info('[AdminController] Messages supprimés', ['manual_id' => $manual->id, 'deleted_count' => $deletedMessages]);
        }

        Conversation::where('application_id', $manual->application_id)
            ->whereDoesntHave('messages')
            ->delete();

        $manual->delete();

        return response()->json(['success' => true]);
    }

    // ──────────────────────────────────────────────────────────────────
    // FAQ MANAGEMENT
    // ──────────────────────────────────────────────────────────────────

    public function faqDashboard()
    {
        return redirect()->route('admin.index', ['section' => 'faq']);
    }

    /**
     * Upload une FAQ JSON pour une application.
     * - Crée ou retrouve une Application avec is_faq = true et le nom exact fourni.
     * - Le nom doit être unique parmi les applications FAQ.
     * - Stockage local dans {faq_dir}/{slug}.json puis envoi au pipeline.
     */
    public function faqUpload(Request $request): JsonResponse
    {
        $request->validate([
            'app_id'   => ['nullable', 'integer'],
            'app_name' => ['nullable', 'string', 'max:255'],
            'file'     => ['required', 'file', 'mimes:json,txt'],
        ]);

        // Résoudre app_id XOR app_name
        $appId       = trim((string) $request->input('app_id', ''));
        $appNameInput = trim((string) $request->input('app_name', ''));

        if ($appId !== '' && $appNameInput !== '') {
            return response()->json(['success' => false, 'error' => 'Choisissez une application OU saisissez un nom, pas les deux.'], 422);
        }
        if ($appId === '' && $appNameInput === '') {
            return response()->json(['success' => false, 'error' => "Veuillez choisir ou saisir le nom de l'application."], 422);
        }

        if ($appId !== '') {
            $application = Application::find((int) $appId);
            if (!$application) {
                return response()->json(['success' => false, 'error' => 'Application introuvable.'], 422);
            }
            // Si cette application est is_faq=false, on crée/récupère son pendant FAQ
            if (!$application->is_faq) {
                $application = $this->findOrCreateFaqApplication($application->name);
            }
            $appName = $application->name;
        } else {
            // Vérifier unicité du nom parmi les applications FAQ
            $application = $this->findOrCreateFaqApplication($appNameInput);
            $appName     = $application->name;
        }

        $slug = $this->appNameToFaqSlug($appName);

        // Lecture et validation JSON
        try {
            $raw     = file_get_contents($request->file('file')->getRealPath());
            $decoded = json_decode($raw, true, 512, JSON_THROW_ON_ERROR);
        } catch (\Throwable $e) {
            return response()->json(['success' => false, 'error' => 'JSON invalide : ' . $e->getMessage()], 422);
        }

        $items = $decoded['items'] ?? $decoded;
        if (!is_array($items)) {
            return response()->json(['success' => false, 'error' => "Le JSON doit contenir un tableau d'entrées FAQ."], 422);
        }

        // Sauvegarder localement
        $faqDir = $this->getFaqDir();
        if (!is_dir($faqDir)) mkdir($faqDir, 0775, true);
        $faqFile = $faqDir . '/' . $slug . '.json';
        file_put_contents($faqFile, json_encode(['items' => $items], JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));

        Log::info('[FAQ Upload] Fichier sauvegardé localement', ['file' => $faqFile, 'item_count' => count($items)]);

        ProcessFaqPipeline::dispatch('sync');

        return response()->json([
            'success'    => true,
            'app_id'     => $application->id,
            'app_name'   => $appName,
            'slug'       => $slug,
            'collection' => 'faq',
            'file'       => $faqFile,
            'item_count' => count($items),
            'updated_at' => date('d/m/Y', filemtime($faqFile)),
        ]);
    }

    /**
     * Retourne les entrées FAQ d'une application (lecture locale prioritaire, fallback backend).
     */
    public function faqShow(string $app): JsonResponse
    {
        [$application, $slug, $appName] = $this->resolveFaqApp($app);

        $faqFile = $this->getFaqDir() . '/' . $slug . '.json';

        // Priorité 1 : fichier local
        if (file_exists($faqFile)) {
            try {
                $data  = json_decode(file_get_contents($faqFile), true) ?: [];
                $items = $data['items'] ?? $data;
                $items = is_array($items) ? array_values($items) : [];

                return response()->json([
                    'app_id'     => $application?->id ?? $app,
                    'app_name'   => $appName,
                    'slug'       => $slug,
                    'collection' => 'faq',
                    'faq'        => $items,
                    'item_count' => count($items),
                    'source'     => 'local',
                ]);
            } catch (\Throwable $e) {
                Log::warning('[FAQ Show] Erreur lecture fichier local', ['file' => $faqFile, 'error' => $e->getMessage()]);
            }
        }

        // Priorité 2 : backend FastAPI
        $collection = $application?->qdrant_collection ?? $slug;
        $backendUrl = rtrim((string) config('services.backend.url', 'http://127.0.0.1:8000'), '/');
        $url        = $backendUrl . '/api/admin/faq/' . urlencode($collection);

        try {
            $client   = new \GuzzleHttp\Client(['timeout' => 30]);
            $response = $client->get($url);
            $data     = json_decode((string) $response->getBody(), true);
            $items    = $data['faq'] ?? $data['items'] ?? [];

            if (is_array($items) && count($items) > 0) {
                $faqDir = $this->getFaqDir();
                if (!is_dir($faqDir)) mkdir($faqDir, 0775, true);
                file_put_contents($faqFile, json_encode(['items' => $items], JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
            }

            return response()->json([
                'app_id'     => $application?->id ?? $app,
                'app_name'   => $appName,
                'slug'       => $slug,
                'collection' => 'faq',
                'faq'        => is_array($items) ? $items : [],
                'item_count' => is_array($items) ? count($items) : 0,
                'source'     => 'backend',
            ]);
        } catch (\Exception $e) {
            Log::info('[FAQ Show] Aucune FAQ trouvée', ['app' => $app, 'slug' => $slug, 'error' => $e->getMessage()]);
            return response()->json([
                'app_id'     => $application?->id ?? $app,
                'app_name'   => $appName,
                'slug'       => $slug,
                'collection' => 'faq',
                'faq'        => [],
                'item_count' => 0,
                'source'     => 'empty',
            ]);
        }
    }

    /**
     * Met à jour les entrées FAQ (PUT).
     * Sauvegarde localement ET lance le pipeline de réindexation.
     */
    public function faqUpdate(Request $request, string $app): JsonResponse
    {
        $request->validate([
            'items' => ['required', 'array'],
        ]);

        $items = $request->input('items');
        [$application, $slug] = $this->resolveFaqApp($app);

        $faqDir = $this->getFaqDir();
        if (!is_dir($faqDir)) mkdir($faqDir, 0775, true);
        $faqFile = $faqDir . '/' . $slug . '.json';
        file_put_contents($faqFile, json_encode(['items' => array_values($items)], JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));

        Log::info('[FAQ Update] Fichier local mis à jour', ['file' => $faqFile, 'item_count' => count($items)]);

        // Relancer le pipeline de réindexation
        ProcessFaqPipeline::dispatch('sync');

        return response()->json(['success' => true, 'item_count' => count($items), 'slug' => $slug, 'collection' => 'faq']);
    }

    /**
     * Met à jour les métadonnées d'une FAQ (app_name).
     * Si le nom change, renomme le fichier JSON et met à jour la BDD.
     * Le nom doit rester unique parmi les applications FAQ.
     */
    public function faqUpdateInfos(Request $request, string $app): JsonResponse
    {
        try {
            $request->validate([
                'app_name' => ['required', 'string', 'max:255'],
                'version'  => ['nullable', 'string', 'max:20'],
            ]);

            $newAppName = trim($request->input('app_name'));
            $version    = trim($request->input('version', ''));

            [$application, $oldSlug, $oldAppName] = $this->resolveFaqApp($app);

            $newSlug = $this->appNameToFaqSlug($newAppName);

            // Vérifier que le nouveau nom n'est pas déjà pris par une AUTRE application FAQ
            if (strtolower($newAppName) !== strtolower($oldAppName)) {
                $conflict = Application::where('is_faq', true)
                    ->whereRaw('LOWER(name) = ?', [strtolower($newAppName)])
                    ->when($application, fn($q) => $q->where('id', '!=', $application->id))
                    ->first();

                if ($conflict) {
                    return response()->json([
                        'success' => false,
                        'error'   => "Le nom d'application FAQ '{$newAppName}' est déjà utilisé.",
                    ], 409);
                }
            }

            // Mettre à jour ou créer l'application FAQ en BDD
            if ($application) {
                $application->update(['name' => $newAppName]);
            } else {
                $application = Application::create(['name' => $newAppName, 'is_faq' => true]);
            }

            // Renommer le fichier si le slug change
            $faqDir  = $this->getFaqDir();
            $oldFile = $faqDir . '/' . $oldSlug . '.json';
            $newFile = $faqDir . '/' . $newSlug . '.json';

            if ($oldSlug !== $newSlug && file_exists($oldFile)) {
                try {
                    rename($oldFile, $newFile);
                    Log::info('[FAQ Update Infos] Fichier renommé', ['old' => $oldFile, 'new' => $newFile]);
                } catch (\Throwable $e) {
                    Log::warning('[FAQ Update Infos] Impossible de renommer le fichier', [
                        'error' => $e->getMessage(), 'old' => $oldFile, 'new' => $newFile,
                    ]);
                }
            }

            Log::info('[FAQ Update Infos] Métadonnées mises à jour', [
                'app_id'   => $application->id,
                'app_name' => $newAppName,
                'version'  => $version,
                'slug'     => $newSlug,
            ]);

            return response()->json([
                'success'  => true,
                'app_id'   => $application->id,
                'app_name' => $newAppName,
                'version'  => $version,
                'slug'     => $newSlug,
            ]);
        } catch (\Throwable $e) {
            Log::error('[FAQ Update Infos] Erreur', ['error' => $e->getMessage(), 'app' => $app]);
            return response()->json(['success' => false, 'error' => $e->getMessage()], 500);
        }
    }

    /**
     * Déclenche manuellement l'indexation FAQ.
     */
    public function faqIndex(string $app): JsonResponse
    {
        ProcessFaqPipeline::dispatch('sync');
        return response()->json(['success' => true, 'collection' => 'faq']);
    }

    /**
     * Supprime une FAQ (fichier local + pipeline sync).
     */
    public function faqDestroy(string $app): JsonResponse
    {
        [$application, $slug] = $this->resolveFaqApp($app);

        $faqFile = $this->getFaqDir() . '/' . $slug . '.json';
        $deleted = file_exists($faqFile) ? @unlink($faqFile) : false;

        if (!$deleted) {
            return response()->json(['success' => false, 'error' => 'FAQ introuvable'], 404);
        }

        ProcessFaqPipeline::dispatch('sync');

        return response()->json(['success' => true, 'slug' => $slug, 'collection' => 'faq']);
    }

    // ──────────────────────────────────────────────────────────────────
    // CHATS ANONYMISÉS
    // ──────────────────────────────────────────────────────────────────

    /**
     * Retourne les conversations anonymisées filtrées par application_id.
     * - Uniquement les messages où le chatbot a répondu (role=assistant)
     * - Exclut les réponses "Je ne peux pas répondre..."
     */
    public function chatsShow(string $app): JsonResponse
    {
        $application = $this->resolveAnyApplication($app);

        if (!$application) {
            return response()->json(['chats' => [], 'error' => 'Application introuvable'], 404);
        }

        $limit = min((int) request()->input('limit', 100), 500);

        $excludedPhrases = [
            'je ne peux pas répondre',
            'je ne dispose pas',
            'aucune information disponible dans',
            "je n'ai pas trouvé",
            "je n'ai pas d'information",
            'hors de ma portée',
            'je suis désolé, je ne',
            'cette question dépasse',
            'ne figure pas dans',
        ];

        try {
            $conversations = Conversation::where('application_id', $application->id)
                ->with(['messages' => fn($q) => $q->orderBy('created_at', 'asc')])
                ->orderByDesc('created_at')
                ->limit($limit)
                ->get();

            $statusOrder = ['pending' => 0, 'validated' => 1, 'rejected' => 2];
            $chats       = [];

            foreach ($conversations as $conversation) {
                $messages     = $conversation->messages;
                $userMessages = $messages->where('role', 'user');

                foreach ($userMessages as $userMsg) {
                    $assistantMsg = $messages
                        ->where('role', 'assistant')
                        ->where('created_at', '>', $userMsg->created_at)
                        ->first();

                    if (!$assistantMsg) continue;

                    $answer      = $assistantMsg->content ?? '';
                    $lowerAnswer = mb_strtolower($answer);
                    $excluded    = false;

                    foreach ($excludedPhrases as $phrase) {
                        if (str_contains($lowerAnswer, $phrase)) { $excluded = true; break; }
                    }
                    if ($excluded || mb_strlen(trim($answer)) < 20) continue;

                    $sources = [];
                    $meta    = is_string($assistantMsg->metadata)
                        ? json_decode($assistantMsg->metadata, true)
                        : ($assistantMsg->metadata ?? []);
                    if (is_array($meta)) {
                        $sources = $meta['sources'] ?? $meta['references'] ?? [];
                    }

                    $faqStatus = $assistantMsg->faq_status ?? 'pending';

                    $chats[] = [
                        'conversation_id' => $conversation->id,
                        'message_id'      => $userMsg->id,
                        'assistant_id'    => $assistantMsg->id,
                        'question'        => $userMsg->content ?? '',
                        'answer'          => $answer,
                        'app_id'          => $application->id,
                        'app_name'        => $application->name,
                        'sources'         => $sources,
                        'status'          => $faqStatus,
                        'status_label'    => match ($faqStatus) {
                            'validated' => 'Validée',
                            'rejected'  => 'Rejetée',
                            default     => 'En attente',
                        },
                    ];
                }
            }

            usort($chats, function ($a, $b) use ($statusOrder) {
                $oa = $statusOrder[$a['status']] ?? 99;
                $ob = $statusOrder[$b['status']] ?? 99;
                return $oa !== $ob ? $oa <=> $ob : strcmp($b['conversation_id'], $a['conversation_id']);
            });

            return response()->json(['chats' => $chats, 'total' => count($chats)]);

        } catch (\Throwable $e) {
            Log::error('[Chats Show] Erreur BDD', ['error' => $e->getMessage()]);
            return $this->chatsShowFromBackend($application, $limit);
        }
    }

    private function chatsShowFromBackend(Application $application, int $limit): JsonResponse
    {
        $collection = $application->qdrant_collection ?? $this->appNameToFaqSlug($application->name);
        $backendUrl = rtrim((string) config('services.backend.url', 'http://127.0.0.1:8000'), '/');
        $url        = $backendUrl . '/api/admin/chats/' . urlencode($collection) . '?limit=' . $limit;

        try {
            $client   = new \GuzzleHttp\Client(['timeout' => 30]);
            $response = $client->get($url);
            $data     = json_decode((string) $response->getBody(), true);

            $excludedPhrases = ['je ne peux pas répondre', 'je ne dispose pas', 'aucune information disponible', "je n'ai pas"];
            $chats = array_filter($data['chats'] ?? [], function ($chat) use ($excludedPhrases) {
                $lowerAnswer = mb_strtolower($chat['answer'] ?? '');
                foreach ($excludedPhrases as $phrase) {
                    if (str_contains($lowerAnswer, $phrase)) return false;
                }
                return mb_strlen(trim($chat['answer'] ?? '')) >= 20;
            });

            return response()->json(['chats' => array_values($chats)]);
        } catch (\Exception $e) {
            Log::error('[Chats Show Backend] Erreur', ['error' => $e->getMessage()]);
            return response()->json(['chats' => [], 'error' => $e->getMessage()]);
        }
    }

    /**
     * Rejette un chat — statut → 'rejected'.
     */
    public function chatReject(string $app, int $messageId): JsonResponse
    {
        try {
            $message      = Message::findOrFail($messageId);
            $conversation = Conversation::findOrFail($message->conversation_id);
            $application  = $this->resolveAnyApplication($app);

            if (!$application || $conversation->application_id !== $application->id) {
                return response()->json(['success' => false, 'error' => 'Message non trouvé pour cette application'], 404);
            }

            $message->update(['faq_status' => 'rejected']);

            Log::info('[Chat Reject] Message rejeté', ['message_id' => $messageId, 'app_id' => $application->id]);

            return response()->json(['success' => true, 'message' => 'Réponse rejetée']);
        } catch (\Throwable $e) {
            Log::error('[Chat Reject] Erreur', ['error' => $e->getMessage(), 'message_id' => $messageId]);
            return response()->json(['success' => false, 'error' => $e->getMessage()], 500);
        }
    }

    /**
     * Valide un chat et l'ajoute à la FAQ de l'application.
     *
     * Deux cas :
     *  1. Un fichier JSON FAQ local existe déjà → append + réindexation.
     *  2. Pas de FAQ locale → création d'un nouveau fichier JSON + réindexation.
     *
     * Dans les deux cas, le pipeline ProcessFaqPipeline est déclenché.
     */
    public function chatValidate(Request $request, string $app): JsonResponse
    {
        $request->validate([
            'question'             => ['required', 'string', 'min:5'],
            'answer'               => ['required', 'string', 'min:10'],
            'assistant_message_id' => ['nullable', 'integer'],
        ]);

        $question           = trim($request->input('question'));
        $answer             = trim($request->input('answer'));
        $assistantMessageId = $request->input('assistant_message_id');

        // Résoudre l'application (peut être manuel ou faq)
        $application = $this->resolveAnyApplication($app);
        $appName     = $application?->name ?? $app;

        // Récupérer/créer l'application FAQ correspondante
        $faqApplication = $this->findOrCreateFaqApplication($appName);
        $slug           = $this->appNameToFaqSlug($appName);

        $faqDir  = $this->getFaqDir();
        if (!is_dir($faqDir)) mkdir($faqDir, 0775, true);
        $faqFile = $faqDir . '/' . $slug . '.json';

        // Charger ou initialiser la FAQ existante
        $items    = [];
        $isNewFaq = true;
        if (file_exists($faqFile)) {
            try {
                $existing = json_decode(file_get_contents($faqFile), true) ?: [];
                $items    = $existing['items'] ?? $existing;
                $items    = is_array($items) ? $items : [];
                $isNewFaq = false;
            } catch (\Throwable $e) {
                $items = [];
            }
        }

        // Vérifier doublon (question identique)
        foreach ($items as $existingItem) {
            $existingQ = mb_strtolower(trim($existingItem['question'] ?? $existingItem['q'] ?? ''));
            if ($existingQ === mb_strtolower($question)) {
                return response()->json([
                    'success' => false,
                    'error'   => 'Cette question existe déjà dans la FAQ.',
                ], 422);
            }
        }

        // Append du nouvel item
        $items[] = [
            'id'       => 'validated_' . Str::uuid(),
            'question' => $question,
            'answer'   => $answer,
            'source'   => 'admin_validated',
        ];

        // Sauvegarder localement
        file_put_contents($faqFile, json_encode(['items' => array_values($items)], JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));

        Log::info('[Chat Validate] Entrée ajoutée à la FAQ', [
            'file'       => $faqFile,
            'slug'       => $slug,
            'app_name'   => $appName,
            'item_count' => count($items),
            'is_new_faq' => $isNewFaq,
        ]);

        // Récupérer la version du dernier manuel indexé (si applicable)
        $manualVersion = null;
        if ($application) {
            $manualApp = Application::where('is_faq', false)
                ->whereRaw('LOWER(name) = ?', [strtolower($appName)])
                ->first();
            if ($manualApp) {
                $latestManual = Manual::where('application_id', $manualApp->id)
                    ->where('status', 'indexed')
                    ->latest('created_at')
                    ->first();
                $manualVersion = $latestManual?->version;
            }
        }

        // Marquer le message assistant comme validé
        if ($assistantMessageId) {
            try {
                $am = Message::find($assistantMessageId);
                if ($am) $am->update(['faq_status' => 'validated']);
            } catch (\Throwable $e) {
                Log::warning('[Chat Validate] Unable to update assistant message status', ['error' => $e->getMessage()]);
            }
        }

        // Envoyer au backend + lancer le pipeline de réindexation
        $collection = $faqApplication->qdrant_collection ?? $slug;
        $backendUrl = rtrim((string) config('services.backend.url', 'http://127.0.0.1:8000'), '/');

        try {
            $client   = new \GuzzleHttp\Client(['timeout' => 120]);
            $response = $client->put(
                $backendUrl . '/api/admin/faq/' . urlencode($collection) . '?reindex=true',
                ['json' => ['items' => $items]]
            );
            $data = json_decode((string) $response->getBody(), true);

            ProcessFaqPipeline::dispatch('sync');

            return response()->json([
                'success'    => true,
                'data'       => $data,
                'item_count' => count($items),
                'slug'       => $slug,
                'app_name'   => $appName,
                'app_id'     => $faqApplication->id,
                'version'    => $manualVersion,
                'is_new_faq' => $isNewFaq,
                'updated_at' => date('d/m/Y', filemtime($faqFile)),
            ]);
        } catch (\Exception $e) {
            Log::warning('[Chat Validate] Backend inaccessible, FAQ sauvegardée localement', ['error' => $e->getMessage()]);

            ProcessFaqPipeline::dispatch('sync');

            return response()->json([
                'success'         => true,
                'backend_warning' => $e->getMessage(),
                'item_count'      => count($items),
                'slug'            => $slug,
                'app_name'        => $appName,
                'app_id'          => $faqApplication->id,
                'version'         => $manualVersion,
                'is_new_faq'      => $isNewFaq,
                'updated_at'      => date('d/m/Y', filemtime($faqFile)),
            ]);
        }
    }

    // ──────────────────────────────────────────────────────────────────
    // HELPERS RÉSOLUTION D'APPLICATION
    // ──────────────────────────────────────────────────────────────────

    /**
     * Résout n'importe quelle application (faq ou manuelle) par ID ou nom.
     */
    private function resolveAnyApplication(string $app): ?Application
    {
        if (is_numeric($app)) {
            return Application::find((int) $app);
        }
        $slug = $this->appNameToFaqSlug($app);
        return Application::whereRaw('LOWER(name) = ?', [strtolower($app)])->first()
            ?? Application::whereRaw('LOWER(REPLACE(REPLACE(name, \' \', \'_\'), \'-\', \'_\')) = ?', [strtolower($slug)])->first();
    }

    /**
     * Résout une application FAQ (is_faq = true) et retourne [application, slug, appName].
     */
    private function resolveFaqApp(string $app): array
    {
        $application = null;
        $appName     = $app;

        if (is_numeric($app)) {
            $application = Application::find((int) $app);
            $appName     = $application?->name ?? $app;
        } else {
            $slug        = $this->appNameToFaqSlug($app);
            $application = Application::where('is_faq', true)
                ->whereRaw('LOWER(name) = ?', [strtolower($app)])
                ->first()
                ?? Application::where('is_faq', true)
                    ->whereRaw('LOWER(REPLACE(REPLACE(name, \' \', \'_\'), \'-\', \'_\')) = ?', [strtolower($slug)])
                    ->first();
            if ($application) $appName = $application->name;
        }

        $slug = $this->appNameToFaqSlug($appName);
        return [$application, $slug, $appName];
    }

    /**
     * Trouve ou crée une application FAQ (is_faq = true) avec le nom exact fourni.
     * Le nom doit être unique parmi les applications FAQ.
     */
    private function findOrCreateFaqApplication(string $name): Application
    {
        $existing = Application::where('is_faq', true)
            ->whereRaw('LOWER(name) = ?', [strtolower($name)])
            ->first();

        if ($existing) return $existing;

        return Application::create(['name' => $name, 'is_faq' => true]);
    }

    /**
     * Trouve ou crée une application manuelle (is_faq = false) avec le nom exact fourni.
     * Le nom doit être unique parmi les applications manuelles.
     */
    private function findOrCreateManualApplication(string $name): Application
    {
        $existing = Application::where('is_faq', false)
            ->whereRaw('LOWER(name) = ?', [strtolower($name)])
            ->first();

        if ($existing) return $existing;

        return Application::create(['name' => $name, 'is_faq' => false]);
    }

    // ──────────────────────────────────────────────────────────────────
    // HELPERS FICHIERS / QDRANT
    // ──────────────────────────────────────────────────────────────────

    private function collectionNameFromCleanedPath(?string $cleanedJsonPath): ?string
    {
        if (!$cleanedJsonPath) return null;
        $stem = pathinfo($cleanedJsonPath, PATHINFO_FILENAME);
        if (!str_ends_with($stem, '_2levels_cleaned')) {
            Log::warning('[AdminController] Nom de fichier nettoyé inattendu', ['stem' => $stem]);
            return null;
        }
        return str_replace([' ', '-'], '_', $stem);
    }

    private function deleteJsonFiles(string $cleanedJsonPath): void
    {
        $jsonDir         = dirname($cleanedJsonPath);
        $cleanedFilename = basename($cleanedJsonPath);
        $this->deleteFile($cleanedJsonPath);

        $rawFilename = str_replace('_2levels_cleaned.json', '_2levels.json', $cleanedFilename);
        if ($rawFilename !== $cleanedFilename) {
            $this->deleteFile($jsonDir . DIRECTORY_SEPARATOR . $rawFilename);
        }

        $baseName = preg_replace('/_2levels_cleaned\.json$/', '', $cleanedFilename);
        if ($baseName) {
            foreach (glob($jsonDir . DIRECTORY_SEPARATOR . $baseName . '*.json') as $f) {
                $this->deleteFile($f);
            }
        }
    }

    private function deleteJsonFilesByPdfName(string $pdfFileName): void
    {
        $extractDir = rtrim((string) config('services.extract.extract_dir', base_path('../../extract/app')), '/');
        $jsonDir    = rtrim((string) config('services.extract.json_dir', $extractDir . '/json'), '/');
        $baseName   = pathinfo($pdfFileName, PATHINFO_FILENAME);

        $this->deleteFile($jsonDir . '/' . $baseName . '_2levels.json');
        $this->deleteFile($jsonDir . '/' . $baseName . '_2levels_cleaned.json');
        foreach (glob($jsonDir . '/' . $baseName . '*.json') as $f) {
            $this->deleteFile($f);
        }
    }

    private function deleteQdrantCollection(string $collectionName): void
    {
        $qdrantUrl = rtrim((string) config('services.qdrant.url', 'http://127.0.0.1:6333'), '/');
        $url       = $qdrantUrl . '/collections/' . urlencode($collectionName);

        try {
            $context  = stream_context_create(['http' => ['method' => 'DELETE', 'timeout' => 10, 'ignore_errors' => true]]);
            $response = @file_get_contents($url, false, $context);
            $data     = $response ? json_decode($response, true) : null;
            Log::info('[AdminController] Qdrant DELETE collection', ['collection' => $collectionName, 'result' => $data['result'] ?? null]);
        } catch (\Exception $e) {
            Log::warning("[AdminController] Qdrant '{$collectionName}': " . $e->getMessage());
        }
    }

    private function deleteFile(?string $path): void
    {
        if ($path && is_file($path)) {
            @unlink($path);
            Log::info('[AdminController] Fichier supprimé', ['path' => $path]);
        }
    }

    private function deleteDirectory(?string $path): void
    {
        if (!$path || !is_dir($path)) return;
        $iterator = new \RecursiveIteratorIterator(
            new \RecursiveDirectoryIterator($path, \RecursiveDirectoryIterator::SKIP_DOTS),
            \RecursiveIteratorIterator::CHILD_FIRST
        );
        foreach ($iterator as $file) {
            $file->isDir() ? @rmdir($file->getRealPath()) : @unlink($file->getRealPath());
        }
        @rmdir($path);
        Log::info('[AdminController] Dossier supprimé', ['path' => $path]);
    }

    // ──────────────────────────────────────────────────────────────────
    // HELPERS MANUELS
    // ──────────────────────────────────────────────────────────────────

    private function normalizeManualVersion(?string $version): string
    {
        $value = trim((string) $version);
        return $value === '' ? '1.0' : $value;
    }

    private function buildPdfFileName(string $adminName): string
    {
        $manualsDir = $this->getManualsDir();
        $safe = Str::of($adminName)
            ->replaceMatches('/[\/\\\\:*?"<>|]/', '_')
            ->replaceMatches('/\s+/', '_')
            ->trim('_')
            ->value();
        if ($safe === '') $safe = 'manuel';
        $candidate = $safe . '.pdf';
        $i         = 1;
        while (file_exists($manualsDir . '/' . $candidate)) {
            $candidate = $safe . '_' . $i . '.pdf';
            $i++;
        }
        return $candidate;
    }

    private function storeManualPdf(Request $request, string $fileName): void
    {
        $manualsDir = $this->getManualsDir();
        if (!is_dir($manualsDir)) mkdir($manualsDir, 0775, true);
        $request->file('file')->move($manualsDir, $fileName);
    }

    private function mergePdfFiles(string $existingPath, string $newPdfPath, string $outputPath): void
    {
        $pythonScript = <<<'PYTHON'
import sys, json
try:
    from PyPDF2 import PdfMerger
    merger = PdfMerger()
    merger.append(sys.argv[1])
    merger.append(sys.argv[2])
    merger.write(sys.argv[3])
    merger.close()
    print(json.dumps({"success": True}))
except Exception as e:
    print(json.dumps({"success": False, "error": str(e)}))
PYTHON;

        $tempDir        = sys_get_temp_dir();
        $tempScriptPath = $tempDir . '/merge_pdf_' . uniqid() . '.py';
        file_put_contents($tempScriptPath, $pythonScript);

        $command = sprintf('python3 %s %s %s %s 2>&1',
            escapeshellarg($tempScriptPath),
            escapeshellarg($existingPath),
            escapeshellarg($newPdfPath),
            escapeshellarg($outputPath)
        );
        $output = shell_exec($command);
        if (file_exists($tempScriptPath)) @unlink($tempScriptPath);

        if (!$output) {
            throw new \Exception("Erreur lors de l'exécution du script de fusion (pas de sortie)");
        }
        $result = json_decode($output, true);
        if (!isset($result['success']) || !$result['success']) {
            throw new \Exception($result['error'] ?? 'Erreur inconnue lors de la fusion');
        }
        if (!file_exists($outputPath)) {
            throw new \Exception("Le fichier de sortie n'a pas été créé");
        }

        Log::info('[AdminController] Fusion PDF réussie', ['output_path' => $outputPath]);
    }

    private function buildMergedPdfFileName(string $existingFileName): string
    {
        $baseName  = pathinfo($existingFileName, PATHINFO_FILENAME);
        $extension = pathinfo($existingFileName, PATHINFO_EXTENSION);
        return $baseName . '_merged.' . $extension;
    }

    private function deleteManualPdf(?string $filePath): void
    {
        if (!$filePath) return;
        $this->deleteFile($this->absolutePath($filePath, $this->getManualsDir()));
    }

    private function getManualsDir(): string
    {
        $extractDir = rtrim((string) config('services.extract.extract_dir', base_path('../../extract/app')), '/');
        return rtrim((string) config('services.extract.manuals_dir', $extractDir . '/manuels'), '/');
    }

    private function absolutePath(string $filePath, string $baseDir): string
    {
        return Str::startsWith($filePath, '/')
            ? $filePath
            : rtrim($baseDir, '/') . '/' . ltrim($filePath, '/');
    }
}
