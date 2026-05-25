<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Conversation extends Model
{
    use HasFactory;

    protected $fillable = [
        'user_id',
        'application_id',
        'manual_id',
        'title',
        'started_at',
        'last_message_at',
    ];

    protected $casts = [
        'started_at'      => 'datetime',
        'last_message_at' => 'datetime',
    ];

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }

    public function application(): BelongsTo
    {
        return $this->belongsTo(Application::class);
    }

    public function messages(): HasMany
    {
        return $this->hasMany(Message::class)->orderBy('created_at');
    }

    public function userMessages(): HasMany
    {
        return $this->hasMany(Message::class)->where('role', 'user');
    }

    public function assistantMessages(): HasMany
    {
        return $this->hasMany(Message::class)->where('role', 'assistant');
    }
}
