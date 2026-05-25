<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        // ── Conversations : ajouter started_at, last_message_at ──────────
        Schema::table('conversations', function (Blueprint $table) {
            // Heure exacte de création de la première question
            $table->timestamp('started_at')->nullable()->after('title');
            // Heure de la dernière activité
            $table->timestamp('last_message_at')->nullable()->after('started_at');
        });

        // ── Messages : ajouter timing et metadata ────────────────────────
        Schema::table('messages', function (Blueprint $table) {
            // Temps de réponse en secondes (null pour les messages user)
            $table->float('response_time_sec')->nullable()->after('needs_escalation');
            // Heure exacte de la question (copie de created_at pour clarté)
            $table->timestamp('asked_at')->nullable()->after('response_time_sec');
            // Heure exacte de la réponse complète
            $table->timestamp('answered_at')->nullable()->after('asked_at');
        });
    }

    public function down(): void
    {
        Schema::table('conversations', function (Blueprint $table) {
            $table->dropColumn(['started_at', 'last_message_at']);
        });

        Schema::table('messages', function (Blueprint $table) {
            $table->dropColumn(['response_time_sec', 'asked_at', 'answered_at']);
        });
    }
};
