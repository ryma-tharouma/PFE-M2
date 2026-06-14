<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('tickets', function (Blueprint $table) {
            $table->id();

            // Lien avec le chatbot
            $table->foreignId('user_id')
                ->nullable()
                ->constrained('users')
                ->nullOnDelete();
            $table->foreignId('conversation_id')
                ->nullable()
                ->constrained('conversations')
                ->nullOnDelete();
            $table->foreignId('application_id')
                ->nullable()
                ->constrained('applications')
                ->nullOnDelete();

            // Contenu du ticket
            $table->string('title');
            $table->enum('category', ['incident', 'demande', 'question'])->default('question');
            $table->enum('priority', ['Basse', 'Moyenne', 'Haute', 'Critique'])->default('Moyenne');
            $table->text('description')->nullable();

            // Question qui a déclenché le ticket (quand le bot n'a pas pu répondre)
            $table->text('unanswerable_question')->nullable();

            // Réponse GLPI (reçue par webhook)
            $table->text('glpi_response')->nullable();
            $table->timestamp('glpi_responded_at')->nullable();

            // Référence GLPI
            $table->unsignedInteger('glpi_ticket_id')->nullable()->index();
            $table->enum('glpi_status', ['new', 'processing', 'solved', 'closed'])->default('new');

            // Source : bouton manuel ou suggestion automatique
            $table->enum('source', ['manual', 'auto_suggestion'])->default('manual');

            // Mail de l'utilisateur (pour recevoir la réponse)
            $table->string('user_email')->nullable();

            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('tickets');
    }
};
