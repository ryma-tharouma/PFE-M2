<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class Message extends Model
{
    use HasFactory;

    protected $fillable = [
        'conversation_id',
        'role',
        'content',
        'sources',
        'collection',
        'manual_id',
        'confidence',
        'needs_escalation',
        'response_time_sec',
        'asked_at',
        'answered_at',
        'faq_status',
    ];

    protected $casts = [
        'sources'           => 'array',
        'needs_escalation'  => 'boolean',
        'asked_at'          => 'datetime',
        'answered_at'       => 'datetime',
    ];

    public function conversation(): BelongsTo
    {
        return $this->belongsTo(Conversation::class);
    }
}
