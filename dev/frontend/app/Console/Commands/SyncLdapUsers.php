<?php

namespace App\Console\Commands;

use App\Models\User;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Hash;

/**
 * Synchronise TOUS les utilisateurs LDAP (Sonatrach) dans la table `users`,
 * y compris ceux qui ne se sont jamais connectés à l'application.
 *
 * Sans cette synchro, la table `users` ne contient que les comptes créés
 * "à la volée" lors du premier login, ce qui explique pourquoi les listes
 * d'administration (choix admin, choix users par département) n'affichaient
 * qu'une poignée de personnes au lieu des 200 importées via le LDIF.
 *
 * Usage :
 *   php artisan ldap:sync-users
 *
 * Options (sinon lues dans .env) :
 *   --host=ldap://localhost:389
 *   --base="ou=people,dc=sonatrach,dc=test"
 *   --admin-dn="cn=admin,dc=sonatrach,dc=test"
 *   --admin-pass="pfe@2026"
 *
 * Pré-requis :
 *   - extension PHP ldap activée (php-ldap)
 *   - colonne `ldap_uid` unique dans la table users (sert de clé de matching)
 */
class SyncLdapUsers extends Command
{
    protected $signature = 'ldap:sync-users
                            {--host= : Hôte LDAP}
                            {--base= : Base DN people}
                            {--admin-dn= : DN admin LDAP}
                            {--admin-pass= : Mot de passe admin LDAP}';

    protected $description = "Synchronise tous les utilisateurs LDAP dans la table users (y compris ceux jamais connectés).";

    public function handle(): int
    {
        $host      = $this->option('host')       ?: env('LDAP_HOST', 'ldap://localhost:389');
        $baseDn    = $this->option('base')       ?: env('LDAP_BASE_DN', 'ou=people,dc=sonatrach,dc=test');
        $adminDn   = $this->option('admin-dn')   ?: env('LDAP_ADMIN_DN', 'cn=admin,dc=sonatrach,dc=test');
        $adminPass = $this->option('admin-pass') ?: env('LDAP_ADMIN_PASSWORD', 'pfe@2026');

        if (!function_exists('ldap_connect')) {
            $this->error("L'extension PHP ldap n'est pas installée/activée.");
            return self::FAILURE;
        }

        $this->info("Connexion LDAP : {$host}");

        $conn = ldap_connect($host);
        if (!$conn) {
            $this->error('Impossible de contacter le serveur LDAP.');
            return self::FAILURE;
        }

        ldap_set_option($conn, LDAP_OPT_PROTOCOL_VERSION, 3);
        ldap_set_option($conn, LDAP_OPT_REFERRALS, 0);

        if (!@ldap_bind($conn, $adminDn, $adminPass)) {
            $this->error('Bind LDAP échoué : ' . ldap_error($conn));
            return self::FAILURE;
        }

        $filter     = '(objectClass=inetOrgPerson)';
        $attributes = ['uid', 'cn', 'mail', 'title', 'ou', 'description', 'employeenumber'];

        $search = ldap_search($conn, $baseDn, $filter, $attributes);
        if (!$search) {
            $this->error('Recherche LDAP échouée : ' . ldap_error($conn));
            return self::FAILURE;
        }

        $entries = ldap_get_entries($conn, $search);
        $count   = 0;
        $bar     = $this->output->createProgressBar($entries['count'] ?? 0);
        $bar->start();

        for ($i = 0; $i < ($entries['count'] ?? 0); $i++) {
            $entry = $entries[$i];

            $uid   = $entry['uid'][0]            ?? null;
            $cn    = $entry['cn'][0]             ?? $uid;
            $mail  = $entry['mail'][0]           ?? null;
            $title = $entry['title'][0]          ?? null;
            $ou    = $entry['ou'][0]             ?? null;
            $desc  = $entry['description'][0]    ?? null;
            $empNo = $entry['employeenumber'][0] ?? null;

            if (!$uid || !$mail) {
                $bar->advance();
                continue;
            }

            $isAdmin   = in_array($desc, ['admin', 'superadmin'], true);
            $adminType = match ($desc) {
                'superadmin' => 'super',
                'admin'      => 'app',
                default      => 'user',
            };

            User::updateOrCreate(
                ['ldap_uid' => $uid],
                [
                    'employee_no' => $empNo,
                    'name'        => $cn,
                    'email'       => $mail,
                    'title'       => $title,
                    'department'  => $ou,
                    'is_admin'    => $isAdmin,
                    'admin_type'  => $adminType,
                    // Mot de passe local inutilisé (auth via LDAP), on met un hash aléatoire.
                    'password'    => Hash::make(bin2hex(random_bytes(16))),
                ]
            );

            $count++;
            $bar->advance();
        }

        $bar->finish();
        $this->newLine(2);

        ldap_unbind($conn);

        $this->info("{$count} utilisateur(s) synchronisé(s) depuis LDAP.");
        return self::SUCCESS;
    }
}
