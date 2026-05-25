<?php

namespace App\Http\Controllers;

use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class TicketController extends Controller
{
    /**
     * Crée un ticket GLPI via l'API.
     * Tokens stockés en env :
     *   - GLPI_API_TOKEN
     *   - GLPI_APP_TOKEN
     */
    public function create(Request $request): JsonResponse
    {
        $request->validate([
            'title'           => ['required', 'string', 'max:255'],
            'category'        => ['required', 'string', 'in:incident,demande,question'],
            'priority'        => ['required', 'string', 'in:Basse,Moyenne,Haute,Critique'],
            'description'     => ['nullable', 'string'],
            'app_id'          => ['nullable', 'integer'],
            'conversation_id' => ['nullable', 'integer'],
        ]);

        try {
            $apiToken = config('services.glpi.api_token');
            $appToken = config('services.glpi.app_token');
            $glpiUrl  = config('services.glpi.url', 'https://glpi.sonatrach.dz');

            if (!$apiToken || !$appToken) {
                Log::warning('[TicketController] GLPI tokens not configured');
                return response()->json([
                    'success' => false,
                    'message' => 'Configuration GLPI manquante',
                ], 500);
            }

            // Cartographie des priorités GLPI
            $priorityMap = [
                'Basse'    => 5,
                'Moyenne'  => 3,
                'Haute'    => 2,
                'Critique' => 1,
            ];

            $priority = $priorityMap[$request->input('priority')] ?? 3;

            // Cartographie des catégories vers types GLPI
            $typeMap = [
                'incident' => 1,
                'demande'  => 2,
                'question' => 2,
            ];

            $type = $typeMap[$request->input('category')] ?? 2;

            // 1. Obtenir le sessiontoken
            $sessionRes = Http::withHeaders([
                'Content-Type' => 'application/json',
                'App-Token'    => $appToken,
            ])->post("{$glpiUrl}/apirest.php/initSession", [
                'user_token' => $apiToken,
            ]);

            if (!$sessionRes->successful()) {
                Log::error('[TicketController] GLPI session init failed', [
                    'status' => $sessionRes->status(),
                    'body'   => $sessionRes->body(),
                ]);
                return response()->json([
                    'success' => false,
                    'message' => 'Erreur GLPI session',
                ], 500);
            }

            $sessionToken = $sessionRes->json('session_token');

            // 2. Créer le ticket
            $ticketRes = Http::withHeaders([
                'Content-Type'  => 'application/json',
                'App-Token'     => $appToken,
                'Session-Token' => $sessionToken,
            ])->post("{$glpiUrl}/apirest.php/Ticket", [
                'input' => [
                    'name'             => $request->input('title'),
                    'content'          => $request->input('description', 'No description'),
                    'type'             => $type,
                    'priority'         => $priority,
                    'impact'           => 3,
                    'urgency'          => 3,
                    'status'           => 1, // Nouvelle
                    'requesttypes_id'  => 1,
                ],
            ]);

            if (!$ticketRes->successful()) {
                Log::error('[TicketController] GLPI ticket creation failed', [
                    'status' => $ticketRes->status(),
                    'body'   => $ticketRes->body(),
                ]);
                return response()->json([
                    'success' => false,
                    'message' => 'Impossible de créer le ticket GLPI',
                ], 500);
            }

            $ticketData = $ticketRes->json();
            $ticketId = $ticketData['id'] ?? $ticketData[0]['id'] ?? null;

            Log::info('[TicketController] GLPI ticket created', [
                'ticket_id'       => $ticketId,
                'title'           => $request->input('title'),
                'user_id'         => auth()->id(),
                'app_id'          => $request->input('app_id'),
                'conversation_id' => $request->input('conversation_id'),
            ]);

            return response()->json([
                'success'   => true,
                'ticket_id' => $ticketId,
                'message'   => "Ticket #{$ticketId} créé avec succès",
            ]);

        } catch (\Exception $e) {
            Log::error('[TicketController] Exception', [
                'error' => $e->getMessage(),
                'trace' => $e->getTraceAsString(),
            ]);
            return response()->json([
                'success' => false,
                'message' => 'Erreur serveur',
            ], 500);
        }
    }
}



