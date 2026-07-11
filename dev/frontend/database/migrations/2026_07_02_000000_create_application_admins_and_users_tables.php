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
        // Table pour les admins des applications
        Schema::create('application_admins', function (Blueprint $table) {
            $table->id();
            $table->foreignId('application_id')->constrained('applications')->cascadeOnDelete();
            $table->foreignId('user_id')->constrained('users')->cascadeOnDelete();
            $table->timestamps();

            // Un admin par application
            $table->unique(['application_id', 'user_id']);
        });

        // Table pour les utilisateurs des applications
        Schema::create('application_users', function (Blueprint $table) {
            $table->id();
            $table->foreignId('application_id')->constrained('applications')->cascadeOnDelete();
            $table->foreignId('user_id')->constrained('users')->cascadeOnDelete();
            $table->timestamps();

            // Un user par application
            $table->unique(['application_id', 'user_id']);
        });

        // Ajouter la colonne admin_type au modèle User
        Schema::table('users', function (Blueprint $table) {
            $table->enum('admin_type', ['super', 'app', 'user'])->default('user')->after('is_admin');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('application_users');
        Schema::dropIfExists('application_admins');
        Schema::table('users', function (Blueprint $table) {
            $table->dropColumn('admin_type');
        });
    }
};

