<?php

namespace App\Events;

use Illuminate\Broadcasting\Channel;
use Illuminate\Broadcasting\InteractsWithSockets;
use Illuminate\Broadcasting\PrivateChannel;
use Illuminate\Contracts\Broadcasting\ShouldBroadcast;
use Illuminate\Queue\SerializesModels;
use App\Models\Message;

class MessageCreated implements ShouldBroadcast
{
    use InteractsWithSockets, SerializesModels;

    public Message $message;
    public int $conversationId;
    public int $userId;

    /**
     * Create a new event instance.
     *
     * @return void
     */
    public function __construct(Message $message)
    {
        $this->message = $message;
        $this->conversationId = $message->conversation_id;
        $this->userId = $message->conversation->user_id ?? null;
    }

    /**
     * Get the channels the event should broadcast on.
     *
     * We broadcast to two private channels:
     *  - private-conversation.{id} so clients viewing the conversation can update
     *  - private-user.{user_id} so the user receives notifications in sidebar
     *
     * @return \Illuminate\Broadcasting\Channel|array
     */
    public function broadcastOn()
    {
        $channels = [];
        if ($this->conversationId) {
            $channels[] = new PrivateChannel('conversation.' . $this->conversationId);
        }

        if ($this->userId) {
            $channels[] = new PrivateChannel('user.' . $this->userId);
        }

        return $channels;
    }

    /**
     * The data to broadcast.
     *
     * @return array
     */
    public function broadcastWith()
    {
        return [
            'id' => $this->message->id,
            'conversation_id' => $this->conversationId,
            'role' => $this->message->role,
            'content' => $this->message->content,
            'sources' => $this->message->sources ?? [],
            'collection' => $this->message->collection ?? null,
            'created_at' => $this->message->created_at ? $this->message->created_at->toDateTimeString() : now()->toDateTimeString(),
        ];
    }

    public function broadcastAs()
    {
        return 'message.created';
    }
}
