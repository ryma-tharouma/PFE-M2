<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::create('manuals', function (Blueprint $table) {
            $table->id();
            $table->string('name');
            $table->foreignId('application_id')->constrained('applications')->cascadeOnDelete();
            $table->string('version', 50)->nullable();
            $table->string('file_path');
            $table->string('status', 20)->default('pending');
            $table->string('cleaned_json_path')->nullable();
            $table->text('processing_error')->nullable();
            $table->timestamps();

            $table->index(['application_id', 'status']);
        });

        Schema::create('tickets', function (Blueprint $table) {
            $table->id();
            $table->foreignId('user_id')->nullable()->constrained('users')->nullOnDelete();
            $table->string('title');
            $table->string('category', 50);
            $table->string('priority', 20);
            $table->text('description')->nullable();
            $table->string('glpi_ticket_id')->nullable();
            $table->string('glpi_status', 50)->nullable();
            $table->timestamps();

            $table->index(['user_id', 'created_at']);
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('tickets');
        Schema::dropIfExists('manuals');
    }
};
