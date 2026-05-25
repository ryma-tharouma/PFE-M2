<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::table('users', function (Blueprint $table) {
            $table->string('ldap_uid')->nullable()->unique();
            $table->string('title')->nullable();
            $table->string('department')->nullable();
            $table->boolean('is_admin')->default(false);
            $table->timestamp('last_login_at')->nullable();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('users', function (Blueprint $table) {
            $table->dropUnique('users_ldap_uid_unique');
            $table->dropColumn([
                'ldap_uid',
                'title',
                'department',
                'is_admin',
                'last_login_at',
            ]);
        });
    }
};

