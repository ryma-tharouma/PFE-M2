
<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('tickets', function (Blueprint $table) {
            if (!Schema::hasColumn('tickets', 'glpi_event')) {
                $table->string('glpi_event', 64)->nullable()->after('glpi_response');
            }
            if (!Schema::hasColumn('tickets', 'qdrant_indexed')) {
                $table->boolean('qdrant_indexed')->default(false)->after('glpi_event');
            }
        });
    }

    public function down(): void
    {
        Schema::table('tickets', function (Blueprint $table) {
            $table->dropColumn(['glpi_event', 'qdrant_indexed']);
        });
    }
};
