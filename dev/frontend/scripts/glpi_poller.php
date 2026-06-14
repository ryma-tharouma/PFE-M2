<?php
$glpiUrl    = 'http://localhost:8080';
$appToken   = 'XY12O6dDRNAXLFyIELY7aiCibxuWIQHAOlFA8Zps';
$userToken  = '5QXljqcvwEC4vMOsuOyWyWKgTNAypkDkVZ3ceMS7';
$webhookUrl = 'http://localhost:8001/webhook/glpi/response';
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

/**
 * Récupère le contenu de la réponse GLPI :
 * Priorité 1 → ITILSolution (ticket résolu)
 * Priorité 2 → ITILFollowup (réponse agent sans clôture)
 * Retourne ['content' => '...', 'source' => 'solution|followup']
 */
function getTicketResponse(int $ticketId, string $glpiUrl, string $appToken, string $token): ?array
{
    // 1. Essayer ITILSolution
    $solutions = glpiGet("$glpiUrl/apirest.php/Ticket/$ticketId/ITILSolution", $appToken, $token);
    if (!empty($solutions) && is_array($solutions)) {
        foreach (array_reverse($solutions) as $sol) {
            $content = $sol['content'] ?? '';
            if ($content && $content !== 'Solution approuvée' && $content !== 'Solution approved') {
                $clean = trim(strip_tags(html_entity_decode($content, ENT_QUOTES, 'UTF-8')));
                if (strlen($clean) > 5) {
                    return ['content' => $clean, 'source' => 'solution'];
                }
            }
        }
    }

    // 2. Fallback → ITILFollowup (réponses agent)
    $followups = glpiGet("$glpiUrl/apirest.php/Ticket/$ticketId/ITILFollowup", $appToken, $token);
    if (!empty($followups) && is_array($followups)) {
        foreach (array_reverse($followups) as $fu) {
            if (($fu['is_private'] ?? 0) === 1) continue;
            $content = $fu['content'] ?? '';
            if ($content) {
                $clean = trim(strip_tags(html_entity_decode($content, ENT_QUOTES, 'UTF-8')));
                if (strlen($clean) > 5) {
                    return ['content' => $clean, 'source' => 'followup'];
                }
            }
        }
    }

    return null;
}

function callWebhook($url, $ticketId, $solution, $source) {
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true, CURLOPT_POST => true,
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
    return ['status' => $status, 'body' => trim($res)];
}

// ── Main ──────────────────────────────────────────────────────────────
$log("=== Poller démarré ===");
$state     = file_exists($stateFile) ? (json_decode(file_get_contents($stateFile), true) ?? []) : [];
$processed = $state['processed'] ?? [];

// Session GLPI
$sess = glpiPost("$glpiUrl/apirest.php/initSession", $appToken, ['user_token' => $userToken]);
if (empty($sess['session_token'])) { $log("❌ Session échouée"); exit(1); }
$token = $sess['session_token'];
$log("✅ Session OK");

$newProcessed = [];

// ── Récupérer TOUS les tickets d'un coup (le filtre searchText[status] ne fonctionne pas) ──
$tickets = glpiGet(
    "$glpiUrl/apirest.php/Ticket?range=0-200",
    $appToken, $token
);


if (!is_array($tickets) || empty($tickets)) {
    $log("❌ Aucun ticket retourné par l'API");
} else {
    $log("Total tickets trouvés : " . count($tickets));

    foreach ($tickets as $t) {
        $id     = $t['id']     ?? null;
        $status = $t['status'] ?? '?';

        if (!$id) continue;

        // Déjà traité → on skippe
        if (in_array($id, $processed)) {
            continue;
        }

        // Chercher une réponse (solution ou followup)
        $response = getTicketResponse($id, $glpiUrl, $appToken, $token);
        $log("  #$id (status=$status) : vérification en cours...");
        if (!$response) {
            $log("  #$id (status=$status) : pas de réponse agent encore");
            continue;
        }

        $log("  #$id (status=$status) : réponse trouvée via [{$response['source']}] → envoi webhook...");
        $log("  #$id : contenu = " . mb_substr($response['content'], 0, 80) . "...");

        $result = callWebhook($webhookUrl, $id, $response['content'], $response['source']);
        $log("  #$id : HTTP {$result['status']} — {$result['body']}");

        if ($result['status'] === 200 && $result['body'] === 'OK') {
            $newProcessed[] = $id;
            $log("  ✅ #$id traité avec succès");
        } else {
            $log("  ⚠️  #$id non confirmé — sera réessayé au prochain tour");
        }
    }
}

// Fermer session GLPI
glpiGet("$glpiUrl/apirest.php/killSession", $appToken, $token);

// Sauvegarder état
$state['processed'] = array_values(array_unique(array_merge($processed, $newProcessed)));
if (count($state['processed']) > 500) $state['processed'] = array_slice($state['processed'], -500);
@mkdir(dirname($stateFile), 0755, true);
file_put_contents($stateFile, json_encode($state, JSON_PRETTY_PRINT));

$log("=== Terminé : " . count($newProcessed) . " nouveau(x) traité(s) ===\n");
