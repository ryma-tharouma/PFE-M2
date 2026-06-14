<?php

return [

    /*
    |--------------------------------------------------------------------------
    | Default Mailer
    |--------------------------------------------------------------------------
    | Lit MAIL_MAILER dans .env → 'smtp' pour Gmail
    */

    'default' => env('MAIL_MAILER', 'smtp'),

    /*
    |--------------------------------------------------------------------------
    | Mailer Configurations
    |--------------------------------------------------------------------------
    */

    'mailers' => [

        'smtp' => [
            'transport'  => 'smtp',
            'host'       => env('MAIL_HOST', 'smtp.gmail.com'),
            'port'       => env('MAIL_PORT', 587),
            'encryption' => env('MAIL_ENCRYPTION', 'tls'),
            'username'   => env('MAIL_USERNAME'),
            'password'   => env('MAIL_PASSWORD'),
            'timeout'    => 30,
            'local_domain' => env('MAIL_EHLO_DOMAIN'),
        ],

        // Utile en dev pour voir les mails dans le browser sans les envoyer
        'log' => [
            'transport' => 'log',
            'channel'   => env('MAIL_LOG_CHANNEL', 'stack'),
        ],

        // Pour tester sans rien envoyer (null driver)
        'array' => [
            'transport' => 'array',
        ],

    ],

    /*
    |--------------------------------------------------------------------------
    | Global "From" Address
    |--------------------------------------------------------------------------
    | Adresse expéditeur par défaut pour tous les mails envoyés par Laravel.
    | Doit correspondre au MAIL_USERNAME Gmail sinon Gmail peut rejeter.
    */

    'from' => [
        'address' => env('MAIL_FROM_ADDRESS', 'lizamezioug22@gmail.com'),
        'name'    => env('MAIL_FROM_NAME', 'Assistant IA Sonatrach'),
    ],

];
