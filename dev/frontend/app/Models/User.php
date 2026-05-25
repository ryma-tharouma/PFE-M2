<?php

namespace App\Models;

// use Illuminate\Contracts\Auth\MustVerifyEmail;
use Database\Factories\UserFactory;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Foundation\Auth\User as Authenticatable;
use Illuminate\Notifications\Notifiable;
use Illuminate\Database\Eloquent\Relations\HasMany;

class User extends Authenticatable
{
    /** @use HasFactory<UserFactory> */
    use HasFactory, Notifiable;

    /**
     * The attributes that are mass assignable.
     *
     * @var list<string>
     */
    protected $fillable = [
        'ldap_uid',
        'employee_no',
        'name',
        'email',
        'title',
        'department',
        'is_admin',
        'last_login_at',
        'password',
    ];

    /**
     * The attributes that should be hidden for serialization.
     *
     * @var list<string>
     */
    protected $hidden = [
        'password',
        'remember_token',
    ];

    /**
     * Get the attributes that should be cast.
     *
     * @return array<string, string>
     */
    protected function casts(): array
    {
        return [
            'email_verified_at' => 'datetime',
            'is_admin' => 'boolean',
            'last_login_at' => 'datetime',
            'password' => 'hashed',
        ];
    }

    /**
     * Accessor pour afficher le nom complet / label à utiliser dans l'UI.
     * Usage: auth()->user()->display_name
     */
    public function getDisplayNameAttribute(): string
    {
        // Si flag admin présent -> afficher Super Admin
        if (($this->is_admin ?? false) === true) {
            return 'Super Admin';
        }

        // Si un nom complet est stocké -> l'utiliser
        if (!empty($this->name)) {
            return $this->name;
        }

        // Sinon utiliser employee_no ou ldap_uid comme fallback
        return $this->employee_no ?? ($this->ldap_uid ?? 'Utilisateur');
    }

    /**
     * Relation: l'utilisateur a plusieurs conversations
     */
    public function conversations(): HasMany
    {
        return $this->hasMany(Conversation::class);
    }
}

