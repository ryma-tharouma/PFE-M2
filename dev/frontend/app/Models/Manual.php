<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class Manual extends Model
{
    use HasFactory;

    protected $fillable = [
        'name',
        'application_id',
        'version',
        'file_path',
        'status',
        'cleaned_json_path',
        'processing_error',
    ];

    public function application(): BelongsTo
    {
        return $this->belongsTo(Application::class);
    }
}
