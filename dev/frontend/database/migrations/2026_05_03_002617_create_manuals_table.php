<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('manuals', function (Blueprint $table) {
            $table->id();
            $table->string('name');
            $table->foreignId('application_id')->constrained()->onDelete('cascade');
            $table->string('version', 20)->default('1.0');
            $table->string('file_path');
            $table->enum('status', ['pending', 'processing', 'indexed', 'failed'])->default('pending');
            $table->string('cleaned_json_path')->nullable();
            $table->text('processing_error')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('manuals');
    }
};
