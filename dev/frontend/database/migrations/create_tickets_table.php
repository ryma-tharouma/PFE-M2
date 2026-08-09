<?php
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('tickets', function (Blueprint $table) {
            if (!Schema::hasColumn('tickets', 'conversation_id')) {
                $table->foreignId('conversation_id')
                    ->nullable()
                    ->after('user_id')
                    ->constrained('conversations')
                    ->nullOnDelete();
            }
            if (!Schema::hasColumn('tickets', 'application_id')) {
                $table->foreignId('application_id')
                    ->nullable()
                    ->after('conversation_id')
                    ->constrained('applications')
                    ->nullOnDelete();
            }
            if (!Schema::hasColumn('tickets', 'unanswerable_question')) {
                $table->text('unanswerable_question')->nullable();
            }
            if (!Schema::hasColumn('tickets', 'glpi_response')) {
                $table->text('glpi_response')->nullable();
            }
            if (!Schema::hasColumn('tickets', 'glpi_responded_at')) {
                $table->timestamp('glpi_responded_at')->nullable();
            }
            if (!Schema::hasColumn('tickets', 'source')) {
                $table->enum('source', ['manual', 'auto_suggestion'])->default('manual');
            }
            if (!Schema::hasColumn('tickets', 'user_email')) {
                $table->string('user_email')->nullable();
            }
        });
    }

    public function down(): void
    {
        Schema::table('tickets', function (Blueprint $table) {
            $table->dropColumn(['unanswerable_question', 'glpi_response', 'glpi_responded_at', 'source', 'user_email']);
            $table->dropConstrainedForeignId('conversation_id');
            $table->dropConstrainedForeignId('application_id');
        });
    }
};
