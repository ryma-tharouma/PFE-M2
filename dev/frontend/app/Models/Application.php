<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Application extends Model
{
    use HasFactory;

    protected $fillable = [
        'name',
        'is_faq',
        'color',
        'icon',
        'qdrant_collection',   // ← rempli automatiquement par le pipeline
    ];

    public function conversations(): HasMany
    {
        return $this->hasMany(Conversation::class);
    }

    public function manuals(): HasMany
    {
        return $this->hasMany(Manual::class);
    }
}
