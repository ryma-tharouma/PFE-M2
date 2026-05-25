<?php

namespace App\Services;

use Illuminate\Support\Facades\Log;
use Exception;

/**
 * Service pour communiquer avec l'API Python du Chatbot (Qdrant + Assistant)
 * Supporte le streaming via WebSocket Python pour l'affichage token par token.
 */
class ChatbotService
{
    protected string $apiUrl;
    protected int $timeout;
    protected string $wsUrl;

    public function __construct()
    {
        $this->apiUrl = rtrim(config('services.chatbot.url'), '/');
        $this->timeout = config('services.chatbot.timeout', 60);
        // Convertit http(s):// en ws(s)://
        $this->wsUrl = preg_replace('/^http/', 'ws', $this->apiUrl);
    }

    /**
     * Stream un message via WebSocket Python, en broadcastant chaque token
     * via l'événement Laravel Broadcasting (MessageTokenReceived).
     *
     * @param string   $userId
     * @param string   $message
     * @param int      $conversationId  Utilisé pour le channel de broadcast
     * @param string   $collection
     * @param int      $maxTurns
     * @param callable|null $onToken    Callback optionnel appelé pour chaque token reçu
     * @return array   ['success', 'response', 'sources', 'collection']
     */
    public function streamChat(
        string $userId,
        string $message,
        int $conversationId,
        string $collection = 'manuel_parc_auto',
        int $maxTurns = 1,
        ?callable $onToken = null
    ): array {
        $fullResponse = '';
        $sources = [];

        try {
            // Parse WebSocket URL: ws://host:port/path → host, port, path
            $parsed = parse_url($this->wsUrl . '/ws/chat');
            $host = $parsed['host'] ?? 'localhost';
            $port = $parsed['port'] ?? 8000;
            $path = ($parsed['path'] ?? '/ws/chat');

            // Ouvrir socket TCP
            $socket = @fsockopen($host, $port, $errno, $errstr, $this->timeout);
            if (!$socket) {
                throw new Exception("WebSocket connection failed: {$errstr}");
            }

            // WebSocket handshake
            $key = base64_encode(random_bytes(16));
            $handshake = "GET {$path} HTTP/1.1\r\n";
            $handshake .= "Host: {$host}:{$port}\r\n";
            $handshake .= "Upgrade: websocket\r\n";
            $handshake .= "Connection: Upgrade\r\n";
            $handshake .= "Sec-WebSocket-Key: {$key}\r\n";
            $handshake .= "Sec-WebSocket-Version: 13\r\n";
            $handshake .= "\r\n";

            fwrite($socket, $handshake);

            // Lire la réponse handshake
            $response = '';
            while (!feof($socket) && strpos($response, "\r\n\r\n") === false) {
                $response .= fgets($socket, 1024);
            }

            if (strpos($response, '101') === false) {
                throw new Exception('WebSocket upgrade failed');
            }

            // Envoyer le payload initial
            $payload = json_encode([
                'user_id'    => $userId,
                'message'    => $message,
                'collection' => $collection,
                'max_turns'  => $maxTurns,
            ]);
            $this->sendWebSocketFrame($socket, $payload);

            // Lire et traiter les messages
            while (!feof($socket)) {
                $frame = $this->readWebSocketFrame($socket);
                if ($frame === null) break;

                $data = json_decode($frame, true);
                if (!$data) continue;

                $type = $data['type'] ?? '';
                if ($type === 'typing') {
                    broadcast(new \App\Events\ChatTyping($conversationId, (bool) ($data['status'] ?? false)));
                } elseif ($type === 'token' || $type === 'chunk') {
                    $token = $data['text'] ?? '';
                    if ($token !== '') {
                        $fullResponse .= $token;
                        broadcast(new \App\Events\MessageTokenReceived($conversationId, $token));
                        if ($onToken) {
                            $onToken($token);
                        }
                    }
                } elseif ($type === 'done') {
                    $sources = $data['sources'] ?? [];
                    break;
                } elseif ($type === 'error') {
                    throw new Exception($data['error'] ?? 'WebSocket error');
                }
            }

            fclose($socket);

            return [
                'success'    => true,
                'response'   => $fullResponse,
                'sources'    => $sources,
                'collection' => $collection,
                'error'      => null,
            ];

        } catch (Exception $e) {
            Log::error('ChatbotService::streamChat error', [
                'error'      => $e->getMessage(),
                'user_id'    => $userId,
                'collection' => $collection,
            ]);

            return [
                'success'    => false,
                'response'   => null,
                'sources'    => [],
                'collection' => $collection,
                'error'      => $e->getMessage(),
            ];
        }
    }

    /**
     * Envoie un frame WebSocket maské (client → serveur)
     */
    private function sendWebSocketFrame($socket, string $payload): void
    {
        $len = strlen($payload);
        $frame = chr(0x81); // FIN + TEXT opcode

        if ($len < 126) {
            $frame .= chr($len | 0x80); // MASK + length
        } elseif ($len < 65536) {
            $frame .= chr(126 | 0x80);
            $frame .= pack('n', $len);
        } else {
            $frame .= chr(127 | 0x80);
            $frame .= pack('N', 0); // top 32 bits
            $frame .= pack('N', $len); // bottom 32 bits
        }

        $mask = random_bytes(4);
        $frame .= $mask;

        // Masquer le payload
        for ($i = 0; $i < $len; $i++) {
            $frame .= chr(ord($payload[$i]) ^ ord($mask[$i % 4]));
        }

        fwrite($socket, $frame);
    }

    /**
     * Lit un frame WebSocket non-masqué (serveur → client)
     */
    private function readWebSocketFrame($socket): ?string
    {
        $byte = fread($socket, 1);
        if (!$byte || feof($socket)) return null;

        $len_byte = fread($socket, 1);
        if (!$len_byte) return null;

        $len = ord($len_byte) & 0x7F;
        if ($len === 126) {
            $len_bytes = fread($socket, 2);
            $len = unpack('n', $len_bytes)[1];
        } elseif ($len === 127) {
            $len_bytes = fread($socket, 8);
            $len = unpack('N', substr($len_bytes, 4))[1];
        }

        $payload = '';
        while (strlen($payload) < $len && !feof($socket)) {
            $payload .= fread($socket, $len - strlen($payload));
        }

        return $payload;
    }

    /**
     * Appel HTTP classique (non-streaming) — gardé pour compatibilité.
     */
    public function chat(
        string $userId,
        string $message,
        ?array $history = null,
        string $collection = 'manuel_parc_auto'
    ): array {
        try {
            $health = $this->health();
            if (!$health['ok']) {
                throw new Exception('API du chatbot non disponible');
            }

            $response = \Illuminate\Support\Facades\Http::timeout($this->timeout)
                ->post("{$this->apiUrl}/api/chat", [
                    'user_id'    => $userId,
                    'message'    => $message,
                    'collection' => $collection,
                    'max_turns'  => 1,
                ])
                ->throw()
                ->json();

            return [
                'success' => $response['success'] ?? true,
                'data'    => $response,
                'error'   => null,
            ];

        } catch (\Illuminate\Http\Client\RequestException $e) {
            $error = 'Erreur lors de la requête: ' . $e->getMessage();
            Log::error("Chatbot API Error: {$error}");
            return ['success' => false, 'data' => null, 'error' => $error];

        } catch (Exception $e) {
            Log::error("Chat Service Error: {$e->getMessage()}");
            return ['success' => false, 'data' => null, 'error' => $e->getMessage()];
        }
    }

    /**
     * Vérifier la santé de l'API
     */
    public function health(): array
    {
        try {
            $response = \Illuminate\Support\Facades\Http::timeout(10)
                ->get("{$this->apiUrl}/health")
                ->json();

            return [
                'ok'       => isset($response['status']) && $response['status'] === 'ok',
                'response' => $response,
            ];
        } catch (Exception $e) {
            Log::warning('Chatbot API health check failed: ' . $e->getMessage());
            return ['ok' => false, 'response' => null];
        }
    }

    /**
     * Récupérer les informations de l'API
     */
    public function info(): array
    {
        try {
            $response = \Illuminate\Support\Facades\Http::timeout($this->timeout)
                ->get("{$this->apiUrl}/api/info")
                ->json();
            return ['success' => true, 'data' => $response];
        } catch (Exception $e) {
            Log::error('Chatbot API info error: ' . $e->getMessage());
            return ['success' => false, 'data' => null];
        }
    }

    /**
     * Récupérer les collections disponibles
     */
    public function getCollections(): array
    {
        try {
            $response = \Illuminate\Support\Facades\Http::timeout($this->timeout)
                ->get("{$this->apiUrl}/api/collections")
                ->json();
            return ['success' => true, 'data' => $response['collections'] ?? []];
        } catch (Exception $e) {
            Log::error('Chatbot API collections error: ' . $e->getMessage());
            return ['success' => false, 'data' => []];
        }
    }
}

