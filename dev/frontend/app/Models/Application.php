<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\Relations\BelongsToMany;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class Application extends Model
{
    use HasFactory;

    protected $fillable = [
        'name',
        'color',
        'icon',
        'qdrant_collection',
        'admin_id',
        'department',
        'archived',
        'archived_at',
    ];

    protected $casts = [
        'archived'    => 'boolean',
        'archived_at' => 'datetime',
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

    /**
     * Relation: l'application a un admin (user) — propriétaire historique
     */
    public function admin(): BelongsTo
    {
        return $this->belongsTo(User::class, 'admin_id');
    }

    /**
     * Relation: l'application a plusieurs admins
     */
    public function admins(): BelongsToMany
    {
        return $this->belongsToMany(User::class, 'application_admins');
    }

    /**
     * Relation: l'application a plusieurs utilisateurs autorisés
     */
    public function allowedUsers(): BelongsToMany
    {
        return $this->belongsToMany(User::class, 'application_users');
    }

    /**
     * Relation: l'application peut être liée à plusieurs départements
     */
    public function departmentLinks(): HasMany
    {
        return $this->hasMany(ApplicationDepartment::class);
    }

    /**
     * Retourne la liste des noms de départements liés à cette application.
     */
    public function departmentNames(): array
    {
        return $this->departmentLinks()->pluck('department')->toArray();
    }

    /**
     * Remplace complètement la liste des départements de cette application.
     */
    public function syncDepartments(array $departments): void
    {
        $departments = array_values(array_unique(array_filter(array_map('trim', $departments))));

        $this->departmentLinks()->delete();

        foreach ($departments as $dept) {
            $this->departmentLinks()->create(['department' => $dept]);
        }
    }
}
