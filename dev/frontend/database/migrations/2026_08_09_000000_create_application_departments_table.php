<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('application_departments', function (Blueprint $table) {
            $table->id();
            $table->foreignId('application_id')->constrained()->onDelete('cascade');
            $table->string('department');
            $table->timestamps();
            $table->unique(['application_id', 'department']);
        });

        // Migration des données existantes : la colonne applications.department
        // (une seule valeur) devient une ligne dans le pivot.
        DB::table('applications')->whereNotNull('department')->get()->each(function ($app) {
            DB::table('application_departments')->insert([
                'application_id' => $app->id,
                'department'     => $app->department,
                'created_at'     => now(),
                'updated_at'     => now(),
            ]);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('application_departments');
    }
};
