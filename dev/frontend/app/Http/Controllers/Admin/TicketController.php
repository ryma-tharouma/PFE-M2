<?php

namespace App\Http\Controllers;

use App\Models\Ticket;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

/**
 * TicketController
 *
 * Crée un ticket dans GLPI via son API REST,
 * puis le sauvegarde en base locale pour le suivi admin.
 *
 * Documentation GLPI API : https://glpi-project.org/wp-content/uploads/2018/03/glpi-9.1-api-doc.pdf
 */
class TicketController extends Controller
{
    private const PRIORITY_MAP = [
        'Basse'    => 1,
        'Moyenne'  => 3,
        'Haute'    => 4,
        'Critique' => 5,
    ];

    private const CATEGORY_MAP = [
        'incident' => 1,
        'demande'  => 2,
        'question' => 3,
    ];

    /**
     * POST /ticket/create
     */
    public function create(Request $request): JsonResponse
    {
        $validated = $request->validate([
            'title'       => ['required', 'string', 'max:255'],
            'category'    => ['required', 'string', 'in:incident,demande,question'],
            'priority'    => ['required', 'string', 'in:Basse,Moyenne,Haute,Critique'],
            'description' => ['nullable', 'string', 'max:5000'],
        ]);

        // ── Appel API GLPI ──
        $glpiResult = $this->createGlpiTicket($validated);

        // ── Sauvegarde locale (pour le tableau admin) ──
        $ticket = Ticket::create([
            'user_id'        => Auth::id(),
            'title'          => $validated['title'],
            'category'       => $validated['category'],
            'priority'       => $validated['priority'],
            'description'    => $validated['description'] ?? '',
            'glpi_ticket_id' => $glpiResult['id'] ?? null,
            'glpi_status'    => $glpiResult['status'] ?? 'Envoyé',
        ]);

        return response()->json([
            'success'   => true,
            'ticket_id' => $glpiResult['id'] ?? $ticket->id,
            'message'   => 'Ticket créé avec succès.',
        ]);
    }

    /**
     * Crée un ticket dans GLPI via son API REST.
     * Retourne ['id' => int, 'status' => string] ou [] en cas d'erreur.
     */
    private function createGlpiTicket(array $data): array
    {
        $glpiUrl   = config('services.glpi.url',   'http://glpi.sonatrach.dz');
        $appToken  = config('services.glpi.app_token');
        $userToken = config('services.glpi.user_token');

        if (!$appToken || !$userToken) {
            Log::warning('GLPI : tokens non configurés — ticket non envoyé.');
            return [];
        }

        try {
            // ── 1. Init session GLPI ──
            $sessionResp = Http::withHeaders([
                'App-Token'        => $appToken,
                'Authorization'    => "user_token {$userToken}",
                'Content-Type'     => 'application/json',
            ])->get("{$glpiUrl}/apirest.php/initSession");

            if (!$sessionResp->successful()) {
                Log::error('GLPI initSession failed', ['status' => $sessionResp->status()]);
                return [];
            }

            $sessionToken = $sessionResp->json('session_token');

            // ── 2. Créer le ticket ──
            $ticketResp = Http::withHeaders([
                'App-Token'     => $appToken,
                'Session-Token' => $sessionToken,
                'Content-Type'  => 'application/json',
            ])->post("{$glpiUrl}/apirest.php/Ticket", [
                'input' => [
                    'name'     => $data['title'],
                    'content'  => $data['description'] ?? $data['title'],
                    'priority' => self::PRIORITY_MAP[$data['priority']] ?? 3,
                    'type'     => self::CATEGORY_MAP[$data['category']] ?? 1,
                    // 'itilcategories_id' => 0,  // à configurer selon GLPI
                    // 'requesttypes_id'  => 1,   // 1 = Helpdesk
                ],
            ]);

            // ── 3. Kill session ──
            Http::withHeaders([
                'App-Token'     => $appToken,
                'Session-Token' => $sessionToken,
            ])->get("{$glpiUrl}/apirest.php/killSession");

            if ($ticketResp->successful()) {
                return [
                    'id'     => $ticketResp->json('id'),
                    'status' => 'Nouveau',
                ];
            }

            Log::error('GLPI ticket creation failed', [
                'status' => $ticketResp->status(),
                'body'   => $ticketResp->body(),
            ]);

        } catch (\Exception $e) {
            Log::error('GLPI exception', ['message' => $e->getMessage()]);
        }

        return [];
    }
}