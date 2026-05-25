<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::create('applications', function (Blueprint $table) {
            $table->id();
            $table->string('name')->unique();
            $table->string('color', 16)->default('#F26522');
            $table->string('icon', 8)->default('APP');
            $table->timestamps();
        });

        Schema::create('conversations', function (Blueprint $table) {
            $table->id();
            $table->foreignId('user_id')->constrained()->cascadeOnDelete();
            $table->foreignId('application_id')->constrained('applications')->cascadeOnDelete();
            $table->string('title')->nullable();
            $table->timestamps();

            $table->index(['user_id', 'updated_at']);
            $table->index(['user_id', 'application_id']);
        });

        Schema::create('messages', function (Blueprint $table) {
            $table->id();
            $table->foreignId('conversation_id')->constrained('conversations')->cascadeOnDelete();
            $table->string('role', 20);
            $table->text('content');
            $table->timestamps();

            $table->index(['conversation_id', 'created_at']);
            $table->index(['role', 'created_at']);
        });

        DB::table('applications')->insert([
            ['name' => 'Parc Auto', 'color' => '#F26522', 'icon' => 'PA', 'created_at' => now(), 'updated_at' => now()],
            ['name' => 'BDM', 'color' => '#0F4C81', 'icon' => 'BDM', 'created_at' => now(), 'updated_at' => now()],
            ['name' => 'GRC', 'color' => '#2E7D32', 'icon' => 'GRC', 'created_at' => now(), 'updated_at' => now()],
        ]);
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('messages');
        Schema::dropIfExists('conversations');
        Schema::dropIfExists('applications');
    }
};

