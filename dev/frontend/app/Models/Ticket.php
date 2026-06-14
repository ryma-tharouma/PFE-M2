<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class Ticket extends Model
{
    protected $fillable = [
        'user_id',
        'conversation_id',
        'application_id',
        'title',
        'category',
        'priority',
        'description',
        'unanswerable_question',
        'glpi_ticket_id',
        'glpi_status',
        'glpi_response',
        'glpi_responded_at',
        'source',
        'user_email',
    ];

    protected $casts = [
        'glpi_responded_at' => 'datetime',
        'qdrant_indexed'    => 'boolean',
    ];

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }

    public function conversation(): BelongsTo
    {
        return $this->belongsTo(Conversation::class);
    }

    public function application(): BelongsTo
    {
        return $this->belongsTo(Application::class);
    }
}
