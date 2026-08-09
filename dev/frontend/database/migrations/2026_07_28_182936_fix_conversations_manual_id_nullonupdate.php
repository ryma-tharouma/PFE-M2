<?php
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('conversations', function (Blueprint $table) {
            $table->dropForeign(['manual_id']);
            $table->foreign('manual_id')
                ->references('id')->on('manuals')
                ->nullOnDelete(); // au lieu de cascadeOnDelete()
        });
    }

    public function down(): void
    {
        Schema::table('conversations', function (Blueprint $table) {
            $table->dropForeign(['manual_id']);
            $table->foreign('manual_id')
                ->references('id')->on('manuals')
                ->cascadeOnDelete();
        });
    }
};
