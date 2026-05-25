<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Ajoute la colonne qdrant_collection à la table applications.
     * Cette colonne est remplie automatiquement par ProcessManualPipeline
     * après indexation dans Qdrant.
     *
     * Valeur exemple : "manuel_parc_auto_cleaned"
     */
    public function up(): void
    {
        Schema::table('applications', function (Blueprint $table) {
            $table->string('qdrant_collection')->nullable()->after('icon');
        });
    }

    public function down(): void
    {
        Schema::table('applications', function (Blueprint $table) {
            $table->dropColumn('qdrant_collection');
        });
    }
};
