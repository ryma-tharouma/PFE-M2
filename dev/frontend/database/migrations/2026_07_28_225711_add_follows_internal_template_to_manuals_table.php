<?php
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('manuals', function (Blueprint $table) {
            if (!Schema::hasColumn('manuals', 'follows_internal_template')) {
                $table->boolean('follows_internal_template')->default(false)->after('status');
            }
        });
    }

    public function down(): void
    {
        Schema::table('manuals', function (Blueprint $table) {
            $table->dropColumn('follows_internal_template');
        });
    }
};
