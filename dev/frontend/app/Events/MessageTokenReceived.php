<?php

namespace App\Events;

use Illuminate\Broadcasting\InteractsWithSockets;
use Illuminate\Broadcasting\PrivateChannel;
use Illuminate\Contracts\Broadcasting\ShouldBroadcast;
use Illuminate\Queue\SerializesModels;

/**
 * Broadcasté pour chaque token reçu du Python API en streaming.
 * Le frontend écoute ce channel et ajoute le token au message en cours.
 */
class MessageTokenReceived implements ShouldBroadcast
{
    use InteractsWithSockets, SerializesModels;

    public int $conversationId;
    public string $token;

    public function __construct(int $conversationId, string $token)
    {
        $this->conversationId = $conversationId;
        $this->token = $token;
    }

    public function broadcastOn(): array
    {
        return [
            new PrivateChannel('conversation.' . $this->conversationId),
        ];
    }

    public function broadcastWith(): array
    {
        return [
            'conversation_id' => $this->conversationId,
            'token'           => $this->token,
        ];
    }

    public function broadcastAs(): string
    {
        return 'message.token';
    }
}
