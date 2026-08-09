<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class ApplicationDepartment extends Model
{
    protected $fillable = [
        'application_id',
        'department',
    ];

    public function application(): BelongsTo
    {
        return $this->belongsTo(Application::class);
    }
}
