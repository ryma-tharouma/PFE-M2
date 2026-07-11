<?php

namespace App\Http\Controllers;

use App\Models\Faq;
use App\Models\Ticket;
use Illuminate\Http\Request;
use Illuminate\Http\Response;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Mail;

class GlpiWebhookController extends Controller
{
    public function handle(Request $request): Response
    {
        // ── 1. Secret ─────────────────────────────────────────────────
        $expectedSecret = config('services.glpi.webhook_secret');
        if ($expectedSecret) {
            $received = $request->query('secret')
                ?? $request->header('X-Glpi-Signature')
                ?? '';
            if ($received !== $expectedSecret) {
                Log::warning('[GlpiWebhook] Secret invalide', ['ip' => $request->ip()]);
                return response('Unauthorized', 401);
            }
        }

        $payload  = $request->json()->all();
        $event    = $payload['event']    ?? 'update';
        $glpiId   = $payload['items_id'] ?? $payload['ticket_id'] ?? null;
        $solution = $payload['solution'] ?? null;
        $source   = $payload['source']   ?? 'unknown';

        Log::info('[GlpiWebhook] Payload reçu', [
            'glpi_id' => $glpiId,
            'event'   => $event,
            'source'  => $source,
        ]);

        if (!$glpiId) {
            return response('Missing ticket id', 400);
        }

        // ── 2. Retrouver le ticket ────────────────────────────────────
        $ticket = Ticket::where('glpi_ticket_id', $glpiId)->first();

        if (!$ticket) {
            Log::warning('[GlpiWebhook] Ticket introuvable en base', ['glpi_id' => $glpiId]);
            return response('OK', 200);
        }

        // ── 3. DÉJÀ TRAITÉ → on retourne immédiatement sans rien faire
        // Condition : glpi_response existe ET qdrant_indexed = true
        // Le poller verra 'Already processed' et marquera l'ID dans son JSON
        if ($ticket->glpi_response && $ticket->qdrant_indexed) {
            Log::info('[GlpiWebhook] Ticket déjà traité — skip', ['ticket_id' => $ticket->id]);
            return response('Already processed', 200);
        }

        // ── 4. Contenu : depuis le payload sinon appel API GLPI ───────
        if (!$solution) {
            $solution = $this->fetchSolutionFromGlpi($glpiId);
        }

        if (!$solution) {
            Log::warning('[GlpiWebhook] Aucune solution trouvée', ['glpi_id' => $glpiId]);
            return response('No solution yet', 200);
        }

        Log::info('[GlpiWebhook] Solution récupérée', [
            'glpi_id'  => $glpiId,
            'solution' => mb_substr($solution, 0, 100),
        ]);

        // ── 5. Mettre à jour le ticket ────────────────────────────────
        $ticket->update([
            'glpi_response'     => $solution,
            'glpi_status'       => 'solved',
            'glpi_event'        => $event,
            'glpi_responded_at' => now(),
        ]);

        // ── 6. Mail ───────────────────────────────────────────────────
        $mailSent = false;
        if ($ticket->user_email) {
            try {
                Mail::html(
                    $this->buildEmailHtml($ticket, $solution),
                    function ($message) use ($ticket) {
                        $message->to($ticket->user_email)
                            ->subject("Réponse à votre ticket #{$ticket->glpi_ticket_id} — {$ticket->title}");
                    }
                );
                $mailSent = true;
                Log::info('[GlpiWebhook] Mail envoyé', ['to' => $ticket->user_email]);
            } catch (\Exception $e) {
                Log::error('[GlpiWebhook] Erreur mail', ['error' => $e->getMessage()]);
            }
        }

        // ── 7. FAQ + Qdrant ───────────────────────────────────────────
        $qdrantOk = false;
        if ($ticket->application_id) {
            try {
                $qdrantOk = $this->injectIntoFaq($ticket, $solution);
            } catch (\Exception $e) {
                Log::error('[GlpiWebhook] Erreur FAQ', ['error' => $e->getMessage()]);
            }
        }

        // ── 8. Marquer qdrant_indexed TOUJOURS après le premier traitement
        // Même si Qdrant échoue, on marque true pour éviter le spam mail.
        // L'indexation Qdrant peut être refaite manuellement si besoin.
        $ticket->update(['qdrant_indexed' => true]);

        Log::info('[GlpiWebhook] Traitement complet', [
            'ticket_id' => $ticket->id,
            'glpi_id'   => $glpiId,
            'mail_sent' => $mailSent,
            'qdrant'    => $qdrantOk,
        ]);

        return response('OK', 200);
    }

    // ─────────────────────────────────────────────────────────────────

    private function fetchSolutionFromGlpi(int $glpiId): ?string
    {
        $apiToken = config('services.glpi.api_token');
        $appToken = config('services.glpi.app_token');
        $glpiUrl  = rtrim(config('services.glpi.url', 'http://localhost:8080'), '/');

        if (!$apiToken || !$appToken) return null;

        try {
            $sessionRes = Http::timeout(10)
                ->withHeaders(['Content-Type' => 'application/json', 'App-Token' => $appToken])
                ->post("{$glpiUrl}/apirest.php/initSession", ['user_token' => $apiToken]);

            if (!$sessionRes->successful()) return null;

            $sessionToken = $sessionRes->json('session_token');
            $solution     = null;

            // 1. ITILSolution
            $solRes = Http::timeout(10)
                ->withHeaders(['App-Token' => $appToken, 'Session-Token' => $sessionToken])
                ->get("{$glpiUrl}/apirest.php/Ticket/{$glpiId}/ITILSolution");

            if ($solRes->successful() && !empty($solRes->json())) {
                foreach (array_reverse($solRes->json()) as $sol) {
                    $content = $sol['content'] ?? '';
                    if (in_array(trim($content), ['Solution approuvée', 'Solution approved', ''])) continue;
                    $clean = trim(strip_tags(html_entity_decode($content, ENT_QUOTES, 'UTF-8')));
                    if (strlen($clean) > 5) { $solution = $clean; break; }
                }
            }

            // 2. Fallback ITILFollowup
            if (!$solution) {
                $fuRes = Http::timeout(10)
                    ->withHeaders(['App-Token' => $appToken, 'Session-Token' => $sessionToken])
                    ->get("{$glpiUrl}/apirest.php/Ticket/{$glpiId}/ITILFollowup");

                if ($fuRes->successful() && !empty($fuRes->json())) {
                    foreach (array_reverse($fuRes->json()) as $fu) {
                        if (($fu['is_private'] ?? 0) === 1) continue;
                        $content = $fu['content'] ?? '';
                        $clean   = trim(strip_tags(html_entity_decode($content, ENT_QUOTES, 'UTF-8')));
                        if (strlen($clean) > 5) { $solution = $clean; break; }
                    }
                }
            }

            Http::timeout(5)
                ->withHeaders(['App-Token' => $appToken, 'Session-Token' => $sessionToken])
                ->get("{$glpiUrl}/apirest.php/killSession");

            return $solution;

        } catch (\Exception $e) {
            Log::error('[GlpiWebhook] fetchSolution exception', ['error' => $e->getMessage()]);
            return null;
        }
    }

    private function buildEmailHtml(Ticket $ticket, string $solution): string
    {
        $title        = htmlspecialchars($ticket->title);
        $solutionHtml = nl2br(htmlspecialchars($solution));
        $question     = $ticket->unanswerable_question
            ? '<p style="margin:0 0 8px;"><strong>Votre question :</strong></p>'
            . '<p style="margin:0;color:#555;">' . nl2br(htmlspecialchars($ticket->unanswerable_question)) . '</p>'
            : '';

        return <<<HTML
<!DOCTYPE html><html lang="fr">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:30px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.1);">
        <tr><td style="background:#F26522;padding:24px 32px;">
          <h1 style="margin:0;color:#fff;font-size:20px;">Réponse à votre ticket</h1>
          <p style="margin:6px 0 0;color:rgba(255,255,255,.85);font-size:13px;">Assistant IA Sonatrach</p>
        </td></tr>
        <tr><td style="padding:32px;">
          <p style="margin:0 0 16px;color:#666;font-size:13px;">
            Ticket <strong>#{$ticket->glpi_ticket_id}</strong> — {$title}
          </p>
          {$question}
          <div style="margin-top:20px;background:#f9f9f9;border-left:4px solid #F26522;padding:20px 24px;border-radius:4px;">
            <p style="margin:0 0 10px;font-weight:600;color:#333;font-size:14px;">Réponse de notre équipe support :</p>
            <p style="margin:0;color:#444;line-height:1.7;font-size:14px;">{$solutionHtml}</p>
          </div>
          <p style="margin:24px 0 0;font-size:12px;color:#999;">
            Cette réponse a été intégrée à notre base de connaissances automatiquement.
          </p>
        </td></tr>
        <tr><td style="background:#f9f9f9;padding:16px 32px;border-top:1px solid #eee;">
          <p style="margin:0;font-size:11px;color:#aaa;text-align:center;">Sonatrach — Système d'assistance IA</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>
HTML;
    }

    private function injectIntoFaq(Ticket $ticket, string $solution): bool
    {
        $appId   = $ticket->application_id;
        $appName = $ticket->application?->name ?? 'unknown';

        Faq::updateOrCreate(
            ['section_id' => 'glpi_ticket_' . $ticket->glpi_ticket_id],
            [
                'application_id' => $appId,
                'problem'        => $ticket->unanswerable_question ?? $ticket->title,
                'answer'         => $solution,
                'source_type'    => 'faq',
                'source'         => 'glpi_response',
                'title'          => 'Ticket #' . $ticket->glpi_ticket_id,
                'applies_to'     => $appName,
            ]
        );

        $items = Faq::where('application_id', $appId)
            ->get()->map(fn($f) => $f->toFaqArray())->values()->toArray();

        $backendUrl = rtrim(config('services.backend.url', 'http://127.0.0.1:8000'), '/');
        $collection = $ticket->application?->qdrant_collection
            ?? str_replace([' ', '-'], '_', strtolower($appName));

        try {
            $res = Http::timeout(60)->post("{$backendUrl}/api/faq/index", [
                'collection' => $collection,
                'items'      => $items,
            ]);

            if ($res->successful()) {
                Log::info('[GlpiWebhook] FAQ réindexée dans Qdrant', [
                    'collection' => $collection,
                    'items'      => count($items),
                ]);
                return true;
            }
            Log::warning('[GlpiWebhook] Qdrant échoué', ['status' => $res->status(), 'body' => $res->body()]);
            return false;
        } catch (\Exception $e) {
            Log::error('[GlpiWebhook] Qdrant exception', ['error' => $e->getMessage()]);
            return false;
        }
    }
}
