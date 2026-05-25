
<?php
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('messages', function (Blueprint $table) {
            $table->json('sources')->nullable()->after('content');
            $table->string('collection')->nullable()->after('sources');
            $table->float('confidence')->default(0)->after('collection');
            $table->boolean('needs_escalation')->default(false)->after('confidence');
        });
    }

    public function down(): void
    {
        Schema::table('messages', function (Blueprint $table) {
            $table->dropColumn(['sources', 'collection', 'confidence', 'needs_escalation']);
        });
    }
};
