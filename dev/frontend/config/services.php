<?php
return [
    'postmark' => [
        'key' => env('POSTMARK_API_KEY'),
    ],
    'resend' => [
        'key' => env('RESEND_API_KEY'),
    ],
    'ses' => [
        'key'    => env('AWS_ACCESS_KEY_ID'),
        'secret' => env('AWS_SECRET_ACCESS_KEY'),
        'region' => env('AWS_DEFAULT_REGION', 'us-east-1'),
    ],
    'slack' => [
        'notifications' => [
            'bot_user_oauth_token' => env('SLACK_BOT_USER_OAUTH_TOKEN'),
            'channel'              => env('SLACK_BOT_USER_DEFAULT_CHANNEL'),
        ],
    ],
    'chatbot' => [
        'url'     => env('PYTHON_API_URL', 'http://127.0.0.1:8000'),
        'ws_url'  => env('PYTHON_WS_URL',  'ws://127.0.0.1:8000/ws/chat'),
        'timeout' => env('PYTHON_API_TIMEOUT', 30),
    ],

    // ── Backend API (FastAPI pour FAQ et chats) ────────────────────────
    'backend' => [
        'url' => env('BACKEND_API_URL', 'http://127.0.0.1:8000'),
    ],
    'extract' => [
        'python_bin'    => env('EXTRACT_PYTHON_BIN',     '/var/www/PFE_M2/PFE-M2/extract/venv_docling/bin/python3'),
        'extract_dir'   => env('EXTRACT_DIR',            base_path('../../extract/app')),
        'manuals_dir'   => env('EXTRACT_MANUALS_DIR',    base_path('../../extract/app/manuels')),
        'json_dir'      => env('EXTRACT_JSON_DIR',       base_path('../../extract/app/json')),
        'max_upload_kb' => env('EXTRACT_MAX_UPLOAD_KB',  512000),
        'timeout'       => env('EXTRACT_TIMEOUT',        1800),
    ],

    // ── Qdrant vector store ───────────────────────────────────────────
    'qdrant' => [
        'url' => env('QDRANT_URL', 'http://127.0.0.1:6333'),
    ],

    // ── GLPI ticket system ─────────────────────────────────────────────
    'glpi' => [
        'url'            => env('GLPI_URL', 'http://localhost:8080'),
        'api_token'      => env('GLPI_API_TOKEN', '5QXljqcvwEC4vMOsuOyWyWKgTNAypkDkVZ3ceMS7'),
        'app_token'      => env('GLPI_APP_TOKEN', 'XY12O6dDRNAXLFyIELY7aiCibxuWIQHAOlFA8Zps'),
        'webhook_secret' => env('GLPI_WEBHOOK_SECRET', ''),
    ],
];
