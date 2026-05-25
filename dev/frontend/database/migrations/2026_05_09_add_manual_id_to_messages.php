<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Ajoute manual_id aux messages pour meilleure traçabilité.
     * Permet de supprimer directement tous les messages/conversations d'un manuel.
     */
    public function up(): void
    {
        Schema::table('messages', function (Blueprint $table) {
            $table->foreignId('manual_id')->nullable()->constrained('manuals')->cascadeOnDelete();
            $table->index(['manual_id', 'created_at']);
        });

        Schema::table('conversations', function (Blueprint $table) {
            $table->foreignId('manual_id')->nullable()->constrained('manuals')->cascadeOnDelete();
            $table->index(['manual_id']);
        });
    }

    public function down(): void
    {
        Schema::table('messages', function (Blueprint $table) {
            $table->dropForeignKeyIfExists(['manual_id']);
            $table->dropColumn('manual_id');
        });

        Schema::table('conversations', function (Blueprint $table) {
            $table->dropForeignKeyIfExists(['manual_id']);
            $table->dropColumn('manual_id');
        });
    }
};

