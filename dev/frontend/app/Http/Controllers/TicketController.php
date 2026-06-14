<?php

namespace App\Http\Controllers;

use App\Models\Application;
use App\Models\Ticket;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Mail;

class TicketController extends Controller
{
    /**
     * Crée un ticket GLPI et le sauvegarde en base.
     * Appelé depuis :
     *   - Le bouton « Créer un ticket » (source = manual)
     *   - La suggestion automatique quand le bot ne peut pas répondre (source = auto_suggestion)
     */
    public function create(Request $request): JsonResponse
    {
        $request->validate([
            'title'                 => ['required', 'string', 'max:255'],
            'category'              => ['required', 'string', 'in:incident,demande,question'],
            'priority'              => ['required', 'string', 'in:Basse,Moyenne,Haute,Critique'],
            'description'           => ['nullable', 'string'],
            'app_id'                => ['nullable', 'integer'],
            'conversation_id'       => ['nullable', 'integer'],
            'unanswerable_question' => ['nullable', 'string'],
            'source'                => ['nullable', 'string', 'in:manual,auto_suggestion'],
        ]);

        try {
            $apiToken = config('services.glpi.api_token');
            $appToken = config('services.glpi.app_token');
            $glpiUrl  = rtrim(config('services.glpi.url', 'http://localhost:8080'), '/');
            $user     = Auth::user();

            // ── Sauvegarde en base avant d'appeler GLPI ───────────────
            $ticket = Ticket::create([
                'user_id'               => $user?->id,
                'conversation_id'       => $request->integer('conversation_id') ?: null,
                'application_id'        => $request->integer('app_id') ?: null,
                'title'                 => $request->input('title'),
                'category'              => $request->input('category'),
                'priority'              => $request->input('priority'),
                'description'           => $request->input('description'),
                'unanswerable_question' => $request->input('unanswerable_question')
                    ?: ($request->input('description') ?: $request->input('title')),
                'source'                => $request->input('source', 'manual'),
                'user_email'            => $user?->email,
                'glpi_status'           => 'new',
            ]);

            // ── Si tokens GLPI non configurés : on sauvegarde sans envoyer ──
            if (!$apiToken || !$appToken) {
                Log::warning('[TicketController] GLPI tokens not configured — ticket saved locally only', [
                    'ticket_id' => $ticket->id,
                ]);
                return response()->json([
                    'success'   => true,
                    'ticket_id' => $ticket->id,
                    'glpi_id'   => null,
                    'message'   => "Ticket #{$ticket->id} enregistré (GLPI non configuré)",
                ]);
            }

            // ── Mapping priorités GLPI (1=très haute, 6=très basse) ────
            $priorityMap = [
                'Critique' => 1,
                'Haute'    => 2,
                'Moyenne'  => 3,
                'Basse'    => 5,
            ];

            // ── Mapping catégories → types GLPI (1=incident, 2=demande) ─
            $typeMap = [
                'incident' => 1,
                'demande'  => 2,
                'question' => 2,
            ];

            $priority = $priorityMap[$request->input('priority')] ?? 3;
            $type     = $typeMap[$request->input('category')] ?? 2;

            // ── Contenu enrichi : ajouter la question si c'est une suggestion ─
            $content = $request->input('description', '');
            if ($request->input('unanswerable_question')) {
                $appName = null;
                if ($request->integer('app_id')) {
                    $app     = Application::find($request->integer('app_id'));
                    $appName = $app?->name;
                }
                $content = "Question posée au chatbot :\n"
                    . $request->input('unanswerable_question')
                    . "\n\nApplication concernée : " . ($appName ?? 'Non précisée')
                    . "\n\nUtilisateur : " . ($user?->display_name ?? $user?->name ?? 'Anonyme')
                    . "\n\nEmail : " . ($user?->email ?? 'Non renseigné')
                    . "\n\n---\n"
                    . $content;
            }

            // ── 1. Ouvrir une session GLPI ────────────────────────────
            $sessionRes = Http::timeout(10)
                ->withHeaders([
                    'Content-Type' => 'application/json',
                    'App-Token'    => $appToken,
                ])
                ->post("{$glpiUrl}/apirest.php/initSession", [
                    'user_token' => $apiToken,
                ]);

            if (!$sessionRes->successful()) {
                Log::error('[TicketController] GLPI session init failed', [
                    'status'    => $sessionRes->status(),
                    'body'      => $sessionRes->body(),
                    'ticket_id' => $ticket->id,
                ]);
                return response()->json([
                    'success'   => true,
                    'ticket_id' => $ticket->id,
                    'glpi_id'   => null,
                    'message'   => "Ticket #{$ticket->id} enregistré — GLPI inaccessible (session)",
                ]);
            }

            $sessionToken = $sessionRes->json('session_token');

            // ── 2. Créer le ticket dans GLPI ──────────────────────────
            $ticketRes = Http::timeout(10)
                ->withHeaders([
                    'Content-Type'  => 'application/json',
                    'App-Token'     => $appToken,
                    'Session-Token' => $sessionToken,
                ])
                ->post("{$glpiUrl}/apirest.php/Ticket", [
                    'input' => [
                        'name'            => $request->input('title'),
                        'content'         => $content ?: 'Aucune description fournie.',
                        'type'            => $type,
                        'priority'        => $priority,
                        'impact'          => 3,
                        'urgency'         => 3,
                        'status'          => 1,   // 1 = Nouveau
                        'requesttypes_id' => 1,
                    ],
                ]);

            // ── 3. Fermer la session GLPI ─────────────────────────────
            Http::timeout(5)
                ->withHeaders([
                    'App-Token'     => $appToken,
                    'Session-Token' => $sessionToken,
                ])
                ->get("{$glpiUrl}/apirest.php/killSession");

            if (!$ticketRes->successful()) {
                Log::error('[TicketController] GLPI ticket creation failed', [
                    'status'    => $ticketRes->status(),
                    'body'      => $ticketRes->body(),
                    'ticket_id' => $ticket->id,
                ]);
                return response()->json([
                    'success'   => true,
                    'ticket_id' => $ticket->id,
                    'glpi_id'   => null,
                    'message'   => "Ticket #{$ticket->id} enregistré — GLPI n'a pas pu créer le ticket",
                ]);
            }

            $glpiData = $ticketRes->json();
            $glpiId   = $glpiData['id'] ?? ($glpiData[0]['id'] ?? null);

            // ── 4. Mettre à jour avec l'ID GLPI ───────────────────────
            $ticket->update([
                'glpi_ticket_id' => $glpiId,
                'glpi_status'    => 'processing',
            ]);

            Log::info('[TicketController] GLPI ticket created', [
                'ticket_id'       => $ticket->id,
                'glpi_ticket_id'  => $glpiId,
                'title'           => $request->input('title'),
                'user_id'         => $user?->id,
                'source'          => $request->input('source', 'manual'),
            ]);

            return response()->json([
                'success'   => true,
                'ticket_id' => $ticket->id,
                'glpi_id'   => $glpiId,
                'message'   => "Ticket #{$glpiId} créé avec succès dans GLPI",
            ]);

        } catch (\Exception $e) {
            Log::error('[TicketController] Exception', [
                'error' => $e->getMessage(),
                'trace' => $e->getTraceAsString(),
            ]);
            return response()->json([
                'success' => false,
                'message' => 'Erreur serveur lors de la création du ticket',
            ], 500);
        }
    }
}
