@extends('layouts.app')

@section('title', 'Assistant IA — Sonatrach')

@push('styles')
    <style>
        html, body { height: 100%; overflow: hidden; }

        @keyframes fadeSlideIn { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }
        .msg-animate { animation: fadeSlideIn 0.25s ease-out; }

        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
        .cursor-blink::after {
            content:'▍'; display:inline-block;
            animation:blink 0.6s step-end infinite;
            color:#F26522; font-size:0.85em; margin-left:2px; vertical-align:text-bottom;
        }

        .bot-content { line-height:1.65; }
        .bot-content p { margin:0 0 0.5em; }
        .bot-content p:last-child { margin-bottom:0; }
        .bot-content ul,.bot-content ol { margin:0.4em 0 0.4em 1.2em; }
        .bot-content li { margin-bottom:0.2em; }
        .bot-content strong { font-weight:600; }
        .bot-content code { background:rgba(0,0,0,0.06); border-radius:4px; padding:1px 5px; font-size:0.85em; font-family:ui-monospace,monospace; }
        .bot-content pre { background:#1e1e2e; color:#cdd6f4; border-radius:8px; padding:12px; overflow-x:auto; font-size:0.82em; margin:0.5em 0; }
        .bot-content pre code { background:none; padding:0; color:inherit; }
        .bot-content h1,.bot-content h2,.bot-content h3 { font-weight:600; margin:0.6em 0 0.3em; }
        .bot-content table { border-collapse:collapse; width:100%; font-size:0.88em; margin:0.5em 0; }
        .bot-content th,.bot-content td { border:1px solid rgba(0,0,0,0.12); padding:5px 10px; }
        .bot-content th { background:rgba(0,0,0,0.05); font-weight:600; }
        .bot-content blockquote { border-left:3px solid #F26522; margin:0.4em 0; padding-left:10px; color:#666; }

        @keyframes pulse { 0%,100%{opacity:.4} 50%{opacity:1} }
        .thinking-dots span { display:inline-block; width:6px; height:6px; border-radius:50%; background:#F26522; margin:0 2px; animation:pulse 1.2s ease-in-out infinite; }
        .thinking-dots span:nth-child(2) { animation-delay:.2s; }
        .thinking-dots span:nth-child(3) { animation-delay:.4s; }

        .app-select { appearance:none; background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23F26522' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E"); background-repeat:no-repeat; background-position:right 10px center; padding-right:2rem; }
        .bot-avatar { width:28px; height:28px; border-radius:50%; object-fit:cover; flex-shrink:0; }
        .ttft-bar { height:2px; background:linear-gradient(90deg,#F26522,#f9a97e); border-radius:1px; animation:ttft-grow 30s linear forwards; }
        @keyframes ttft-grow { from{width:0%} to{width:90%} }

        .conv-item { transition: background .15s; }
        .conv-item:hover { background: #ede8e3; }
        .conv-item.active { background: #ede8e3; border-left: 3px solid #F26522; }
        .conv-item .group { display: flex; align-items: center; }
        .conv-item:hover .group-hover\:opacity-100 { opacity: 1 !important; }

        .msg-action-btn { display:inline-flex; align-items:center; justify-content:center; width:26px; height:26px; border-radius:6px; color:#F26522; background:transparent; border:none; cursor:pointer; transition:background .15s, transform .1s; }
        .msg-action-btn:hover { background: rgba(242,101,34,0.12); }
        .msg-action-btn:active { transform: scale(0.92); }
    </style>
@endpush

@section('content')
    <div class="flex h-screen" x-data="chatApp()" x-init="init()">

        {{-- ══ SIDEBAR ══════════════════════════════════════════════════ --}}
        <aside class="w-64 bg-white border-r border-sonatrach-gris-bord flex flex-col" x-show="sidebarOpen">

            {{-- Logo --}}
            <div class="p-4 border-b border-sonatrach-gris-bord flex items-center justify-between">
                <img src="{{ asset('assets/images/sonatrach-logo.png') }}" alt="Sonatrach" class="h-7">
                <button @click="startNewConversation()"
                        title="Nouvelle conversation"
                        class="w-7 h-7 rounded-lg flex items-center justify-center text-sonatrach-orange
                           border border-sonatrach-orange hover:bg-sonatrach-orange hover:text-white transition-colors">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
                    </svg>
                </button>
            </div>

            {{-- Liste des conversations --}}
            <div class="flex-1 overflow-y-auto py-2">
                <template x-if="conversations.length === 0">
                    <div class="px-4 py-8 text-center text-xs text-gray-400">
                        <p>Aucune conversation</p>
                        <p class="mt-1">Posez votre première question !</p>
                    </div>
                </template>

                <template x-for="conv in activeConversations" :key="conv.id">
                    <div class="conv-item w-full flex items-start gap-2 px-3 py-2.5 group relative"
                         :class="conv.id === currentConvId ? 'active' : ''">
                        <button @click="loadConversation(conv.id)"
                                class="flex-1 flex items-start gap-2 text-left">
                            <div class="flex-shrink-0 w-7 h-7 rounded-md flex items-center justify-center text-white text-xs font-bold mt-0.5"
                                 :style="`background:${conv.app_color || '#F26522'}`"
                                 x-text="conv.app_icon || '?'"></div>
                            <div class="flex-1 min-w-0">
                                <p class="text-xs font-medium truncate text-sonatrach-noir"
                                   x-text="conv.title || 'Conversation'"></p>
                                <p class="text-xs text-gray-400 truncate" x-text="conv.app_name || ''"></p>
                            </div>
                        </button>

                        <div class="flex-shrink-0 relative" @click.stop x-data="{ menuOpen: false }">
                            <button @click="menuOpen = !menuOpen"
                                    class="w-6 h-6 flex items-center justify-center rounded hover:bg-gray-200 opacity-0 group-hover:opacity-100 transition-opacity"
                                    title="Options">
                                <svg class="w-4 h-4 text-gray-400" fill="currentColor" viewBox="0 0 24 24">
                                    <path d="M12 8c1.1 0 2-0.9 2-2s-0.9-2-2-2-2 0.9-2 2 0.9 2 2 2zm0 2c-1.1 0-2 0.9-2 2s0.9 2 2 2 2-0.9 2-2-0.9-2-2-2zm0 6c-1.1 0-2 0.9-2 2s0.9 2 2 2 2-0.9 2-2-0.9-2-2-2z"/>
                                </svg>
                            </button>
                            <template x-if="menuOpen">
                                <div class="absolute right-0 top-full mt-1 bg-white rounded-lg shadow-lg border border-gray-200 z-10 w-40"
                                     @click.away="menuOpen = false">
                                    <button @click="deleteConversation(conv.id); menuOpen = false"
                                            class="w-full px-4 py-2.5 text-left text-xs text-red-600 hover:bg-red-50 rounded-lg flex items-center gap-2">
                                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                                        </svg>
                                        <span>Supprimer</span>
                                    </button>
                                </div>
                            </template>
                        </div>
                    </div>
                </template>
                <template x-if="archivedConversations.length > 0">
                    <div class="mt-2 pt-2 border-t border-sonatrach-gris-bord">
                        <p class="px-3 py-2 text-[10px] font-semibold text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
                            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 8h14M5 8a2 2 0 01-2-2V4a2 2 0 012-2h14a2 2 0 012 2v2a2 2 0 01-2 2M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4"/></svg>
                            Archivées
                        </p>
                        <template x-for="conv in archivedConversations" :key="conv.id">
                            <div class="conv-item w-full flex items-start gap-2 px-3 py-2.5 opacity-60"
                                 :class="conv.id === currentConvId ? 'active' : ''">
                                <button @click="loadConversation(conv.id)" class="flex-1 flex items-start gap-2 text-left">
                                    <div class="flex-shrink-0 w-7 h-7 rounded-md flex items-center justify-center text-white text-xs font-bold mt-0.5"
                                         style="background:#9CA3AF"
                                         x-text="conv.app_icon || '?'"></div>
                                    <div class="flex-1 min-w-0">
                                        <p class="text-xs font-medium truncate text-sonatrach-noir" x-text="conv.title || 'Conversation'"></p>
                                        <p class="text-xs text-gray-400 truncate" x-text="(conv.app_name || '') + ' · Archivée'"></p>
                                    </div>
                                </button>
                            </div>
                        </template>
                    </div>
                </template>
            </div>

            {{-- Utilisateur connecté + Logout --}}
            <div class="border-t border-sonatrach-gris-bord p-3 flex items-center gap-2">
                <div class="w-8 h-8 rounded-full bg-sonatrach-orange flex items-center justify-center text-white text-xs font-bold flex-shrink-0"
                     x-text="userInitials"></div>
                <div class="flex-1 min-w-0">
                    <p class="text-xs font-semibold text-sonatrach-noir truncate" x-text="userName"></p>
                    <p class="text-xs text-gray-400 truncate" x-text="userRole"></p>
                </div>
                <form method="POST" action="{{ route('auth.logout') }}">
                    @csrf
                    <button type="submit" title="Se déconnecter"
                            class="w-7 h-7 rounded-lg flex items-center justify-center text-gray-400
                               hover:text-red-500 hover:bg-red-50 transition-colors">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                  d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h6a2 2 0 012 2v1"/>
                        </svg>
                    </button>
                </form>
            </div>
        </aside>

        {{-- ══ MAIN ══════════════════════════════════════════════════════ --}}
        <main class="flex-1 flex flex-col min-w-0">

            {{-- Header --}}
            <header class="flex items-center justify-between px-4 py-3 border-b border-sonatrach-gris-bord bg-white flex-shrink-0">
                <div class="flex items-center gap-3">
                    <button @click="sidebarOpen = !sidebarOpen" class="text-gray-400 hover:text-gray-600">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
                        </svg>
                    </button>

                    {{--
                        Select des applications :
                        - Affiche exactement le nom tel que l'admin l'a saisi (app->name)
                        - La valeur envoyée est app->id (clé DB)
                        - Une seule entrée par application (pas de doublons)
                    --}}
                    <select x-model="selectedApp" @change="onAppChange()"
                            class="app-select text-sm border border-sonatrach-gris-bord rounded-lg px-3 py-1.5
                               focus:outline-none focus:ring-2 focus:ring-sonatrach-orange bg-white text-sonatrach-noir">
                        <option value="">— Choisir une application —</option>
                        @foreach($applications as $app)
                            <option value="{{ $app->id }}">{{ $app->name }}</option>
                        @endforeach
                    </select>
                </div>
                <div class="flex items-center gap-3">
                    <button @click="openTicketModal()"
                            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                               border border-sonatrach-orange text-sonatrach-orange
                               hover:bg-sonatrach-orange hover:text-white transition-colors">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
                        </svg>
                        Créer un ticket
                    </button>
                </div>
            </header>

            {{-- Zone messages --}}
            <div class="flex-1 overflow-y-auto scrollbar-thin px-4 py-6 space-y-6" x-ref="messagesContainer">

                {{-- Écran d'accueil : aucune app sélectionnée --}}
                <template x-if="messages.length === 0 && !selectedApp">
                    <div class="flex flex-col items-center justify-center h-full text-center px-4">
                        <img src="{{ asset('assets/images/icon.jpg') }}" class="w-20 h-20 rounded-full object-cover shadow-md mb-5">
                        <h2 class="text-xl font-semibold text-sonatrach-noir mb-2">Bienvenue dans l'Assistant IA Sonatrach</h2>
                        <p class="text-gray-500 text-sm max-w-md">
                            Sélectionnez l'application concernée dans le menu ci-dessus et je vous assiste.
                        </p>
                    </div>
                </template>

                {{-- Écran d'accueil : app sélectionnée, pas encore de messages --}}
                <template x-if="messages.length === 0 && selectedApp">
                    <div class="flex flex-col items-center justify-center h-full text-center">
                        <img src="{{ asset('assets/images/icon.jpg') }}" class="w-14 h-14 rounded-full object-cover shadow-md mb-4">
                        <h3 class="text-lg font-medium text-sonatrach-noir mb-1" x-text="currentApp?.name || 'Application'"></h3>
                        <p class="text-sm text-gray-400">Posez votre question, je vous assiste.</p>
                    </div>
                </template>

                <template x-for="msg in messages" :key="msg.id">
                    <div class="flex gap-3 msg-animate" :class="msg.role==='user' ? 'flex-row-reverse' : 'flex-row'">

                        <template x-if="msg.role==='user'">
                            <div class="flex-shrink-0 w-7 h-7 rounded-full bg-sonatrach-orange flex items-center justify-center text-xs font-bold text-white"
                                 x-text="userInitials"></div>
                        </template>
                        <template x-if="msg.role==='assistant'">
                            <img src="{{ asset('assets/images/icon.jpg') }}" class="bot-avatar">
                        </template>

                        <div class="max-w-2xl w-full" :class="msg.role==='user' ? 'items-end flex flex-col' : 'items-start'">

                            <template x-if="msg.role==='user'">
                                <div class="px-4 py-3 rounded-2xl text-sm leading-relaxed bg-sonatrach-orange text-white rounded-tr-sm"
                                     x-text="msg.content"></div>
                            </template>

                            <template x-if="msg.role==='assistant'">
                                <div>
                                    <template x-if="msg.thinking">
                                        <div class="px-4 py-3 rounded-2xl text-sm bg-sonatrach-gris-fond border border-sonatrach-gris-bord rounded-tl-sm">
                                            <div class="flex items-center gap-2 text-gray-400 text-xs mb-1">
                                                <div class="thinking-dots"><span></span><span></span><span></span></div>
                                                <span>Analyse en cours</span>
                                                <span x-text="msg.elapsed ? `· ${msg.elapsed}s` : ''" class="tabular-nums"></span>
                                            </div>
                                            <div class="ttft-bar mt-2"></div>
                                        </div>
                                    </template>

                                    <template x-if="!msg.thinking">
                                        <div class="px-4 py-3 rounded-2xl text-sm bg-sonatrach-gris-fond border border-sonatrach-gris-bord rounded-tl-sm bot-content"
                                             :class="msg.streaming ? 'cursor-blink' : ''"
                                             x-html="msg.html"></div>
                                    </template>

                                    <template x-if="msg.sources && msg.sources.length > 0">
                                        <div class="mt-2 px-1">
                                            <details class="text-xs text-gray-400">
                                                <summary class="cursor-pointer hover:text-sonatrach-orange">
                                                    📚 <span x-text="msg.sources.length"></span> source(s)
                                                </summary>
                                                <ul class="mt-1 space-y-0.5 pl-3">
                                                    <template x-for="src in msg.sources" :key="src.breadcrumb || src.source">
                                                        <li x-text="src.breadcrumb || src.source || '?'"></li>
                                                    </template>
                                                </ul>
                                            </details>
                                        </div>
                                    </template>

                                    <template x-if="!msg.thinking && !msg.streaming">
                                        <div class="flex items-center gap-1 mt-1.5 px-1">
                                            <button @click="copyMessage(msg)" class="msg-action-btn"
                                                    :title="copiedMsgId === msg.id ? 'Copié !' : 'Copier la réponse'">
                                                <template x-if="copiedMsgId !== msg.id">
                                                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/>
                                                    </svg>
                                                </template>
                                                <template x-if="copiedMsgId === msg.id">
                                                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                                                    </svg>
                                                </template>
                                            </button>
                                            <button @click="downloadMessagePdf(msg)" class="msg-action-btn" title="Télécharger en PDF">
                                                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5 5-5M12 15V3"/>
                                                </svg>
                                            </button>
                                        </div>
                                    </template>
                                </div>
                            </template>

                            <p class="text-xs text-gray-400 mt-1 px-1"
                               :class="msg.role==='user' ? 'text-right' : 'text-left'"
                               x-text="msg.time"></p>
                        </div>
                    </div>
                </template>
            </div>

            {{-- Barre de saisie --}}
            <div class="border-t border-sonatrach-gris-bord bg-white px-4 py-3 flex-shrink-0" x-show="!viewingArchived">
                <div class="max-w-3xl mx-auto">
                    <template x-if="!selectedApp">
                        <p class="text-xs text-center text-gray-400 mb-2">Sélectionnez une application pour commencer</p>
                    </template>
                    <div class="flex items-end gap-2 bg-sonatrach-gris-fond rounded-xl border border-sonatrach-gris-bord
                            focus-within:border-sonatrach-orange focus-within:ring-2 focus-within:ring-sonatrach-orange/20
                            transition-all px-4 py-2">
                    <textarea x-model="inputMessage"
                              @keydown.enter.prevent="handleEnterKey($event)"
                              :disabled="!selectedApp || isLoading"
                              rows="1" placeholder="Décrivez votre problème..."
                              class="flex-1 bg-transparent text-sm text-sonatrach-noir placeholder-gray-400
                                     resize-none outline-none max-h-32 disabled:opacity-40 disabled:cursor-not-allowed"
                              style="min-height:24px"
                              @input="autoResize($el)"></textarea>
                        <button @click="sendMessage()" :disabled="!selectedApp || !inputMessage.trim() || isLoading"
                                class="flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center
                                   bg-sonatrach-orange text-white hover:bg-sonatrach-orange-dark
                                   disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                            <template x-if="!isLoading">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/>
                                </svg>
                            </template>
                            <template x-if="isLoading">
                                <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                                </svg>
                            </template>
                        </button>
                    </div>
                    <p class="text-xs text-center text-gray-400 mt-2">Entrée pour envoyer · Maj+Entrée pour nouvelle ligne</p>
                </div>
            </div>

            <template x-if="viewingArchived">
                <div class="border-t border-sonatrach-gris-bord bg-sonatrach-gris-fond px-4 py-3 flex-shrink-0 text-center">
                    <p class="text-xs text-gray-500 flex items-center justify-center gap-1.5">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 8h14M5 8a2 2 0 01-2-2V4a2 2 0 012-2h14a2 2 0 012 2v2a2 2 0 01-2 2M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4"/></svg>
                        Conversation archivée (application supprimée) — lecture seule
                    </p>
                </div>
            </template>
        </main>

        {{-- ══ MODAL SUGGESTION TICKET ════════════════════════════ --}}
        <template x-if="suggestTicketModalOpen">
            <div class="fixed inset-0 z-50 flex items-center justify-center px-4" style="background:rgba(0,0,0,0.45)">
                <div class="bg-white rounded-2xl shadow-xl w-full max-w-md p-6" @click.stop>
                    <div class="mb-4">
                        <h2 class="text-lg font-semibold text-sonatrach-noir mb-2">Créer un ticket de support ?</h2>
                        <p class="text-sm text-gray-600">
                            Le chatbot n'a pas pu répondre à votre question. Souhaitez-vous créer un ticket pour qu'un assistant humain vous aide ?
                        </p>
                    </div>
                    <div class="flex gap-3">
                        <button @click="dismissTicketSuggestion()"
                                class="flex-1 py-2.5 rounded-lg text-sm font-medium border border-sonatrach-gris-bord text-gray-600 hover:bg-gray-50">
                            Non
                        </button>
                        <button @click="acceptTicketSuggestion()"
                                class="flex-1 py-2.5 rounded-lg text-sm font-semibold text-white bg-sonatrach-orange hover:bg-sonatrach-orange-dark">
                            Oui
                        </button>
                    </div>
                </div>
            </div>
        </template>

        {{-- ══ MODAL TICKET ══════════════════════════════════════════════ --}}
        <template x-if="ticketModalOpen">
            <div class="fixed inset-0 z-50 flex items-center justify-center px-4" style="background:rgba(0,0,0,0.45)">
                <div class="bg-white rounded-2xl shadow-xl w-full max-w-lg p-6" @click.stop>
                    <div class="flex items-center justify-between mb-5">
                        <h2 class="text-base font-semibold text-sonatrach-noir">Créer un ticket GLPI</h2>
                        <button @click="ticketModalOpen=false" class="text-gray-400 hover:text-gray-600">
                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                            </svg>
                        </button>
                    </div>
                    <div class="space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Titre</label>
                            <input type="text" x-model="ticket.title" placeholder="Résumé du problème"
                                   class="w-full px-3 py-2 text-sm border border-sonatrach-gris-bord rounded-lg focus:outline-none focus:ring-2 focus:ring-sonatrach-orange">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Catégorie</label>
                            <select x-model="ticket.category" class="app-select w-full px-3 py-2 text-sm border border-sonatrach-gris-bord rounded-lg focus:outline-none focus:ring-2 focus:ring-sonatrach-orange bg-white">
                                <option value="">— Sélectionner —</option>
                                <option value="incident">Incident</option>
                                <option value="demande">Demande de service</option>
                                <option value="question">Question</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Priorité</label>
                            <div class="flex gap-2">
                                <template x-for="p in ['Basse','Moyenne','Haute','Critique']" :key="p">
                                    <button type="button" @click="ticket.priority=p"
                                            class="flex-1 py-1.5 rounded-lg text-xs font-medium border transition-colors"
                                            :class="ticket.priority===p ? 'bg-sonatrach-orange text-white border-sonatrach-orange' : 'border-sonatrach-gris-bord text-gray-600 hover:border-sonatrach-orange'"
                                            x-text="p"></button>
                                </template>
                            </div>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Description</label>
                            <textarea x-model="ticket.description" rows="4" placeholder="Décrivez le problème en détail..."
                                      class="w-full px-3 py-2 text-sm border border-sonatrach-gris-bord rounded-lg focus:outline-none focus:ring-2 focus:ring-sonatrach-orange resize-none"></textarea>
                        </div>
                    </div>
                    <div class="flex gap-3 mt-6">
                        <button @click="ticketModalOpen=false" class="flex-1 py-2 rounded-lg text-sm font-medium border border-sonatrach-gris-bord text-gray-600 hover:bg-gray-50">Annuler</button>
                        <button @click="submitTicket()" :disabled="!ticket.title || !ticket.category || ticketLoading"
                                class="flex-1 py-2 rounded-lg text-sm font-semibold text-white bg-sonatrach-orange hover:bg-sonatrach-orange-dark disabled:opacity-50 flex items-center justify-center gap-2">
                            <svg x-show="ticketLoading" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                            </svg>
                            <span x-text="ticketLoading ? 'Envoi...' : 'Envoyer vers GLPI'"></span>
                        </button>
                    </div>
                </div>
            </div>
        </template>
    </div>
@endsection

@php
    if (Auth::check()) {
        $userName     = auth()->user()->display_name;
        $userRole     = auth()->user()->is_admin ? 'Super Admin' : (auth()->user()->title ?? '');
        $userInitials = strtoupper(substr($userName, 0, 2));
    } else {
        $userName     = session('user_name', 'Utilisateur');
        $userRole     = session('is_admin', false) ? 'Super Admin' : session('user_title', '');
        $userInitials = strtoupper(substr($userName, 0, 2));
    }
@endphp

@push('scripts')
    <script src="https://cdnjs.cloudflare.com/ajax/libs/marked/9.1.6/marked.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
    <script>
        marked.setOptions({ breaks: true, gfm: true });
        function renderMarkdown(t) { return t ? marked.parse(t) : ''; }

        function chatApp() {
            return {
                sidebarOpen:   true,
                selectedApp:   '',
                currentApp:    null,
                viewingArchived: false,

                get activeConversations() {
                    return this.conversations.filter(c => !c.archived);
                },
                get archivedConversations() {
                    return this.conversations.filter(c => c.archived);
                },
                inputMessage:  '',
                isLoading:     false,
                messages:      [],
                conversations: @json($conversations ?? []),
                currentConvId: null,
                userName:      @json($userName),
                userRole:      @json($userRole),
                userInitials:  @json($userInitials),

                /*
                 * applications : liste injectée depuis le contrôleur Laravel.
                 * Chaque objet contient { id, name, collection, color, icon, ... }
                 * Le "name" est exactement ce que l'admin a saisi.
                 * Le "collection" est le nom de la collection Qdrant correspondante.
                 */
                applications:  @json($applications ?? []),

                copiedMsgId:        null,
                pdfDownloadCounter: 0,

                ticketModalOpen: false,
                ticketLoading:   false,
                ticket: { title:'', category:'', priority:'Moyenne', description:'' },

                 // Modal pour proposer création de ticket après non-réponse
                 suggestTicketModalOpen: false,
                 lastUnanswerableQuestion: '',
                 lastUnanswerableManual: '',

                init() {
                    const currentUserId = @json(Auth::id() ?? null);
                    const storageKey = `sonatrach_convs_${currentUserId}`;

                    if (this.conversations.length === 0 && currentUserId) {
                        const s = localStorage.getItem(storageKey);
                        if (s) { try { this.conversations = JSON.parse(s); } catch(e){} }
                    }

                    // Nettoyer les clés localStorage des autres utilisateurs
                    for (let key in localStorage) {
                        if (key.startsWith('sonatrach_convs_') && key !== storageKey) {
                            localStorage.removeItem(key);
                        }
                    }

                    this.refreshConversations();
                },

                async refreshConversations() {
                    try {
                        const res = await fetch('/chat/conversations', {
                            headers: { 'X-Requested-With': 'XMLHttpRequest' }
                        });
                        const data = await res.json();
                        if (data.conversations) {
                            this.conversations = data.conversations;
                            const currentUserId = @json(Auth::id() ?? null);
                            localStorage.setItem(`sonatrach_convs_${currentUserId}`, JSON.stringify(data.conversations));
                        }
                    } catch(e) {
                        console.warn('Could not refresh conversations', e);
                    }
                },

                onAppChange() {
                    if (!this.selectedApp) { this.currentApp = null; return; }
                    this.currentApp = this.applications.find(a => String(a.id) === String(this.selectedApp)) || null;

                    const currentConv = this.conversations.find(c => String(c.id) === String(this.currentConvId));
                    if (currentConv && String(currentConv.app_id) === String(this.selectedApp)) return;

                    this.openNewConversation();
                },

                startNewConversation() {
                    if (!this.selectedApp) return;
                    this.openNewConversation();
                },

                openNewConversation() {
                    this.messages      = [];
                    this.currentConvId = null;
                    this.viewingArchived = false;
                },

                loadConversation(id) {
                    if (this.currentConvId === id) return;

                    this.currentConvId = id;
                    const conv = this.conversations.find(c => c.id === id);
                    this.viewingArchived = !!(conv && conv.archived);
                    if (conv) {
                        this.selectedApp = this.viewingArchived ? '' : String(conv.app_id);
                        this.currentApp  = this.viewingArchived ? null : (this.applications.find(a => String(a.id) === String(conv.app_id)) || null);
                    }

                    fetch(`/chat/conversation/${id}`, { headers:{'X-Requested-With':'XMLHttpRequest'} })
                        .then(r => r.json())
                        .then(data => {
                            this.messages = (data.messages || []).map(m => ({
                                ...m,
                                html:      m.role === 'assistant' ? renderMarkdown(m.content) : m.content,
                                thinking:  false,
                                streaming: false,
                            }));
                            this.$nextTick(() => this.scrollBottom());
                        })
                        .catch(() => { this.messages = []; });
                },

                async sendMessage() {
                    const text = this.inputMessage.trim();
                    if (!text || !this.selectedApp || this.isLoading || this.viewingArchived) return;

                    this.messages.push({
                        id: Date.now(), role: 'user', content: text,
                        html: '', thinking: false, streaming: false, time: this.formatTime(),
                    });
                    this.inputMessage = '';
                    this.isLoading    = true;
                    this.$nextTick(() => this.scrollBottom());

                    const botMsgId = Date.now() + 1;
                    this.messages.push({
                        id: botMsgId, role: 'assistant', content: '', html: '',
                        thinking: true, streaming: false, elapsed: 0, sources: [], time: this.formatTime(),
                    });
                    this.$nextTick(() => this.scrollBottom());

                    const startAt = Date.now();
                    const timer   = setInterval(() => {
                        const idx = this.messages.findIndex(m => m.id === botMsgId);
                        if (idx !== -1 && this.messages[idx].thinking) {
                            this.messages[idx].elapsed = Math.floor((Date.now() - startAt) / 1000);
                        } else { clearInterval(timer); }
                    }, 1000);

                    try {
                        // 1. Init Laravel → récupère ws_url, user_id, collection (nom Qdrant exact)
                        const initRes  = await fetch('/chat/message/init', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').content,
                                'X-Requested-With': 'XMLHttpRequest',
                            },
                            body: JSON.stringify({
                                message:         text,
                                app_id:          this.selectedApp,   // ID de l'app en DB
                                conversation_id: this.currentConvId,
                            }),
                        });
                        const initData = await initRes.json();
                        if (!initData.success) throw new Error(initData.error || 'Erreur init');

                        const isNewConv = !this.currentConvId || this.currentConvId !== initData.conversation_id;
                        this.currentConvId = initData.conversation_id;

                        if (isNewConv) {
                            const existing = this.conversations.find(c => c.id === initData.conversation_id);
                            if (!existing) {
                                this.conversations.unshift({
                                    id:        initData.conversation_id,
                                    app_id:    this.selectedApp,
                                    app_name:  this.currentApp?.name  || 'App',
                                    app_color: this.currentApp?.color || '#F26522',
                                    app_icon:  this.currentApp?.icon  || '📄',
                                    title:     text.substring(0, 50),
                                });
                            }
                        }

                        // 2. WebSocket → Python
                        // initData.collection contient le nom de la collection Qdrant
                        // tel qu'il est stocké en DB (ex: "manuel_parc_auto_cleaned")
                        const streamData = await this.streamDirect({
                            wsUrl:      initData.ws_url,
                            userId:     initData.user_id,
                            collection: initData.collection,   // ← nom exact Qdrant depuis Laravel
                            message:    text,
                            botMsgId,
                        });

                         // 3. Finalize Laravel
                         const responseTimeSec = (Date.now() - startAt) / 1000;
                         if ((streamData.response || '').trim()) {
                             await fetch('/chat/message/finalize', {
                                 method: 'POST',
                                 headers: {
                                     'Content-Type': 'application/json',
                                     'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').content,
                                     'X-Requested-With': 'XMLHttpRequest',
                                 },
                                 body: JSON.stringify({
                                     conversation_id:    this.currentConvId,
                                     response:           streamData.response,
                                     sources:            streamData.sources,
                                     collection:         initData.collection,
                                     asked_at:           initData.asked_at,
                                     response_time_sec:  responseTimeSec,
                                 }),
                             });

                             // ━━ Vérifier si le bot ne peut pas répondre ━━
                             if (streamData.response.includes('Je ne peux pas répondre à cette question')) {
                                 this.lastUnanswerableQuestion = text;
                                 this.lastUnanswerableManual = this.currentApp?.name || 'Application';
                                 this.suggestTicketModalOpen = true;
                             }
                         }

                        const ce = this.conversations.find(c => c.id === this.currentConvId);
                        if (ce && (!ce.title || ce.title === 'Nouvelle conversation')) {
                            ce.title = text.substring(0, 50) + (text.length > 50 ? '…' : '');
                        }

                        await this.refreshConversations();

                    } catch(err) {
                        clearInterval(timer);
                        const idx = this.messages.findIndex(m => m.id === botMsgId);
                        if (idx !== -1) {
                            this.messages[idx].thinking  = false;
                            this.messages[idx].streaming = false;
                            this.messages[idx].content   = 'Erreur de connexion. Veuillez réessayer.';
                            this.messages[idx].html      = '<em style="color:#cc4444">Erreur de connexion. Veuillez réessayer.</em>';
                        }
                        console.error('Chat error:', err);
                    } finally {
                        clearInterval(timer);
                        const idx = this.messages.findIndex(m => m.id === botMsgId);
                        if (idx !== -1) {
                            this.messages[idx].thinking  = false;
                            this.messages[idx].streaming = false;
                        }
                        this.isLoading = false;
                        this.$nextTick(() => this.scrollBottom());
                    }
                },

                streamDirect({ wsUrl, userId, collection, message, botMsgId }) {
                    return new Promise((resolve, reject) => {
                        let rawText = '', sources = [], done = false;

                        const ws = new WebSocket(wsUrl);

                        ws.onopen = () => {
                            ws.send(JSON.stringify({ user_id: userId, message, collection, max_turns: 1 }));
                        };

                        ws.onmessage = ({ data }) => {
                            let p; try { p = JSON.parse(data); } catch(_) { return; }

                            if (p.type === 'typing') return;

                            if (p.type === 'token' || p.type === 'chunk') {
                                const token = String(p.text || '');
                                if (!token) return;
                                rawText += token;

                                const idx = this.messages.findIndex(m => m.id === botMsgId);
                                if (idx !== -1) {
                                    this.messages[idx].thinking  = false;
                                    this.messages[idx].streaming = true;
                                    this.messages[idx].content   = rawText;
                                    this.messages[idx].html      = renderMarkdown(rawText);
                                }
                                this.$nextTick(() => this.scrollBottom());
                                return;
                            }

                            if (p.type === 'done') {
                                done    = true;
                                sources = Array.isArray(p.sources) ? p.sources : [];
                                const idx = this.messages.findIndex(m => m.id === botMsgId);
                                if (idx !== -1) {
                                    this.messages[idx].sources   = sources;
                                    this.messages[idx].streaming = false;
                                }
                                ws.close();
                                return;
                            }

                            if (p.type === 'error') {
                                ws.close();
                                reject(new Error(p.error || 'Erreur backend'));
                            }
                        };

                        ws.onerror = () => reject(new Error('WebSocket connexion échouée — Python est-il lancé ?'));

                        ws.onclose = () => {
                            const idx = this.messages.findIndex(m => m.id === botMsgId);
                            if (idx !== -1) {
                                this.messages[idx].streaming = false;
                                this.messages[idx].thinking  = false;
                            }
                            if (done || rawText) resolve({ response: rawText, sources });
                            else reject(new Error('Connexion interrompue sans réponse'));
                        };
                    });
                },

                handleEnterKey(e) { if (!e.shiftKey) this.sendMessage(); },

                copyMessage(msg) {
                    if (!msg || !msg.content) return;
                    navigator.clipboard.writeText(msg.content).then(() => {
                        this.copiedMsgId = msg.id;
                        setTimeout(() => {
                            if (this.copiedMsgId === msg.id) this.copiedMsgId = null;
                        }, 2000);
                    }).catch(() => {
                        alert('Impossible de copier la réponse.');
                    });
                },

                downloadMessagePdf(msg) {
                    if (!msg || !msg.content) return;

                    const rawAppName  = (this.currentApp && this.currentApp.name) ? this.currentApp.name : 'App';
                    const safeAppName = rawAppName.trim().replace(/\s+/g, '_').replace(/[^a-zA-Z0-9_\-]/g, '');
                    this.pdfDownloadCounter += 1;
                    const filename = `${safeAppName || 'App'}_help_${this.pdfDownloadCounter}.pdf`;

                    const { jsPDF } = window.jspdf;
                    const doc = new jsPDF({ unit: 'pt', format: 'a4' });

                    const marginX   = 40;
                    const marginTop = 50;
                    const maxWidth  = 515;
                    const lineHeight = 16;
                    const pageHeight = doc.internal.pageSize.getHeight();

                    doc.setFont('helvetica', 'normal');
                    doc.setFontSize(11);

                    const lines = doc.splitTextToSize(msg.content, maxWidth);
                    let y = marginTop;

                    lines.forEach(line => {
                        if (y > pageHeight - 50) {
                            doc.addPage();
                            y = marginTop;
                        }
                        doc.text(line, marginX, y);
                        y += lineHeight;
                    });

                    doc.save(filename);
                },
                 openTicketModal() {
                     this.ticket = { title:'', category:'', priority:'Moyenne', description:'' };
                     this.ticketModalOpen = true;
                 },

                 acceptTicketSuggestion() {
                     this.suggestTicketModalOpen = false;
                     // Pré-remplir le formulaire de ticket
                     this.ticket = {
                         title:       this.lastUnanswerableQuestion.substring(0, 100),
                         category:    'question',
                         priority:    'Moyenne',
                         description: `Application: ${this.lastUnanswerableManual}\n\nQuestion: ${this.lastUnanswerableQuestion}`,
                     };
                     this.ticketModalOpen = true;
                 },

                 dismissTicketSuggestion() {
                     this.suggestTicketModalOpen = false;
                     this.lastUnanswerableQuestion = '';
                     this.lastUnanswerableManual = '';
                 },

                 async submitTicket() {
                     if (!this.ticket.title || !this.ticket.category) return;
                     this.ticketLoading = true;
                     try {
                         const r    = await fetch('/ticket/create', {
                             method: 'POST',
                             headers: {
                                 'Content-Type':'application/json',
                                 'X-CSRF-TOKEN':document.querySelector('meta[name="csrf-token"]').content
                             },
                             body: JSON.stringify({
                                 title:       this.ticket.title,
                                 category:    this.ticket.category,
                                 priority:    this.ticket.priority,
                                 description: this.ticket.description,
                                 app_id:      this.selectedApp,
                                 conversation_id: this.currentConvId,
                             }),
                         });
                         const data = await r.json();
                         if (data.success) {
                             this.ticketModalOpen = false;
                             alert(`Ticket #${data.ticket_id} créé avec succès.`);
                         }
                         else alert('Erreur : ' + (data.message || 'inconnue'));
                     } catch(e) { alert('Erreur GLPI.'); }
                     finally { this.ticketLoading = false; }
                 },

                scrollBottom() { const c = this.$refs.messagesContainer; if (c) c.scrollTop = c.scrollHeight; },
                autoResize(el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 128) + 'px'; },
                formatTime()   { return new Intl.DateTimeFormat('fr-FR', { hour:'2-digit', minute:'2-digit' }).format(new Date()); },

                async deleteConversation(convId) {
                    if (!confirm('Êtes-vous sûr de vouloir supprimer cette conversation ?')) return;
                    try {
                        const r = await fetch(`/chat/conversation/${convId}`, {
                            method: 'DELETE',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').content,
                                'X-Requested-With': 'XMLHttpRequest',
                            },
                        });
                        const data = await r.json();
                        if (r.ok && data.success) {
                            this.conversations = this.conversations.filter(c => c.id !== convId);
                            if (this.currentConvId === convId) {
                                this.currentConvId = null;
                                this.messages      = [];
                                this.selectedApp   = '';
                                this.currentApp    = null;
                            }
                        } else {
                            if (r.status === 404) {
                                this.conversations = this.conversations.filter(c => c.id !== convId);
                            } else {
                                alert('Erreur : ' + (data.error || 'inconnue'));
                            }
                        }
                    } catch(err) {
                        console.error('Erreur suppression:', err);
                        alert('Erreur réseau lors de la suppression');
                    }
                },
            };
        }
    </script>
@endpush
