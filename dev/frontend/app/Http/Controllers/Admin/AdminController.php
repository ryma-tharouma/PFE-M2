<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Jobs\ProcessFaqPipeline;
use App\Jobs\ProcessManualPipeline;
use App\Models\Application;
use App\Models\Conversation;
use App\Models\Faq;
use App\Models\Manual;
use App\Models\Message;
use App\Models\Ticket;
use App\Models\User;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class AdminController extends Controller
{
    // ──────────────────────────────────────────────────────────────────
    // DASHBOARD
    // ──────────────────────────────────────────────────────────────────
    public function dashboard()
    {
        $user = auth()->user();

        if ($user->admin_type === 'super') {
            return $this->index();
        }

        return $this->adminDashboard();
    }
    public function index()
    {
        $user = auth()->user();
        if ($user->admin_type !== 'super') {
            return redirect()->route('admin.index');
        }
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

        // ── Ouvert / Fermé + répartition par app et département ────────
        $closedStatuses = ['Résolu', 'Solved', 'Closed', 'solved', 'resolved'];

        $ticketsClosed = Ticket::whereIn('glpi_status', $closedStatuses)->count();
        $ticketsOpen   = Ticket::whereNotIn('glpi_status', $closedStatuses)
                           ->orWhereNull('glpi_status')
                           ->count();

        $ticketsByApp = Ticket::query()
            ->join('conversations', 'tickets.conversation_id', '=', 'conversations.id')
            ->join('applications', 'conversations.application_id', '=', 'applications.id')
            ->selectRaw('applications.name as app_name, count(*) as total')
            ->groupBy('applications.name')
            ->orderByDesc('total')
            ->get()
            ->map(function ($row) use ($totalTickets) {
                $row->percentage = $totalTickets > 0 ? (int) round(($row->total / $totalTickets) * 100) : 0;
                return $row;
            });

        $ticketsByDept = Ticket::query()
            ->join('users', 'tickets.user_id', '=', 'users.id')
            ->whereNotNull('users.department')
            ->selectRaw('users.department, count(*) as total')
            ->groupBy('users.department')
            ->orderByDesc('total')
            ->get()
            ->map(function ($row) use ($totalTickets) {
                $row->percentage = $totalTickets > 0 ? (int) round(($row->total / $totalTickets) * 100) : 0;
                return $row;
            });

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
            'tickets_open'        => $ticketsOpen,
            'tickets_closed'      => $ticketsClosed,
            'tickets_by_app'      => $ticketsByApp,
            'tickets_by_dept'     => $ticketsByDept,
            'users_by_dept'       => $usersByDept,
        ];

        $manuals = Manual::with('application')->orderByDesc('created_at')->paginate(20);
        $tickets = Ticket::with('user')->orderByDesc('created_at')->paginate(20);

        $applications = Application::where('archived', false)->orderBy('name')->get();

        $chatApplications = Application::where('archived', false)
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

    private function writeFaqFile(string $faqFile, array $items): void
    {
        $faqDir = dirname($faqFile);

        if (!is_dir($faqDir)) {
            mkdir($faqDir, 0775, true);
        }

        if (file_exists($faqFile) && !is_writable($faqFile)) {
            @chmod($faqFile, 0664);
        }

        $result = file_put_contents(
            $faqFile,
            json_encode(['items' => $items], JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE)
        );

        if ($result === false) {
            Log::error('[AdminController] Impossible d\'écrire le fichier FAQ', ['file' => $faqFile]);
            throw new \RuntimeException("Impossible d'écrire dans {$faqFile}. Vérifiez les permissions.");
        }
    }

    /**
     * Résout la collection Qdrant d'une application.
     *
     * PRIORITÉ :
     *   1. application->qdrant_collection (valeur en base, la plus fiable)
     *   2. Interrogation du backend pour trouver {slug}_2levels_cleaned ou {slug}
     *
     * Cette méthode NE DOIT être appelée que quand qdrant_collection est null.
     */
    private function resolveQdrantCollection(Application $app): string
    {
        // Priorité 1 : valeur déjà persistée en base
        if (!empty($app->qdrant_collection)) {
            return $app->qdrant_collection;
        }

        $slug       = $this->appNameToFaqSlug($app->name);
        $backendUrl = rtrim((string) config('services.backend.url', 'http://127.0.0.1:8000'), '/');

        try {
            $client    = new \GuzzleHttp\Client(['timeout' => 10]);
            $response  = $client->get($backendUrl . '/api/collections');
            $data      = json_decode((string) $response->getBody(), true);
            $available = $data['collections'] ?? [];

            // Cherche d'abord une collection manuel (_2levels_cleaned)
            // dont le nom contient le slug (gère les préfixes comme "manuel_")
            foreach ($available as $col) {
                if (str_ends_with($col, '_2levels_cleaned') && str_contains($col, $slug)) {
                    return $col;
                }
            }

            // Cherche ensuite une collection FAQ exacte
            if (in_array($slug, $available, true)) {
                return $slug;
            }

            // Fallback : retourne le slug, sera créé à l'indexation
            return $slug;

        } catch (\Throwable) {
            return $slug;
        }
    }

    private function resolveActiveCollection(Application $application): string
    {
        if (!empty($application->qdrant_collection)) {
            return $application->qdrant_collection;
        }

        // Aucun chat n'a encore jamais pu être posé sur cette app :
        // première résolution/création de collection.
        $collection = $this->resolveQdrantCollection($application);
        $application->update(['qdrant_collection' => $collection]);
        return $collection;
    }

    private function listFaqFiles(): array
    {
        $faqDir = $this->getFaqDir();
        if (!is_dir($faqDir)) return [];

        $files  = glob($faqDir . '/*.json') ?: [];
        $result = [];

        foreach ($files as $file) {
            try {
                $slug    = pathinfo($file, PATHINFO_FILENAME);
                $appName = str_replace('_', ' ', $slug);

                $application = Application::whereRaw(
                    'LOWER(REPLACE(REPLACE(name, \' \', \'_\'), \'-\', \'_\')) = ?',
                    [strtolower($slug)]
                )->first();

                $itemCount = $application
                    ? Faq::where('application_id', $application->id)->count()
                    : $this->countItemsInFaqFile($file);

                $manualVersion = null;
                if ($application) {
                    $latestManual = Manual::where('application_id', $application->id)
                        ->where('status', 'indexed')
                        ->latest('created_at')
                        ->first();
                    $manualVersion = $latestManual?->version;
                }

                $result[] = [
                    'slug'       => $slug,
                    'file'       => $file,
                    'app_name'   => $application ? $application->name : ucwords($appName),
                    'app_id'     => $application?->id,
                    'version'    => $manualVersion ?? null,
                    'item_count' => $itemCount,
                    'd_at' => date('d/m/Y', filemtime($file)),
                ];
            } catch (\Throwable $e) {
                Log::warning('[AdminController] Erreur lecture FAQ', [
                    'file'  => $file,
                    'error' => $e->getMessage(),
                ]);
            }
        }

        usort($result, fn($a, $b) => filemtime($b['file']) <=> filemtime($a['file']));
        return $result;
    }

    private function countItemsInFaqFile(string $file): int
    {
        try {
            $data  = json_decode(file_get_contents($file), true) ?: [];
            $items = $data['items'] ?? $data;
            return is_array($items) ? count($items) : 0;
        } catch (\Throwable) {
            return 0;
        }
    }

    // ──────────────────────────────────────────────────────────────────
    // CRUD MANUELS
    // ──────────────────────────────────────────────────────────────────

    public function checkAppVersion(Request $request): JsonResponse
    {
        $appName = trim($request->input('app_name', ''));
        $version = $this->normalizeManualVersion($request->input('version', '1.0'));

        if (!$appName) {
            return response()->json(['exists' => false]);
        }

        $application = Application::whereRaw('LOWER(name) = ?', [strtolower($appName)])->first();
        if ($application) $this->assertOwnsApplication($application);

        if (!$application) {
            return response()->json(['exists' => false]);
        }

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
            'name'                      => ['required', 'string', 'max:255'],
            'app_id'                    => ['nullable', 'integer', 'exists:applications,id'],
            'app_name'                  => ['nullable', 'string', 'max:255'],
            'version'                   => ['nullable', 'string', 'max:20'],
            'follows_internal_template' => ['required', 'boolean'],
            'file'                      => ['required', 'file', 'mimes:pdf', "max:{$maxKb}"],
            'conflict_resolution'       => ['nullable', 'in:complementary,contradictory'],
            'existing_manual_id'        => ['nullable', 'integer', 'exists:manuals,id'],
        ]);

        if ($request->filled('app_id')) {
            $application = Application::findOrFail($request->input('app_id'));
            $this->assertOwnsApplication($application);
            $appName     = $application->name;
        } else {
            $appName     = trim($request->input('app_name'));
            $application = Application::whereRaw('LOWER(name) = ?', [strtolower($appName)])->first();

            if ($application) {
                $this->assertOwnsApplication($application);
            } elseif (!$this->isSuperAdmin() && !$request->boolean('auto_versioned')) {
                // Un sous-admin ne peut créer une appli via texte libre QUE dans le
                // cas précis de la résolution automatique de conflit de version.
                return response()->json([
                    'success' => false,
                    'message' => "Vous ne pouvez ajouter un manuel qu'à une application que vous administrez.",
                ], 403);
            }
        }

        $version                 = $this->normalizeManualVersion($request->input('version', '1.0'));
        $followsInternalTemplate = filter_var($request->input('follows_internal_template'), FILTER_VALIDATE_BOOLEAN);
        $resolution              = $request->input('conflict_resolution');

        // Priorité au select (app_id) : évite les doublons/fautes de frappe
        // qu'un champ texte libre autorisait auparavant.
        if ($request->filled('app_id')) {
            $application = Application::findOrFail($request->input('app_id'));
            $appName     = $application->name;
        } else {
            $appName     = trim($request->input('app_name'));
            $application = Application::whereRaw('LOWER(name) = ?', [strtolower($appName)])->first();
        }

        if ($application) {
            $this->assertOwnsApplication($application);
            if (!$this->isSuperAdmin() && !$application) {
                return response()->json(['success' => false, 'message' => "Vous ne pouvez ajouter un manuel qu'à une application que vous administrez."], 403);
            }
            $sameVersionManual = Manual::where('application_id', $application->id)
                ->whereRaw("LOWER(COALESCE(version, '1.0')) = ?", [strtolower($version)])
                ->first();

            if ($sameVersionManual) {
                return response()->json([
                    'success'  => false,
                    'conflict' => 'same_version',
                    'app_name' => $application->name,
                    'version'  => $version,
                    'message'  => "L'application '{$application->name}' avec la version '{$version}' existe déjà.",
                ], 409);
            }

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

        if ($resolution === 'complementary' && $application) {
            return $this->handleComplementaryManual($request, $appName, $application, $version);
        }

        if (!$application) {
            $application = Application::create(['name' => $appName]);

            // Auto-attache le sous-admin comme propriétaire de cette nouvelle
            // "version" d'application générée automatiquement.
            if (!$this->isSuperAdmin()) {
                $application->update(['admin_id' => auth()->id()]);
                $application->admins()->attach(auth()->id());
            }
        }

        $fileName = $this->buildPdfFileName($request->input('name'));
        $this->storeManualPdf($request, $fileName);

        $manual = Manual::create([
            'name'                      => $request->input('name'),
            'application_id'            => $application->id,
            'version'                   => $version,
            'file_path'                 => $fileName,
            'follows_internal_template' => $followsInternalTemplate,
            'status'                    => 'processing',
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

        $tempDir        = sys_get_temp_dir();
        $tempFileName   = 'new_pdf_' . uniqid() . '.pdf';
        $request->file('file')->move($tempDir, $tempFileName);
        $tempNewPdfPath = $tempDir . '/' . $tempFileName;

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

        $oldCleanedJsonPath      = $existingManual->cleaned_json_path;
        $followsInternalTemplate = filter_var($request->input('follows_internal_template'), FILTER_VALIDATE_BOOLEAN);

        DB::transaction(function () use ($existingManual, $mergedFileName, $newVersion, $followsInternalTemplate) {
            $this->deleteManualPdf($existingManual->file_path);
            $existingManual->update([
                'file_path'                 => $mergedFileName,
                'status'                    => 'processing',
                'processing_error'          => null,
                'cleaned_json_path'         => null,
                'version'                   => $newVersion,
                'follows_internal_template' => $followsInternalTemplate,
            ]);
        });

        if ($oldCleanedJsonPath) {
            $oldCollection = $this->collectionNameFromCleanedPath($oldCleanedJsonPath);
            if ($oldCollection) {
                $this->deleteQdrantCollection($oldCollection);
            }
            $this->deleteJsonFiles($oldCleanedJsonPath);
        }

        ProcessManualPipeline::dispatch($existingManual->id)->afterCommit();

        return response()->json([
            'success' => true,
            'message' => 'PDF fusionné avec succès, réindexation en cours',
            'manual'  => $existingManual->fresh('application'),
        ]);
    }

    public function showManual(int $id): JsonResponse
    {
        $manual = Manual::with('application')->findOrFail($id);
        $this->assertOwnsApplication($manual->application);
        return response()->json(array_merge($manual->toArray(), [
            'app_name'                  => $manual->application->name ?? '',
            'follows_internal_template' => (bool) $manual->follows_internal_template,
        ]));
    }

    public function updateManual(Request $request, int $id): JsonResponse
    {
        $manual = Manual::findOrFail($id);
        $this->assertOwnsApplication($manual->application);
        $maxKb  = (int) config('services.extract.max_upload_kb', 512000);

        $request->validate([
            'name'                      => ['required', 'string', 'max:255'],
            'app_name'                  => ['required', 'string', 'max:255'],
            'version'                   => ['nullable', 'string', 'max:20'],
            'follows_internal_template' => ['required', 'boolean'],
            'file'                      => ['nullable', 'file', 'mimes:pdf', "max:{$maxKb}"],
        ]);

        $appName     = trim($request->input('app_name'));
        $application = Application::whereRaw('LOWER(name) = ?', [strtolower($appName)])->first();

        if ($application) {
            $this->assertOwnsApplication($application);
        } else {
            if (!$this->isSuperAdmin() && !$request->boolean('auto_versioned')) {
                return response()->json([
                    'success' => false,
                    'message' => "Vous ne pouvez pas créer une nouvelle application par ce biais.",
                ], 403);
            }
            $application = Application::create(['name' => $appName]);
            if (!$this->isSuperAdmin()) {
                $application->update(['admin_id' => auth()->id()]);
                $application->admins()->attach(auth()->id());
            }
        }

        $followsInternalTemplate = filter_var($request->input('follows_internal_template'), FILTER_VALIDATE_BOOLEAN);

        $updateData = [
            'name'                      => $request->input('name'),
            'application_id'            => $application->id,
            'version'                   => $request->input('version', $manual->version),
            'follows_internal_template' => $followsInternalTemplate,
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
        $this->assertOwnsApplication($manual->application);

        $extractDir = rtrim((string) config('services.extract.extract_dir', base_path('../../extract/app')), '/');
        $jsonDir    = rtrim((string) config('services.extract.json_dir', $extractDir . '/json'), '/');

        $realExtractDir = realpath($extractDir) ?: $extractDir;
        $realJsonDir    = realpath($jsonDir)    ?: $jsonDir;

        $pdfBaseName = pathinfo($manual->file_path, PATHINFO_FILENAME);

        if ($manual->cleaned_json_path) {
            $this->deleteJsonFiles($manual->cleaned_json_path);
        } else {
            $this->deleteJsonFilesByPdfName($manual->file_path);
        }

        if ($pdfBaseName) {
            $imagesPath    = $realJsonDir . '/images/' . $pdfBaseName;
            $imagesPathAlt = $jsonDir . '/images/' . $pdfBaseName;

            if (is_dir($imagesPath)) {
                $this->deleteDirectory($imagesPath);
            } elseif (is_dir($imagesPathAlt)) {
                $this->deleteDirectory($imagesPathAlt);
            } else {
                Log::info('[AdminController] Dossier images introuvable', ['tried' => [$imagesPath, $imagesPathAlt]]);
            }

            $this->deleteExtractLogs($realExtractDir, $pdfBaseName);
        }

        $this->deleteManualPdf($manual->file_path);

        // IMPORTANT : on détache les messages du manuel AVANT de le supprimer,
        // pour empêcher une éventuelle contrainte FK "ON DELETE CASCADE" en base
        // de données de supprimer silencieusement les discussions liées.
        // Les messages/conversations restent intacts, seule la référence
        // manual_id est retirée.
        Message::where('manual_id', $manual->id)->update(['manual_id' => null]);

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

    public function faqUpload(Request $request): JsonResponse
    {
        $request->validate([
            'app_id'   => ['nullable', 'integer'],
            'app_name' => ['nullable', 'string', 'max:255'],
            'file'     => ['required', 'file', 'mimes:json,txt'],
        ]);

        $appId        = trim((string) $request->input('app_id', ''));
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
            $appName = $application->name;
        } else {
            $appName = $appNameInput;
        }


        $application = $this->findOrCreateApplication($appName);
        $this->assertOwnsApplication($application);
        $slug        = $this->appNameToFaqSlug($appName);

        // Collection déjà active (si un chat a déjà pu répondre, elle existe déjà)
        $collectionName = $this->resolveActiveCollection($application);

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

        $imported = Faq::syncFromJson($application->id, $items, 'admin');

        $faqFile = $this->getFaqDir() . '/' . $slug . '.json';
        $dbItems = Faq::where('application_id', $application->id)
            ->get()
            ->map(fn($i) => $i->toFaqArray())
            ->values()
            ->all();

        $this->writeFaqFile($faqFile, $dbItems);

        Log::info('[FAQ Upload] Fichier sauvegardé + DB mise à jour', [
            'file'       => $faqFile,
            'imported'   => $imported,
            'app_id'     => $application->id,
            'collection' => $collectionName,
        ]);

        $backendUrl = rtrim((string) config('services.backend.url', 'http://127.0.0.1:8000'), '/');
        try {
            $client   = new \GuzzleHttp\Client(['timeout' => 120]);
            $response = $client->post(
                $backendUrl . '/api/faq/index',
                ['json' => ['collection' => $collectionName, 'items' => $dbItems]]
            );
            $data           = json_decode((string) $response->getBody(), true);
            $realCollection = $data['collection'] ?? $collectionName;
            if ($application->qdrant_collection !== $realCollection) {
                $application->update(['qdrant_collection' => $realCollection]);
                $collectionName = $realCollection;
            }
        } catch (\Throwable $e) {
            Log::warning('[FAQ Upload] Backend inaccessible, dispatch job sync', ['error' => $e->getMessage()]);
            ProcessFaqPipeline::dispatch('sync');
        }

        return response()->json([
            'success'    => true,
            'app_id'     => $application->id,
            'app_name'   => $appName,
            'slug'       => $slug,
            'collection' => $collectionName,
            'file'       => $faqFile,
            'item_count' => $imported,
            'updated_at' => date('d/m/Y', filemtime($faqFile)),
        ]);
    }

    public function faqShow(string $app): JsonResponse
    {
        [$application, $slug, $appName] = $this->resolveFaqApp($app);
        $this->assertOwnsApplication($application);

        $faqFile = $this->getFaqDir() . '/' . $slug . '.json';

        if (file_exists($faqFile)) {
            try {
                $data  = json_decode(file_get_contents($faqFile), true) ?: [];
                $items = $data['items'] ?? $data;
                $items = is_array($items) ? array_values($items) : [];

                return response()->json([
                    'app_id'     => $application?->id ?? $app,
                    'app_name'   => $appName,
                    'slug'       => $slug,
                    'collection' => $application?->qdrant_collection ?? $slug,
                    'faq'        => $items,
                    'item_count' => count($items),
                    'source'     => 'local',
                ]);
            } catch (\Throwable $e) {
                Log::warning('[FAQ Show] Erreur lecture fichier local', ['file' => $faqFile, 'error' => $e->getMessage()]);
            }
        }

        $collection = $application?->qdrant_collection ?? $slug;
        $backendUrl = rtrim((string) config('services.backend.url', 'http://127.0.0.1:8000'), '/');
        $url        = $backendUrl . '/api/admin/faq/' . urlencode($collection);

        try {
            $client   = new \GuzzleHttp\Client(['timeout' => 30]);
            $response = $client->get($url);
            $data     = json_decode((string) $response->getBody(), true);
            $items    = $data['faq'] ?? $data['items'] ?? [];

            if (is_array($items) && count($items) > 0) {
                $this->writeFaqFile($faqFile, $items);
            }

            return response()->json([
                'app_id'     => $application?->id ?? $app,
                'app_name'   => $appName,
                'slug'       => $slug,
                'collection' => $collection,
                'faq'        => is_array($items) ? $items : [],
                'item_count' => is_array($items) ? count($items) : 0,
                'source'     => 'backend',
            ]);
        } catch (\Exception $e) {
            Log::info('[FAQ Show] Aucune FAQ trouvée', ['app' => $app, 'error' => $e->getMessage()]);
            return response()->json([
                'app_id'     => $application?->id ?? $app,
                'app_name'   => $appName,
                'slug'       => $slug,
                'collection' => $collection ?? $slug,
                'faq'        => [],
                'item_count' => 0,
                'source'     => 'empty',
            ]);
        }
    }

    public function faqUpdate(Request $request, string $app): JsonResponse
    {
        $request->validate([
            'items' => ['required', 'array'],
        ]);

        $items = $request->input('items');
        [$application, $slug] = $this->resolveFaqApp($app);
        $this->assertOwnsApplication($application);

        if (!$application) {
            return response()->json(['success' => false, 'error' => 'Application introuvable.'], 404);
        }

        Faq::where('application_id', $application->id)->delete();
        $imported = Faq::syncFromJson($application->id, $items, 'admin');

        $faqFile = $this->getFaqDir() . '/' . $slug . '.json';
        $dbItems = Faq::where('application_id', $application->id)
            ->get()
            ->map(fn($i) => $i->toFaqArray())
            ->values()
            ->all();

        $this->writeFaqFile($faqFile, $dbItems);

        Log::info('[FAQ Update] Fichier local mis à jour', ['file' => $faqFile, 'item_count' => $imported]);

        ProcessFaqPipeline::dispatch('sync');

        return response()->json([
            'success'    => true,
            'item_count' => $imported,
            'slug'       => $slug,
            'collection' => $application->qdrant_collection ?? $slug,
        ]);
    }

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
            $this->assertOwnsApplication($application);

            $newSlug = $this->appNameToFaqSlug($newAppName);

            if (strtolower($newAppName) !== strtolower($oldAppName)) {
                $conflict = Application::whereRaw('LOWER(name) = ?', [strtolower($newAppName)])
                    ->when($application, fn($q) => $q->where('id', '!=', $application->id))
                    ->first();

                if ($conflict) {
                    return response()->json([
                        'success' => false,
                        'error'   => "Le nom d'application '{$newAppName}' est déjà utilisé.",
                    ], 409);
                }
            }

            if ($application) {
                $application->update(['name' => $newAppName]);
            } else {
                $application = Application::create(['name' => $newAppName]);
            }

            $faqDir  = $this->getFaqDir();
            $oldFile = $faqDir . '/' . $oldSlug . '.json';
            $newFile = $faqDir . '/' . $newSlug . '.json';

            if ($oldSlug !== $newSlug && file_exists($oldFile)) {
                try {
                    rename($oldFile, $newFile);
                } catch (\Throwable $e) {
                    Log::warning('[FAQ Update Infos] Impossible de renommer le fichier', [
                        'error' => $e->getMessage(), 'old' => $oldFile, 'new' => $newFile,
                    ]);
                }
            }

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

    public function faqIndex(string $app): JsonResponse
    {
        [$application, $slug] = $this->resolveFaqApp($app);
        $this->assertOwnsApplication($application);
        ProcessFaqPipeline::dispatch('sync');
        return response()->json([
            'success'    => true,
            'collection' => $application?->qdrant_collection ?? $slug,
        ]);
    }

    public function faqDestroy(string $app): JsonResponse
    {
        [$application, $slug] = $this->resolveFaqApp($app);
        $this->assertOwnsApplication($application);

        $faqFile = $this->getFaqDir() . '/' . $slug . '.json';
        $deleted = file_exists($faqFile) ? @unlink($faqFile) : false;

        if (!$deleted) {
            return response()->json(['success' => false, 'error' => 'FAQ introuvable'], 404);
        }

        // On supprime UNIQUEMENT le document FAQ (fichier JSON + entrées DB).
        // On NE supprime PAS la collection Qdrant ni l'application, et on ne
        // vérifie plus s'il s'agit du dernier document pour archiver l'app :
        // cela reste géré séparément via la suppression d'application.
        if ($application) {
            Faq::where('application_id', $application->id)->delete();
        }

        ProcessFaqPipeline::dispatch('sync');

        return response()->json(['success' => true, 'slug' => $slug]);
    }

    // ──────────────────────────────────────────────────────────────────
    // CHATS ANONYMISÉS
    // ──────────────────────────────────────────────────────────────────

    public function chatsShow(string $app): JsonResponse
    {
        $application = $this->resolveApplication($app);
        $this->assertOwnsApplication($application);

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
                        if (str_contains($lowerAnswer, $phrase)) {
                            $excluded = true;
                            break;
                        }
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

    public function chatReject(string $app, int $messageId): JsonResponse
    {
        try {
            $message      = Message::findOrFail($messageId);
            $conversation = Conversation::findOrFail($message->conversation_id);
            $application  = $this->resolveApplication($app);
            $this->assertOwnsApplication($application);

            if (!$application || $conversation->application_id !== $application->id) {
                return response()->json(['success' => false, 'error' => 'Message non trouvé pour cette application'], 404);
            }

            $message->update(['faq_status' => 'rejected']);

            return response()->json(['success' => true, 'message' => 'Réponse rejetée']);
        } catch (\Throwable $e) {
            Log::error('[Chat Reject] Erreur', ['error' => $e->getMessage(), 'message_id' => $messageId]);
            return response()->json(['success' => false, 'error' => $e->getMessage()], 500);
        }
    }

    public function chatValidate(Request $request, string $app): JsonResponse
    {
        $request->validate([
            'question'             => ['required', 'string', 'min:5'],
            'answer'               => ['required', 'string', 'min:10'],
            'assistant_message_id' => ['nullable', 'integer'],
            'ticket_id'            => ['nullable', 'integer'],
        ]);

        $question           = trim($request->input('question'));
        $answer             = trim($request->input('answer'));
        $assistantMessageId = $request->input('assistant_message_id');
        $ticketId           = $request->input('ticket_id');
        $source             = $ticketId ? 'glpi' : 'chatbot';

        $application = $this->resolveApplication($app);
        $this->assertOwnsApplication($application);
        if (!$application) {
            $application = $this->findOrCreateApplication($app);
        }

        $appName = $application->name;
        $slug    = $this->appNameToFaqSlug($appName);

        // ── Vérification doublon ──────────────────────────────────────
        $duplicate = Faq::where('application_id', $application->id)
            ->whereRaw('LOWER(problem) = ?', [mb_strtolower($question)])
            ->exists();

        if ($duplicate) {
            return response()->json(['success' => false, 'error' => 'Cette question existe déjà dans la FAQ.'], 422);
        }

        // ── Persistance en base ───────────────────────────────────────
        Faq::create([
            'application_id' => $application->id,
            'problem'        => $question,
            'answer'         => $answer,
            'source_type'    => 'faq',
            'source'         => $source,
        ]);

        // ── Écriture fichier JSON FAQ ─────────────────────────────────
        $faqDir   = $this->getFaqDir();
        $faqFile  = $faqDir . '/' . $slug . '.json';
        $isNewFaq = !file_exists($faqFile);

        $dbItems = Faq::where('application_id', $application->id)
            ->get()
            ->map(fn($i) => $i->toFaqArray())
            ->values()
            ->all();

        $this->writeFaqFile($faqFile, $dbItems);

        // ── Version du dernier manuel indexé ─────────────────────────
        $latestManual  = Manual::where('application_id', $application->id)
            ->where('status', 'indexed')
            ->latest('created_at')
            ->first();
        $manualVersion = $latestManual?->version;

        // ── Mise à jour du statut du message assistant ────────────────
        if ($assistantMessageId) {
            try {
                $am = Message::find($assistantMessageId);
                if ($am) $am->update(['faq_status' => 'validated']);
            } catch (\Throwable $e) {
                Log::warning('[Chat Validate] Impossible de mettre à jour le statut', ['error' => $e->getMessage()]);
            }
        }

        $backendUrl = rtrim((string) config('services.backend.url', 'http://127.0.0.1:8000'), '/');

        $collection = $this->resolveActiveCollection($application);

        Log::info('[Chat Validate] Indexation FAQ', [
            'app_id'     => $application->id,
            'app_name'   => $appName,
            'collection' => $collection,
        ]);

        try {
            $client   = new \GuzzleHttp\Client(['timeout' => 120]);
            // On envoie la collection EXACTE au backend — il ne doit pas
            // recalculer de slug, il doit upsert dans cette collection précise.
            $response = $client->post(
                $backendUrl . '/api/faq/index',
                ['json' => ['collection' => $collection, 'items' => $dbItems]]
            );
            $data = json_decode((string) $response->getBody(), true);

            $realCollection = $data['collection'] ?? $collection;
            if ($application->qdrant_collection !== $realCollection) {
                $application->update(['qdrant_collection' => $realCollection]);
            }
            $collection = $realCollection;

            ProcessFaqPipeline::dispatch('sync');

            return response()->json([
                'success'    => true,
                'data'       => $data,
                'item_count' => count($dbItems),
                'slug'       => $slug,
                'app_name'   => $appName,
                'app_id'     => $application->id,
                'collection' => $collection,
                'version'    => $manualVersion,
                'is_new_faq' => $isNewFaq,
                'updated_at' => date('d/m/Y', filemtime($faqFile)),
            ]);
        } catch (\Exception $e) {
            Log::warning('[Chat Validate] Backend inaccessible', ['error' => $e->getMessage()]);
            ProcessFaqPipeline::dispatch('sync');

            return response()->json([
                'success'         => true,
                'backend_warning' => $e->getMessage(),
                'item_count'      => count($dbItems),
                'slug'            => $slug,
                'app_name'        => $appName,
                'app_id'          => $application->id,
                'collection'      => $collection,
                'version'         => $manualVersion,
                'is_new_faq'      => $isNewFaq,
                'updated_at'      => date('d/m/Y', filemtime($faqFile)),
            ]);
        }
    }

    // ──────────────────────────────────────────────────────────────────
    // HELPERS RÉSOLUTION D'APPLICATION
    // ──────────────────────────────────────────────────────────────────

    private function resolveApplication(string $app): ?Application
    {
        if (is_numeric($app)) {
            return Application::find((int) $app);
        }
        $slug = $this->appNameToFaqSlug($app);
        return Application::whereRaw('LOWER(name) = ?', [strtolower($app)])->first()
            ?? Application::whereRaw(
                'LOWER(REPLACE(REPLACE(name, \' \', \'_\'), \'-\', \'_\')) = ?',
                [strtolower($slug)]
            )->first();
    }

    private function resolveFaqApp(string $app): array
    {
        $application = $this->resolveApplication($app);
        $appName     = $application?->name ?? $app;
        $slug        = $this->appNameToFaqSlug($appName);
        return [$application, $slug, $appName];
    }

    private function findOrCreateApplication(string $name): Application
    {
        $existing = Application::whereRaw('LOWER(name) = ?', [strtolower($name)])->first();
        if ($existing) {
            return $existing;
        }
        Log::info('[findOrCreateApplication] Création nouvelle application', ['name' => $name]);
        return Application::create(['name' => $name]);
    }


    private function isSuperAdmin(): bool
    {
        return auth()->user()->admin_type === 'super';
    }

    private function ownedApplicationIds(): array
    {
        return auth()->user()->adminApplications()->pluck('applications.id')->toArray();
    }

    private function assertOwnsApplication(?Application $application): void
    {
        if ($this->isSuperAdmin()) return;

        if (!$application || !in_array($application->id, $this->ownedApplicationIds(), true)) {
            abort(403, "Vous n'êtes pas autorisé à gérer cette application.");
        }
    }
    private function cleanupApplicationIfEmpty(int $applicationId): void
    {
        $app = Application::find($applicationId);
        if (!$app) return;

        $hasManuals = Manual::where('application_id', $applicationId)->exists();
        $hasFaqs    = Faq::where('application_id', $applicationId)->exists();

        if (!$hasManuals && !$hasFaqs && !$app->archived) {
            // On archive au lieu de supprimer : les conversations restent
            // en base pour garder la traçabilité (preuve question/réponse).
            $app->admins()->detach();
            $app->allowedUsers()->detach();
            $app->update(['archived' => true, 'archived_at' => now()]);

            Log::info('[AdminController] Application archivée (plus de contenu)', [
                'app_id'   => $applicationId,
                'app_name' => $app->name,
            ]);
        }
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
        $extractDir  = rtrim((string) config('services.extract.extract_dir', base_path('../../extract/app')), '/');
        $jsonDir     = rtrim((string) config('services.extract.json_dir', $extractDir . '/json'), '/');
        $realJsonDir = realpath($jsonDir) ?: $jsonDir;
        $baseName    = pathinfo($pdfFileName, PATHINFO_FILENAME);

        $this->deleteFile($realJsonDir . '/' . $baseName . '_2levels.json');
        $this->deleteFile($realJsonDir . '/' . $baseName . '_2levels_cleaned.json');
        foreach (glob($realJsonDir . '/' . $baseName . '*.json') ?: [] as $f) {
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
            Log::info('[AdminController] Qdrant DELETE collection', [
                'collection' => $collectionName,
                'result'     => $data['result'] ?? null,
            ]);
        } catch (\Exception $e) {
            Log::warning("[AdminController] Qdrant '{$collectionName}': " . $e->getMessage());
        }
    }

    private function deleteQdrantCollectionData(string $collection): void
    {
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

    private function deleteExtractLogs(string $extractDir, string $baseName): void
    {
        $extractLogsDir = rtrim($extractDir . '/logs/extractor', '/');
        if (is_dir($extractLogsDir)) {
            foreach (glob($extractLogsDir . '/' . $baseName . '*.log') ?: [] as $f) {
                $this->deleteFile($f);
            }
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
        if (!$path) return;

        $realPath   = realpath($path);
        $targetPath = $realPath ?: $path;

        if (!is_dir($targetPath)) {
            Log::info('[AdminController] Dossier déjà absent ou introuvable', ['path' => $path, 'real' => $realPath ?: 'non résolu']);
            return;
        }

        $iterator = new \RecursiveIteratorIterator(
            new \RecursiveDirectoryIterator($targetPath, \RecursiveDirectoryIterator::SKIP_DOTS),
            \RecursiveIteratorIterator::CHILD_FIRST
        );
        foreach ($iterator as $file) {
            if ($file->isDir()) {
                @rmdir($file->getRealPath());
            } else {
                @unlink($file->getRealPath());
            }
        }

        $result = @rmdir($targetPath);

        Log::info('[AdminController] Dossier supprimé', [
            'path'    => $path,
            'real'    => $targetPath,
            'success' => $result,
        ]);
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
        $safe       = Str::of($adminName)
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

        $command = sprintf(
            'python3 %s %s %s %s 2>&1',
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

    // ─────────��─────────────────────────────────────────────────────���──
    // ADMIN MANAGEMENT
    // ──────────────────────────────────────────────────────────────────

    public function getAdmins(): JsonResponse
    {
        $admins = User::where('is_admin', true)
            ->whereIn('admin_type', ['super', 'app'])
            ->get()
            ->map(function ($u) {
                return [
                    'id' => $u->id,
                    'name' => $u->name,
                    'email' => $u->email,
                    'department' => $u->department,
                    'admin_type' => $u->admin_type,
                    'applications_count' => $u->adminApplications()->count(),
                ];
            });
        return response()->json(['admins' => $admins]);
    }

    public function addAdmin(Request $request): JsonResponse
    {
        $request->validate(['user_id' => ['required', 'integer', 'exists:users,id']]);
        $user = User::findOrFail($request->input('user_id'));

        if ($user->is_admin) {
            return response()->json(['success' => false, 'message' => 'Cet utilisateur est déjà administrateur.'], 422);
        }

        $user->update(['is_admin' => true, 'admin_type' => 'app']);

        return response()->json([
            'success' => true,
            'admin' => [
                'id' => $user->id,
                'name' => $user->name,
                'email' => $user->email,
                'department' => $user->department,
                'admin_type' => $user->admin_type,
                'applications_count' => 0,
            ],
        ]);
    }

    public function removeAdmin(int $userId): JsonResponse
    {
        $user = User::findOrFail($userId);

        if (!$user->is_admin) {
            return response()->json(['success' => false, 'message' => 'Cet utilisateur n\'est pas administrateur.'], 422);
        }

        $user->adminApplications()->detach();
        $user->update(['is_admin' => false, 'admin_type' => 'user']);

        return response()->json(['success' => true]);
    }

    public function getAvailableUsers(Request $request): JsonResponse
    {

        $query = User::query();

        if ($request->has('admin')) {
            $query->where('is_admin', $request->boolean('admin'));
        }

        if ($request->filled('department')) {
            $query->where('department', $request->input('department'));
        }

        $users = $query
            ->orderBy('name')
            ->get(['id', 'name', 'email', 'department', 'is_admin']);

        return response()->json(['users' => $users]);
    }

    public function getDepartments(): JsonResponse
    {
        $departments = User::whereNotNull('department')
            ->distinct()
            ->pluck('department')
            ->sort()
            ->values();

        return response()->json(['departments' => $departments]);
    }

    // ──────────────────────────────────────────────────────────────────
    // APPLICATION MANAGEMENT
    // ──────────────────────────────────────────────────────────────────

    public function getApplications(): JsonResponse
    {
        $query = Application::with(['admin', 'admins', 'allowedUsers']);

        if (!$this->isSuperAdmin()) {
            $query->whereIn('id', $this->ownedApplicationIds());
        }

        $apps = $query->get()->map(function ($app) {
            return [
                'id' => $app->id,
                'name' => $app->name,
                'department' => $app->department,
                'admin' => $app->admin ? ['id' => $app->admin->id, 'name' => $app->admin->name] : null,
                'admins_count' => $app->admins()->count(),
                'users_count' => $app->allowedUsers()->count(),
                'manuals_count' => Manual::where('application_id', $app->id)->count(),
                'faq_count' => Faq::where('application_id', $app->id)->count(),
                'color' => $app->color ?? '#F26522',
                'archived' => (bool) $app->archived,
            ];
        });

        return response()->json(['applications' => $apps]);
    }

    public function storeApplication(Request $request): JsonResponse
    {
        $request->validate([
            'name' => ['required', 'string', 'max:255', 'unique:applications,name'],
            'version' => ['nullable', 'string', 'max:20'],
            'admin_id' => ['required', 'integer', 'exists:users,id'],
            'admin_ids' => ['nullable', 'array'],
            'department' => ['nullable', 'string', 'max:255'],
            'user_ids' => ['nullable', 'array'],
            'all_department_users' => ['boolean'],
        ]);

        $primaryAdmin = User::findOrFail($request->input('admin_id'));
        if (!$primaryAdmin->is_admin) {
            return response()->json(['success' => false, 'message' => 'L\'utilisateur doit être administrateur.'], 422);
        }

        $app = Application::create([
            'name' => $request->input('name'),
            'admin_id' => $primaryAdmin->id,
            'department' => $request->input('department'),
        ]);

        // Attach all admins (or just the primary if admin_ids is not provided)
        $adminIds = $request->input('admin_ids') ?: [$primaryAdmin->id];
        $adminIds = array_filter(array_unique(array_map('intval', $adminIds)));

        if (!empty($adminIds)) {
            // Validate all admins exist and are actually admins
            $validAdmins = User::whereIn('id', $adminIds)->where('is_admin', true)->pluck('id')->toArray();
            if (count($validAdmins) === 0) {
                $app->delete();
                return response()->json(['success' => false, 'message' => 'Au moins un administrateur valide doit être sélectionné.'], 422);
            }
            $app->admins()->attach($validAdmins);
        } else {
            $app->admins()->attach($primaryAdmin->id);
        }

        if ($request->boolean('all_department_users') && $request->input('department')) {
            $deptUsers = User::where('department', $request->input('department'))->pluck('id');
            $app->allowedUsers()->attach($deptUsers);
        } elseif ($request->input('user_ids')) {
            $app->allowedUsers()->attach($request->input('user_ids'));
        }

        return response()->json([
            'success' => true,
            'app' => [
                'id' => $app->id,
                'name' => $app->name,
                'department' => $app->department,
                'admin' => ['id' => $primaryAdmin->id, 'name' => $primaryAdmin->name],
                'admins_count' => $app->admins()->count(),
                'users_count' => $app->allowedUsers()->count(),
                'manuals_count' => 0,
                'faq_count' => 0,
                'color' => '#F26522',
            ],
        ]);
    }

    /**
     * Retourne les détails d'une application pour préremplir le modal
     * d'édition (admins actuels, users autorisés, département).
     */
    public function showApplication(int $appId): JsonResponse
    {
        $app = Application::with(['admins', 'allowedUsers'])->findOrFail($appId);

        return response()->json([
            'id'         => $app->id,
            'name'       => $app->name,
            'department' => $app->department,
            'admin_ids'  => $app->admins()->pluck('users.id'),
            'user_ids'   => $app->allowedUsers()->pluck('users.id'),
        ]);
    }

    public function updateApplication(Request $request, int $appId): JsonResponse
    {
        $app = Application::findOrFail($appId);

        $request->validate([
            'name'                  => ['required', 'string', 'max:255', 'unique:applications,name,' . $appId],
            'admin_ids'             => ['required', 'array', 'min:1'],
            'admin_ids.*'           => ['integer', 'exists:users,id'],
            'department'            => ['nullable', 'string', 'max:255'],
            'user_ids'              => ['nullable', 'array'],
            'all_department_users'  => ['boolean'],
        ]);

        $adminIds    = array_filter(array_unique(array_map('intval', $request->input('admin_ids'))));
        $validAdmins = User::whereIn('id', $adminIds)->where('is_admin', true)->pluck('id')->toArray();

        if (empty($validAdmins)) {
            return response()->json(['success' => false, 'message' => 'Au moins un administrateur valide doit être sélectionné.'], 422);
        }

        $app->update([
            'name'       => $request->input('name'),
            'department' => $request->input('department'),
            'admin_id'   => $validAdmins[0], // propriétaire principal historique
        ]);

        $app->admins()->sync($validAdmins);

        if ($request->boolean('all_department_users') && $request->input('department')) {
            $deptUsers = User::where('department', $request->input('department'))->pluck('id');
            $app->allowedUsers()->sync($deptUsers);
        } elseif ($request->input('user_ids')) {
            $app->allowedUsers()->sync($request->input('user_ids'));
        }

        return response()->json(['success' => true, 'message' => 'Application mise à jour avec succès.']);
    }

    public function destroyApplication(int $appId): JsonResponse
    {
        $app = Application::findOrFail($appId);

        // 1) Manuels : chaque destroyManual() gère déjà sa propre collection
        //    Qdrant (_2levels_cleaned), ses fichiers JSON, ses images et son PDF.
        Manual::where('application_id', $appId)->get()->each(function ($manual) {
            $this->destroyManual($manual->id);
        });

        // 2) FAQ : supprimer le fichier .json sur disque + la collection Qdrant
        //    dédiée à la FAQ, SEULEMENT si l'app n'a plus de manuel actif
        //    (sinon la collection Qdrant du manuel a peut-être déjà été
        //    supprimée à l'étape 1, et il ne faut pas la re-résoudre).
        $slug    = $this->appNameToFaqSlug($app->name);
        $faqFile = $this->getFaqDir() . '/' . $slug . '.json';

        if (Faq::where('application_id', $appId)->exists() || file_exists($faqFile)) {
            $stillHasManuals = Manual::where('application_id', $appId)->exists();

            if (!$stillHasManuals) {
                $collection = $app->qdrant_collection ?? $slug;
                if ($collection) {
                    $this->deleteQdrantCollection($collection);
                    $this->deleteQdrantCollectionData($collection);
                }
            }

            if (file_exists($faqFile)) {
                @unlink($faqFile);
                Log::info('[AdminController] Fichier FAQ supprimé', ['file' => $faqFile]);
            }

            Faq::where('application_id', $appId)->delete();
        }
        // 3) On NE supprime PLUS les conversations/messages : ils sont
        //    conservés et l'application est archivée pour garder la preuve
        //    des échanges (protection employeur + traçabilité chatbot).

        // 4) Relations d'admin (l'app archivée ne doit plus être gérable)
        $app->admins()->detach();
        $app->allowedUsers()->detach();
        $app->update(['archived' => true, 'archived_at' => now()]);

        // 5) Réindexation globale FAQ pour purger toute référence résiduelle
        ProcessFaqPipeline::dispatch('sync');

        return response()->json([
            'success' => true,
            'message' => 'Application archivée. Les conversations existantes restent consultables en lecture seule pour les utilisateurs.',
        ]);

        // 5) Réindexation globale FAQ pour purger toute référence résiduelle
        ProcessFaqPipeline::dispatch('sync');

        return response()->json(['success' => true, 'message' => 'Application supprimée avec succès.']);
    }

    public function getApplicationUsers(int $appId): JsonResponse
    {
        $app = Application::findOrFail($appId);
        $users = $app->allowedUsers()->get(['users.id', 'users.name', 'users.email', 'users.department']);

        return response()->json(['users' => $users]);
    }

    public function addApplicationUser(Request $request, int $appId): JsonResponse
    {
        $app = Application::findOrFail($appId);

        $request->validate([
            'user_ids' => ['required', 'array'],
            'user_ids.*' => ['integer', 'exists:users,id'],
        ]);

        $app->allowedUsers()->attach($request->input('user_ids'));

        return response()->json(['success' => true]);
    }

    public function removeApplicationUser(int $appId, int $userId): JsonResponse
    {
        $app = Application::findOrFail($appId);
        $app->allowedUsers()->detach($userId);

        return response()->json(['success' => true]);
    }

    public function adminDashboard()
    {
        $user = auth()->user();
        if ($user->admin_type === 'super') {
            return $this->index();
        }
        if (!$user->is_admin || $user->admin_type !== 'app') {
            return redirect()->route('chat.index');
        }

        $adminApplications = $user->adminApplications()->get();

        if ($adminApplications->isEmpty()) {
            return view('admin.app-dashboard', [
                'stats' => [
                    'requests_total'      => 0,
                    'requests_today'      => 0,
                    'requests_today_pct'  => 0,
                    'requests_by_hour'    => array_fill(0, 24, 0),
                    'hour_max'            => 1,
                    'requests_by_app'     => collect(),
                    'requests_by_dept'    => collect(),
                    'tickets_total'       => 0,
                    'tickets_open'        => 0,
                    'tickets_closed'      => 0,
                    'tickets_by_priority' => collect(),
                    'tickets_by_app'      => collect(),
                    'tickets_by_dept'     => collect(),
                    'manuals_count'       => 0,
                    'manuals_indexed'     => 0,
                    'manuals_processing'  => 0,
                    'manuals_failed'      => 0,
                    'admin_applications'  => 0,
                ],
                'adminApplications'  => collect(),
                'applications'       => collect(),
                'activeApplications' => collect(),
                'users'              => collect(),
                'manuals'            => Manual::whereRaw('1 = 0')->paginate(20),
                'tickets'            => Ticket::whereRaw('1 = 0')->paginate(20),
                'faqList'            => [],
            ]);
        }

        $appIds = $adminApplications->pluck('id');

        $totalRequests = Message::query()
            ->join('conversations', 'messages.conversation_id', '=', 'conversations.id')
            ->whereIn('conversations.application_id', $appIds)
            ->where('messages.role', 'user')
            ->count();

        $requestsToday = Message::query()
            ->join('conversations', 'messages.conversation_id', '=', 'conversations.id')
            ->whereIn('conversations.application_id', $appIds)
            ->where('messages.role', 'user')
            ->whereDate('messages.created_at', today())
            ->count();
        $dayAvg           = $totalRequests > 0 ? max(1, $totalRequests / 30) : 1;
        $requestsTodayPct = min(100, (int) round(($requestsToday / $dayAvg) * 100));

        $requestsByHourRaw = Message::query()
            ->join('conversations', 'messages.conversation_id', '=', 'conversations.id')
            ->whereIn('conversations.application_id', $appIds)
            ->where('messages.role', 'user')
            ->whereDate('messages.created_at', today())
            ->selectRaw('EXTRACT(HOUR FROM messages.created_at)::int as hour, count(*) as total')
            ->groupBy('hour')
            ->orderBy('hour')
            ->pluck('total', 'hour');

        $requestsByHour = [];
        for ($h = 0; $h < 24; $h++) {
            $requestsByHour[$h] = $requestsByHourRaw[$h] ?? 0;
        }
        $hourMax = max(1, max($requestsByHour));

        $requestsByApp = Message::query()
            ->join('conversations', 'messages.conversation_id', '=', 'conversations.id')
            ->join('applications', 'conversations.application_id', '=', 'applications.id')
            ->whereIn('conversations.application_id', $appIds)
            ->where('messages.role', 'user')
            ->selectRaw('applications.name as app_name, count(*) as total')
            ->groupBy('applications.name')
            ->orderByDesc('total')
            ->get()
            ->map(function ($row) use ($totalRequests) {
                $row->percentage = $totalRequests > 0 ? (int) round(($row->total / $totalRequests) * 100) : 0;
                return $row;
            });

        $requestsByDept = Message::query()
            ->join('conversations', 'messages.conversation_id', '=', 'conversations.id')
            ->join('users', 'conversations.user_id', '=', 'users.id')
            ->whereIn('conversations.application_id', $appIds)
            ->where('messages.role', 'user')
            ->whereNotNull('users.department')
            ->selectRaw('users.department, count(*) as total')
            ->groupBy('users.department')
            ->orderByDesc('total')
            ->get()
            ->map(function ($row) use ($totalRequests) {
                $row->percentage = $totalRequests > 0 ? (int) round(($row->total / $totalRequests) * 100) : 0;
                return $row;
            });

        $manualsQuery = Manual::with('application')->whereIn('application_id', $appIds);
        $totalManuals = (clone $manualsQuery)->count();
        $manualsIndexed = (clone $manualsQuery)->where('status', 'indexed')->count();
        $manualsProcessing = (clone $manualsQuery)->where('status', 'processing')->count();
        $manualsFailed = (clone $manualsQuery)->where('status', 'failed')->count();

        $manuals = $manualsQuery->orderByDesc('created_at')->paginate(20);

        $ticketsQuery = Ticket::query()
            ->join('conversations', 'tickets.conversation_id', '=', 'conversations.id')
            ->whereIn('conversations.application_id', $appIds);

        $totalTickets = (clone $ticketsQuery)->count();

        $tickets = Ticket::query()
            ->join('conversations', 'tickets.conversation_id', '=', 'conversations.id')
            ->whereIn('conversations.application_id', $appIds)
            ->select('tickets.*')
            ->with('user')
            ->orderByDesc('tickets.created_at')
            ->paginate(20);

        $ticketsByPriority = Ticket::query()
            ->join('conversations', 'tickets.conversation_id', '=', 'conversations.id')
            ->whereIn('conversations.application_id', $appIds)
            ->selectRaw('priority, count(*) as total')
            ->groupBy('priority')
            ->orderByDesc('total')
            ->get();

        $closedStatuses = ['Résolu', 'Clos', 'Fermé', 'Solved', 'Closed', 'solved', 'resolved'];
        $ticketsClosed = Ticket::query()
            ->join('conversations', 'tickets.conversation_id', '=', 'conversations.id')
            ->whereIn('conversations.application_id', $appIds)
            ->whereIn('tickets.glpi_status', $closedStatuses)
            ->count();
        $ticketsOpen = $totalTickets - $ticketsClosed;

        $ticketsByPriority = Ticket::query()
            ->join('conversations', 'tickets.conversation_id', '=', 'conversations.id')
            ->whereIn('conversations.application_id', $appIds)
            ->selectRaw('priority, count(*) as total')
            ->groupBy('priority')
            ->orderByDesc('total')
            ->get();

        $ticketsByApp = Ticket::query()
            ->join('conversations', 'tickets.conversation_id', '=', 'conversations.id')
            ->join('applications', 'conversations.application_id', '=', 'applications.id')
            ->whereIn('conversations.application_id', $appIds)
            ->selectRaw('applications.name as app_name, count(*) as total')
            ->groupBy('applications.name')
            ->orderByDesc('total')
            ->get()
            ->map(function ($row) use ($totalTickets) {
                $row->percentage = $totalTickets > 0 ? (int) round(($row->total / $totalTickets) * 100) : 0;
                return $row;
            });

        $ticketsByDept = Ticket::query()
            ->join('users', 'tickets.user_id', '=', 'users.id')
            ->join('conversations', 'tickets.conversation_id', '=', 'conversations.id')
            ->whereIn('conversations.application_id', $appIds)
            ->whereNotNull('users.department')
            ->selectRaw('users.department, count(*) as total')
            ->groupBy('users.department')
            ->orderByDesc('total')
            ->get()
            ->map(function ($row) use ($totalTickets) {
                $row->percentage = $totalTickets > 0 ? (int) round(($row->total / $totalTickets) * 100) : 0;
                return $row;
            });
        $adminApplications = $adminApplications->load('allowedUsers');
        $users = User::whereIn('id', $adminApplications->flatMap->allowedUsers->pluck('id'))->get();
        // Uniquement les apps actives (non archivées) de cet admin, pour les <select>
        $activeApplications = $adminApplications->where('archived', false)->values();

        // FAQ scopée : uniquement les entrées liées aux apps administrées
        $faqList = collect($this->listFaqFiles())
            ->filter(fn($f) => $f['app_id'] && $appIds->contains($f['app_id']))
            ->values()
            ->all();

        $stats = [
            'requests_total'      => $totalRequests,
            'requests_today'      => $requestsToday,
            'tickets_total'       => $totalTickets,
            'manuals_count'       => $totalManuals,
            'manuals_indexed'     => $manualsIndexed,
            'manuals_processing'  => $manualsProcessing,
            'manuals_failed'      => $manualsFailed,
            'admin_applications'  => $adminApplications->count(),
            'tickets_by_priority' => $ticketsByPriority,
            'tickets_open'        => $ticketsOpen,
            'tickets_closed'      => $ticketsClosed,
            'tickets_by_app'      => $ticketsByApp,
            'tickets_by_dept'     => $ticketsByDept,
            'requests_today_pct' => $requestsTodayPct,
            'requests_by_hour'   => $requestsByHour,
            'hour_max'           => $hourMax,
            'requests_by_app'    => $requestsByApp,
            'requests_by_dept'   => $requestsByDept,
        ];

        $applications = $adminApplications; // pour les <select> des modals manuels/FAQ

        return view('admin.app-dashboard', compact(
            'stats', 'adminApplications', 'applications', 'activeApplications', 'users', 'manuals', 'tickets', 'faqList'
        ));
    }}


