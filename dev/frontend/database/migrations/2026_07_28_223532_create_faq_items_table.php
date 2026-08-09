<?php
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('faq_items', function (Blueprint $table) {
            $table->id();
            $table->string('section_id')->unique();
            $table->foreignId('application_id')
                ->constrained('applications')
                ->cascadeOnDelete();
            $table->text('problem');
            $table->text('answer');
            $table->text('full_text')->nullable();
            $table->string('source_type', 50)->default('faq');
            $table->string('source', 50)->nullable();
            $table->string('title')->nullable();
            $table->string('applies_to')->nullable();
            $table->timestamps();

            $table->index('application_id');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('faq_items');
    }
};
