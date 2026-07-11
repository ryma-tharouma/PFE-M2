<?php
$glpiUrl    = 'http://localhost:8080';
$appToken   = 'XY12O6dDRNAXLFyIELY7aiCibxuWIQHAOlFA8Zps';
$userToken  = '5QXljqcvwEC4vMOsuOyWyWKgTNAypkDkVZ3ceMS7';
$webhookUrl = 'http://localhost:8001/webhook/glpi/response?secret=glpi_webhook_secret_2026';
$stateFile  = __DIR__ . '/../storage/app/glpi_poller_state.json';

$log = fn($msg) => print("[".date('Y-m-d H:i:s')."] $msg\n");

function glpiGet($url, $appToken, $sessionToken = '') {
    $ch = curl_init($url);
    $h  = ["Content-Type: application/json", "App-Token: $appToken"];
    if ($sessionToken) $h[] = "Session-Token: $sessionToken";
    curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER=>true, CURLOPT_HTTPHEADER=>$h, CURLOPT_TIMEOUT=>10]);
    $res = curl_exec($ch); curl_close($ch);
    return json_decode($res, true) ?? [];
}

function glpiPost($url, $appToken, $body = []) {
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true, CURLOPT_POST => true,
        CURLOPT_POSTFIELDS     => json_encode($body),
        CURLOPT_HTTPHEADER     => ["Content-Type: application/json", "App-Token: $appToken"],
        CURLOPT_TIMEOUT        => 10,
    ]);
    $res = curl_exec($ch); curl_close($ch);
    return json_decode($res, true) ?? [];
}

function getTicketResponse(int $ticketId, string $glpiUrl, string $appToken, string $token): ?array
{
    // Priorité 1 : ITILSolution (ticket résolu)
    $solutions = glpiGet("$glpiUrl/apirest.php/Ticket/$ticketId/ITILSolution", $appToken, $token);
    if (!empty($solutions) && is_array($solutions)) {
        foreach (array_reverse($solutions) as $sol) {
            $content = $sol['content'] ?? '';
            // Ignorer les messages système GLPI
            if (in_array(trim($content), ['Solution approuvée', 'Solution approved', ''])) continue;
            $clean = trim(strip_tags(html_entity_decode($content, ENT_QUOTES, 'UTF-8')));
            if (strlen($clean) > 5) {
                return ['content' => $clean, 'source' => 'solution'];
            }
        }
    }

    // Priorité 2 : ITILFollowup (réponse agent sans clôture)
    $followups = glpiGet("$glpiUrl/apirest.php/Ticket/$ticketId/ITILFollowup", $appToken, $token);
    if (!empty($followups) && is_array($followups)) {
        foreach (array_reverse($followups) as $fu) {
            if (($fu['is_private'] ?? 0) === 1) continue;
            $content = $fu['content'] ?? '';
            $clean   = trim(strip_tags(html_entity_decode($content, ENT_QUOTES, 'UTF-8')));
            if (strlen($clean) > 5) {
                return ['content' => $clean, 'source' => 'followup'];
            }
        }
    }

    return null;
}

function callWebhook(string $url, int $ticketId, string $solution, string $source): array {
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => json_encode([
            'event'    => 'solution_added',
            'itemtype' => 'Ticket',
            'items_id' => $ticketId,
            'solution' => $solution,
            'source'   => $source,
        ]),
        CURLOPT_HTTPHEADER => ['Content-Type: application/json'],
        CURLOPT_TIMEOUT    => 30,
    ]);
    $res    = curl_exec($ch);
    $status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    return ['status' => $status, 'body' => trim($res ?? '')];
}

// ── Main ──────────────────────────────────────────────────────────────
$log("=== Poller démarré ===");

// Charger l'état persistant (tickets déjà traités avec succès)
$state     = file_exists($stateFile)
    ? (json_decode(file_get_contents($stateFile), true) ?? [])
    : [];
$processed = $state['processed'] ?? [];

// Session GLPI
$sess = glpiPost("$glpiUrl/apirest.php/initSession", $appToken, ['user_token' => $userToken]);
if (empty($sess['session_token'])) {
    $log("❌ Session GLPI échouée");
    exit(1);
}
$token = $sess['session_token'];
$log("✅ Session GLPI OK");

$newProcessed = [];

// Récupérer tous les tickets
$tickets = glpiGet("$glpiUrl/apirest.php/Ticket?range=0-200", $appToken, $token);

if (!is_array($tickets) || empty($tickets)) {
    $log("ℹ️  Aucun ticket retourné");
} else {
    $log("Total tickets trouvés : " . count($tickets));

    foreach ($tickets as $t) {
        $id     = $t['id']     ?? null;
        $status = $t['status'] ?? '?';
        if (!$id) continue;

        // ── Déjà traité avec succès → on skippe définitivement ───────
        // Deux sources de vérité :
        //   1. Le fichier JSON local (réponse 'OK' du webhook)
        //   2. Les réponses 'Already processed' du webhook (qdrant_indexed=true en base)
        if (in_array($id, $processed)) {
            // Pas de log pour ne pas polluer — ticket définitivement ignoré
            continue;
        }

        // Chercher une réponse agent (solution ou followup)
        $response = getTicketResponse($id, $glpiUrl, $appToken, $token);

        if (!$response) {
            $log("  #$id (status=$status) : pas encore de réponse agent");
            continue;
        }

        $log("  #$id (status=$status) : réponse [{$response['source']}] trouvée → envoi webhook...");

        $result = callWebhook($webhookUrl, $id, $response['content'], $response['source']);
        $log("  #$id : HTTP {$result['status']} — {$result['body']}");

        if ($result['status'] === 200) {
            $body = $result['body'];

            if ($body === 'OK' || $body === 'Already processed') {
                // 'OK'               → traité maintenant avec succès
                // 'Already processed' → déjà en base (qdrant_indexed=true)
                // Dans les deux cas : on marque comme traité pour ne plus jamais retraiter
                $newProcessed[] = $id;
                $log("  ✅ #$id marqué comme traité définitivement");
            } else {
                // 'No content yet', 'Ticket not found locally', etc.
                // → On ne marque pas : on réessaiera au prochain tour
                $log("  ⏳ #$id : '{$body}' — sera réessayé");
            }
        } else {
            $log("  ⚠️  #$id : erreur HTTP {$result['status']} — sera réessayé");
        }
    }
}

// Fermer session GLPI
glpiGet("$glpiUrl/apirest.php/killSession", $appToken, $token);

// Sauvegarder l'état mis à jour
$state['processed'] = array_values(array_unique(array_merge($processed, $newProcessed)));
// Garder max 1000 entrées pour éviter que le fichier grossisse indéfiniment
if (count($state['processed']) > 1000) {
    $state['processed'] = array_slice($state['processed'], -1000);
}
@mkdir(dirname($stateFile), 0755, true);
file_put_contents($stateFile, json_encode($state, JSON_PRETTY_PRINT));

$log("=== Terminé : " . count($newProcessed) . " nouveau(x) traité(s) ===\n");
