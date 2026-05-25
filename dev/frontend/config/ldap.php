<?php

return [

    /*
    |--------------------------------------------------------------------------
    | Connexion au serveur LDAP
    |--------------------------------------------------------------------------
    | Pour l'environnement de test : localhost avec dc=sonatrach,dc=test
        | En production : remplacer par le DN de l'annuaire Sonatrach
    */

    'host'     => env('LDAP_HOST', 'localhost'),
    'port'     => (int) env('LDAP_PORT', 1389),
    'base_dn'  => env('LDAP_BASE_DN', 'dc=sonatrach,dc=test'),

    /*
    |--------------------------------------------------------------------------
    | Compte de service (lecture de l'annuaire)
    |--------------------------------------------------------------------------
    | Utilisé pour les recherches après un bind réussi.
    | En test avec OpenLDAP basique, on peut laisser vide.
    */
    'bind_dn'       => env('LDAP_BIND_DN',       'cn=admin,dc=sonatrach,dc=test'),
    'bind_password' => env('LDAP_BIND_PASSWORD',  ''),

    /*
    |--------------------------------------------------------------------------
    | Structure de l'annuaire
    |--------------------------------------------------------------------------
    */
    'users_ou'  => env('LDAP_USERS_OU',  'ou=users,dc=sonatrach,dc=test'),
    /*
    |--------------------------------------------------------------------------
    | Attributs mappés
    |--------------------------------------------------------------------------
    */
    'attributes' => [
        'username'    => 'uid',             // ou 'sAMAccountName' en prod AD
        'name'        => 'displayName',
        'email'       => 'mail',
        'title'       => 'title',
        'department'  => 'ou',
        'phone'       => 'telephoneNumber',
    ],

    /*
    |--------------------------------------------------------------------------
    | Groupe administrateurs
    |--------------------------------------------------------------------------
    | CN du groupe LDAP dont les membres ont accès au panneau d'administration.
    */
    'admin_group' => env('LDAP_ADMIN_GROUP', 'admins'),

    /*
    |--------------------------------------------------------------------------
    | Options techniques
    |--------------------------------------------------------------------------
    */
    'timeout'  => (int) env('LDAP_TIMEOUT', 5),
    'use_ssl'  => (bool) env('LDAP_USE_SSL',  false),
    'use_tls'  => (bool) env('LDAP_USE_TLS',  false),
    'version'  => 3,
];
