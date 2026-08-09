<?php
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('faq_items', function (Blueprint $table) {
            $table->text('source')->nullable()->change();
            $table->text('title')->nullable()->change();
            $table->text('applies_to')->nullable()->change();
        });
    }

    public function down(): void
    {
        Schema::table('faq_items', function (Blueprint $table) {
            $table->string('source', 50)->nullable()->change();
            $table->string('title')->nullable()->change();
            $table->string('applies_to')->nullable()->change();
        });
    }
};
