<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="csrf-token" content="{{ csrf_token() }}">
    <title>@yield('title', 'Sonatrach Assistant IA')</title>

    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        sonatrach: {
                            orange:          '#F26522',
                            'orange-dark':   '#C94F1A',
                            'orange-light':  '#F5895A',
                            noir:            '#1A1A1A',
                            'noir-light':    '#2D2D2D',
                            'gris-fond':     '#F7F3EF',
                            'gris-bord':     '#E8DDD4',
                        }
                    },
                    fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] }
                }
            }
        }
    </script>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">

    {{-- Alpine.js --}}
    <script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>

    {{-- ❌ PUSHER + ECHO SUPPRIMÉS — on utilise WebSocket direct vers Python --}}

    <style>
        :root {
            --orange:      #F26522;
            --orange-dark: #C94F1A;
            --noir:        #1A1A1A;
            --gris-fond:   #F7F3EF;
            --gris-bord:   #E8DDD4;
        }
        body { font-family: 'Inter', sans-serif; }
        .scrollbar-thin::-webkit-scrollbar { width: 4px; }
        .scrollbar-thin::-webkit-scrollbar-track { background: transparent; }
        .scrollbar-thin::-webkit-scrollbar-thumb { background: var(--gris-bord); border-radius: 2px; }
        .scrollbar-thin::-webkit-scrollbar-thumb:hover { background: var(--orange); }
    </style>

    @stack('styles')
</head>
<body class="bg-sonatrach-gris-fond text-sonatrach-noir antialiased">
@yield('content')
@stack('scripts')
</body>
</html>
