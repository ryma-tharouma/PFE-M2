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
        'color',
        'icon',
        'qdrant_collection',
    ];

    public function conversations(): HasMany
    {
        return $this->hasMany(Conversation::class);
    }

    public function manuals(): HasMany
    {
        return $this->hasMany(Manual::class);
    }

    public function faqItems(): HasMany
    {
        return $this->hasMany(Faq::class);
    }
}
