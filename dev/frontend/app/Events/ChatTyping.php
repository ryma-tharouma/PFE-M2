<?php

namespace App\Events;

use Illuminate\Broadcasting\InteractsWithSockets;
use Illuminate\Broadcasting\PrivateChannel;
use Illuminate\Contracts\Broadcasting\ShouldBroadcast;
use Illuminate\Queue\SerializesModels;

/**
 * Broadcasté quand le chatbot commence/finit de générer une réponse.
 */
class ChatTyping implements ShouldBroadcast
{
    use InteractsWithSockets, SerializesModels;

    public int $conversationId;
    public bool $isTyping;

    public function __construct(int $conversationId, bool $isTyping)
    {
        $this->conversationId = $conversationId;
        $this->isTyping = $isTyping;
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
            'is_typing'       => $this->isTyping,
        ];
    }

    public function broadcastAs(): string
    {
        return 'chat.typing';
    }
}
