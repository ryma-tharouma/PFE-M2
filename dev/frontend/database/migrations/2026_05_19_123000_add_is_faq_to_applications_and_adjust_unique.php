<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('applications', function (Blueprint $table) {
            // ajouter un flag pour différencier les enregistrements utilisés pour les FAQ
            $table->boolean('is_faq')->default(false)->after('name');
            // supprimer l'unique sur name et créer une contrainte composite (name,is_faq)
            $table->dropUnique(['name']);
            $table->unique(['name', 'is_faq']);
        });
    }

    public function down(): void
    {
        Schema::table('applications', function (Blueprint $table) {
            $table->dropUnique(['name', 'is_faq']);
            $table->unique('name');
            $table->dropColumn('is_faq');
        });
    }
};
