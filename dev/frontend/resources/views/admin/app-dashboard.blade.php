@extends('layouts.app')
@section('title', 'Administration - Tableau de bord admin › Sonatrach IA')

@push('styles')
    <style>
        html,body{height:100%;overflow:hidden}
        .nav-item{display:flex;align-items:center;gap:12px;padding:10px 14px;border-radius:10px;width:100%;text-align:left;transition:all .15s;color:#4B5563;font-size:.875rem;font-weight:500;cursor:pointer;border:none;background:none}
        .nav-item:hover{background:#F9FAFB;color:#111827}
        .nav-item.active{background:#F26522;color:#fff}
        .nav-badge{margin-left:auto;min-width:22px;height:22px;padding:0 5px;border-radius:11px;font-size:.7rem;font-weight:700;display:flex;align-items:center;justify-content:center}
        .nav-badge-inactive{background:#E5E7EB;color:#6B7280}
        .nav-badge-active{background:#fff;color:#F26522}
        .badge-indexed{background:#D1FAE5;color:#065F46}
        .badge-processing{background:#FEF3C7;color:#92400E}
        .badge-failed{background:#FEE2E2;color:#991B1B}
        .badge-pending{background:#F3F4F6;color:#374151}
        .sidebar-scroll::-webkit-scrollbar{width:4px}
        .sidebar-scroll::-webkit-scrollbar-thumb{background:rgba(17,24,39,.15);border-radius:2px}
        .main-scroll::-webkit-scrollbar{width:6px}
        .main-scroll::-webkit-scrollbar-thumb{background:#E8DDD4;border-radius:3px}
        .icon-btn{display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;border-radius:8px;transition:all .15s;cursor:pointer;border:none;background:none}
        .icon-btn:disabled{opacity:0.3;cursor:not-allowed;pointer-events:none}
        .icon-btn-view{color:#6B7280}.icon-btn-view:hover{color:#3B82F6;background:#EFF6FF}
        .icon-btn-edit{color:#6B7280}.icon-btn-edit:hover{color:#F26522;background:#FFF7ED}
        .icon-btn-del{color:#6B7280}.icon-btn-del:hover{color:#EF4444;background:#FEF2F2}
        .icon-btn-validate{color:#6B7280}.icon-btn-validate:hover:not(:disabled){color:#10B981;background:#ECFDF5}
        .icon-btn-reject{color:#6B7280}.icon-btn-reject:hover:not(:disabled){color:#EF4444;background:#FEF2F2}
        #toast-box{position:fixed;bottom:1.5rem;right:1.5rem;z-index:9999;display:flex;flex-direction:column;gap:8px}
        .toast-item{padding:10px 16px;border-radius:12px;font-size:.8rem;font-weight:500;color:#fff;box-shadow:0 4px 12px rgba(0,0,0,.15);animation:slideIn .3s ease}
        @keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}
        .status-badge-validated{background:#D1FAE5;color:#065F46}
        .status-badge-rejected{background:#FEE2E2;color:#991B1B}
        .status-badge-pending{background:#FEF3C7;color:#92400E}
    </style>
@endpush

@php $s = $stats; @endphp

@section('content')
    <div class="flex h-screen overflow-hidden" x-data="appAdminDashboard" x-init="init()">

        {{-- ════════════════════ SIDEBAR ════════════════════ --}}
        <aside class="w-72 bg-white border-r border-sonatrach-gris-bord flex flex-col h-screen flex-shrink-0 sidebar-scroll overflow-y-auto">
            <div class="px-5 py-5 border-b border-sonatrach-gris-bord flex items-center gap-1 bg-white">
                <img src="{{ asset('assets/images/logo.png') }}" alt="Sonatrach" class="w-24 h-24 object-contain flex-shrink-0">
                <div>
                    <p class="text-sonatrach-noir font-semibold text-sm leading-tight">Sonatrach Assistant</p>
                    <p class="text-gray-500 text-xs">Administration IA</p>
                </div>
            </div>
            <nav class="flex-1 px-3 py-4 space-y-1">
                @php
                    $navItems = [
                        ['key'=>'dashboard','label'=>'Tableau de bord','icon'=>'M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z','badge'=>null],
                        ['key'=>'requests','label'=>'Requêtes','icon'=>'M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z','badge'=>$s['requests_today'] ?? 0],
                        ['key'=>'manuals','label'=>'Manuels','icon'=>'M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253','badge'=>$s['manuals_count'] ?? 0],
                        ['key'=>'faq','label'=>'FAQ','icon'=>'M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z','badge'=>null],
                        ['key'=>'tickets','label'=>'Tickets','icon'=>'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2','badge'=>$s['tickets_total'] ?? 0],
                    ];
                @endphp
                @foreach($navItems as $ni)
                    <button class="nav-item" :class="activeSection==='{{ $ni['key'] }}'?'active':''" @click="activeSection='{{ $ni['key'] }}'">
                        <svg class="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="{{ $ni['icon'] }}"/></svg>
                        <span class="flex-1">{{ $ni['label'] }}</span>
                        @if($ni['key']==='faq')
                            <span class="nav-badge nav-badge-inactive" x-show="faqList.length>0" x-text="faqList.length"></span>
                        @elseif($ni['badge'] !== null)
                            <span class="nav-badge" :class="activeSection==='{{ $ni['key'] }}'?'nav-badge-active':'nav-badge-inactive'">{{ $ni['badge'] }}</span>
                        @endif
                    </button>
                @endforeach

                <div class="pt-4 border-t border-sonatrach-gris-bord mt-4 space-y-2 px-1">
                    <p class="text-gray-400 text-xs font-medium uppercase tracking-wider px-3 mb-3">Mes applications</p>
                    @forelse($adminApplications as $app)
                        <div class="flex items-center gap-2 px-3 py-2 rounded-lg bg-sonatrach-gris-fond">
                            <span class="w-2 h-2 rounded-full bg-sonatrach-orange flex-shrink-0"></span>
                            <span class="text-sonatrach-noir text-xs font-medium truncate">{{ $app->name }}</span>
                        </div>
                    @empty
                        <p class="text-gray-400 text-xs px-3">Aucune application assignée.</p>
                    @endforelse
                </div>
            </nav>
            <div class="border-t border-sonatrach-gris-bord p-4 flex items-center gap-3 bg-white">
                <div class="w-9 h-9 rounded-full bg-sonatrach-orange flex items-center justify-center text-white text-xs font-bold flex-shrink-0">{{ strtoupper(substr(session('user_name','A'),0,2)) }}</div>
                <div class="flex-1 min-w-0">
                    <p class="text-sonatrach-noir text-xs font-semibold truncate">{{ session('user_name','Administrateur') }}</p>
                    <p class="text-gray-500 text-xs">Administrateur d'application</p>
                </div>
                <form method="POST" action="{{ route('auth.logout') }}">@csrf
                    <button type="submit" class="w-7 h-7 rounded-lg flex items-center justify-center text-gray-400 hover:text-red-400 hover:bg-red-500/10 transition-colors">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h6a2 2 0 012 2v1"/></svg>
                    </button>
                </form>
            </div>
        </aside>

        {{-- ════════════════════ MAIN ════════════════════ --}}
        <main class="flex-1 flex flex-col h-screen overflow-hidden">

            {{-- Top header --}}
            <div class="bg-white border-b border-sonatrach-gris-bord px-6 py-4 flex items-center justify-between flex-shrink-0">
                <div>
                    <h1 class="text-base font-semibold text-sonatrach-noir" x-text="sectionLabel"></h1>
                    <p class="text-xs text-gray-400 mt-0.5">Sonatrach Assistant IA › Administration › <span x-text="sectionLabel" class="text-sonatrach-orange"></span></p>
                </div>
                <div class="flex items-center gap-3">
                    <div class="text-right">
                        <p class="text-xs text-gray-400">{{ now()->locale('fr')->isoFormat('dddd D MMMM YYYY') }}</p>
                        <p class="text-xs font-medium text-sonatrach-noir">{{ now()->format('H:i') }}</p>
                    </div>
                    <template x-if="activeSection==='manuals'">
                        <button @click="openManualModal()" class="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-sonatrach-orange text-white hover:bg-sonatrach-orange-dark transition-colors">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>Ajouter un manuel
                        </button>
                    </template>
                    <template x-if="activeSection==='faq'">
                        <button @click="openFaqUploadModal()" class="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-sonatrach-orange text-white hover:bg-sonatrach-orange-dark transition-colors">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>Ajouter une FAQ
                        </button>
                    </template>
                </div>
            </div>

            {{-- Scrollable content --}}
            <div class="flex-1 overflow-y-auto main-scroll bg-sonatrach-gris-fond">

                {{-- ═══════════════ DASHBOARD ═══════════════ --}}
                <div x-show="activeSection==='dashboard'" class="p-6 space-y-6">
                    <div class="grid grid-cols-3 gap-4">
                        <div class="bg-white rounded-2xl border border-sonatrach-gris-bord p-5">
                            <div class="flex items-center justify-between">
                                <div>
                                    <p class="text-gray-500 text-xs font-medium">Total Requêtes</p>
                                    <p class="text-3xl font-bold text-sonatrach-noir mt-1">{{ number_format($s['requests_total'] ?? 0) }}</p>
                                </div>
                                <div class="w-12 h-12 rounded-xl flex items-center justify-center bg-sonatrach-orange/10">
                                    <svg class="w-6 h-6 text-sonatrach-orange" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/></svg>
                                </div>
                            </div>
                            <p class="text-xs text-gray-400 mt-3">{{ $s['requests_today'] ?? 0 }} aujourd'hui</p>
                        </div>
                        <div class="bg-white rounded-2xl border border-sonatrach-gris-bord p-5">
                            <div class="flex items-center justify-between">
                                <div>
                                    <p class="text-gray-500 text-xs font-medium">Tickets</p>
                                    <p class="text-3xl font-bold text-sonatrach-noir mt-1">{{ number_format($s['tickets_total'] ?? 0) }}</p>
                                </div>
                                <div class="w-12 h-12 rounded-xl flex items-center justify-center bg-blue-100">
                                    <svg class="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>
                                </div>
                            </div>
                            <p class="text-xs text-gray-400 mt-3">Tickets GLPI</p>
                        </div>
                        <div class="bg-white rounded-2xl border border-sonatrach-gris-bord p-5">
                            <div class="flex items-center justify-between">
                                <div>
                                    <p class="text-gray-500 text-xs font-medium">Manuels</p>
                                    <p class="text-3xl font-bold text-sonatrach-noir mt-1">{{ number_format($s['manuals_count'] ?? 0) }}</p>
                                </div>
                                <div class="w-12 h-12 rounded-xl flex items-center justify-center bg-green-100">
                                    <svg class="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"/></svg>
                                </div>
                            </div>
                            <p class="text-xs text-gray-400 mt-3">{{ $s['manuals_indexed'] ?? 0 }} indexé(s)</p>
                        </div>
                    </div>

                    <div class="bg-white rounded-2xl border border-sonatrach-gris-bord overflow-hidden">
                        <div class="px-6 py-4 border-b border-sonatrach-gris-bord">
                            <h3 class="text-sm font-semibold text-sonatrach-noir">Mes applications</h3>
                            <p class="text-xs text-gray-400 mt-0.5">{{ $s['admin_applications'] ?? 0 }} application(s) gérée(s)</p>
                        </div>
                        @if(count($adminApplications) > 0)
                            <div class="p-6 grid grid-cols-2 lg:grid-cols-3 gap-4">
                                @foreach($adminApplications as $app)
                                    <div class="rounded-xl border border-sonatrach-gris-bord p-4">
                                        <div class="flex items-center gap-2 mb-1">
                                            <span class="w-2.5 h-2.5 rounded-full bg-sonatrach-orange"></span>
                                            <p class="text-sm font-semibold text-sonatrach-noir">{{ $app->name }}</p>
                                        </div>
                                        <p class="text-xs text-gray-400">{{ $app->department ?? '—' }}</p>
                                    </div>
                                @endforeach
                            </div>
                        @else
                            <div class="p-12 text-center">
                                <svg class="w-16 h-16 mx-auto mb-4 text-gray-200" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"/></svg>
                                <p class="text-gray-400 text-sm">Vous n'êtes associé à aucune application. Contactez le super administrateur.</p>
                            </div>
                        @endif
                    </div>

                    @if($users && count($users) > 0)
                        <div class="bg-white rounded-2xl border border-sonatrach-gris-bord overflow-hidden">
                            <div class="px-6 py-4 border-b border-sonatrach-gris-bord">
                                <h3 class="text-sm font-semibold text-sonatrach-noir">Utilisateurs de mes applications</h3>
                            </div>
                            <table class="w-full text-sm">
                                <thead>
                                <tr class="bg-sonatrach-gris-fond border-b border-sonatrach-gris-bord">
                                    <th class="text-left px-6 py-3 text-xs font-medium text-gray-500">Utilisateur</th>
                                    <th class="text-left px-6 py-3 text-xs font-medium text-gray-500">Département</th>
                                    <th class="text-left px-6 py-3 text-xs font-medium text-gray-500">Poste</th>
                                    <th class="text-center px-6 py-3 text-xs font-medium text-gray-500">Requêtes</th>
                                </tr>
                                </thead>
                                <tbody class="divide-y divide-sonatrach-gris-bord">
                                @foreach($users as $u)
                                    <tr class="hover:bg-sonatrach-gris-fond/50 transition-colors">
                                        <td class="px-6 py-3">
                                            <div class="flex items-center gap-3">
                                                <div class="w-8 h-8 rounded-full bg-sonatrach-orange flex items-center justify-center text-white text-xs font-bold">{{ strtoupper(substr($u->name,0,2)) }}</div>
                                                <div>
                                                    <p class="text-xs font-semibold text-sonatrach-noir">{{ $u->name }}</p>
                                                    <p class="text-xs text-gray-400">{{ $u->email }}</p>
                                                </div>
                                            </div>
                                        </td>
                                        <td class="px-6 py-3 text-xs text-gray-600">{{ $u->department ?? '—' }}</td>
                                        <td class="px-6 py-3 text-xs text-gray-600">{{ $u->title ?? '—' }}</td>
                                        <td class="px-6 py-3 text-center">
                                                <span class="inline-flex items-center justify-center min-w-[2rem] px-2 py-0.5 rounded-full text-xs font-bold {{ ($u->requests_count ?? 0) > 0 ? 'bg-sonatrach-orange/10 text-sonatrach-orange' : 'bg-gray-100 text-gray-400' }}">
                                                    {{ number_format($u->requests_count ?? 0) }}
                                                </span>
                                        </td>
                                    </tr>
                                @endforeach
                                </tbody>
                            </table>
                        </div>
                    @endif
                </div>


                {{-- ═══════════════ REQUÊTES ═══════════════ --}}
                <div x-show="activeSection==='requests'" class="p-6 space-y-6">
                    <div class="grid grid-cols-3 gap-4">
                        @php $rk=[['label'=>'Total requêtes','value'=>$s['requests_total'],'color'=>'#F26522'],['label'=>"Aujourd'hui",'value'=>$s['requests_today'],'color'=>'#10B981'],['label'=>'Applications','value'=>$s['requests_by_app']->count(),'color'=>'#3B82F6']]; @endphp
                        @foreach($rk as $r)<div class="bg-white rounded-2xl border border-sonatrach-gris-bord p-5 flex items-center gap-4"><div class="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0" style="background:{{ $r['color'] }}18"><span class="text-xl font-bold" style="color:{{ $r['color'] }}">{{ number_format($r['value']) }}</span></div><p class="text-sm font-medium text-gray-600">{{ $r['label'] }}</p></div>@endforeach
                    </div>
                    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <div class="bg-white rounded-2xl border border-sonatrach-gris-bord p-5"><h3 class="text-sm font-semibold text-sonatrach-noir mb-5">Par application</h3><div class="space-y-4">@forelse($s['requests_by_app'] as $i=>$r)<div><div class="flex items-center justify-between mb-1.5"><div class="flex items-center gap-2"><span class="w-5 h-5 rounded-full flex items-center justify-center text-white text-[10px] font-bold" style="background:hsl({{ ($i*43)%360 }},60%,50%)">{{ $i+1 }}</span><span class="text-xs font-medium text-gray-700">{{ $r->app_name }}</span></div><span class="text-xs font-bold text-sonatrach-noir">{{ number_format($r->total) }}</span></div><div class="h-2.5 bg-sonatrach-gris-bord rounded-full overflow-hidden"><div class="h-2.5 rounded-full bar-fill" style="width:{{ $r->percentage }}%;background:hsl({{ ($i*43)%360 }},60%,50%)"></div></div></div>@empty<p class="text-sm text-gray-400 py-6 text-center">Aucune donnée.</p>@endforelse</div></div>
                        <div class="bg-white rounded-2xl border border-sonatrach-gris-bord p-5"><h3 class="text-sm font-semibold text-sonatrach-noir mb-5">Par département</h3><div class="space-y-4">@forelse($s['requests_by_dept'] as $i=>$r)<div><div class="flex items-center justify-between mb-1.5"><span class="text-xs font-medium text-gray-700 truncate max-w-[180px]">{{ $r->department }}</span><span class="text-xs font-bold text-sonatrach-noir">{{ number_format($r->total) }}</span></div><div class="h-2.5 bg-sonatrach-gris-bord rounded-full overflow-hidden"><div class="h-2.5 rounded-full bg-purple-500 bar-fill" style="width:{{ $r->percentage }}%"></div></div></div>@empty<p class="text-sm text-gray-400 py-6 text-center">Aucune donnée.</p>@endforelse</div></div>
                    </div>
                </div>

                {{-- ═══════════════ MANUELS ═══════════════ --}}
                <div x-show="activeSection==='manuals'" class="p-6 space-y-5">
                    <div class="grid grid-cols-4 gap-4">
                        @php $ms=[['label'=>'Total','value'=>$s['manuals_count'] ?? 0,'cls'=>'bg-gray-100 text-gray-700'],['label'=>'Indexés','value'=>$s['manuals_indexed'] ?? 0,'cls'=>'bg-green-100 text-green-700'],['label'=>'En traitement','value'=>$s['manuals_processing'] ?? 0,'cls'=>'bg-amber-100 text-amber-700'],['label'=>'Échoués','value'=>$s['manuals_failed'] ?? 0,'cls'=>'bg-red-100 text-red-700']]; @endphp
                        @foreach($ms as $m)<div class="bg-white rounded-2xl border border-sonatrach-gris-bord p-4 flex items-center gap-3"><span class="text-2xl font-bold text-sonatrach-noir">{{ $m['value'] }}</span><span class="px-2 py-0.5 rounded-lg text-xs font-medium {{ $m['cls'] }}">{{ $m['label'] }}</span></div>@endforeach
                    </div>
                    <div class="bg-white rounded-2xl border border-sonatrach-gris-bord overflow-hidden">
                        <table class="w-full text-sm"><thead><tr class="bg-sonatrach-gris-fond border-b border-sonatrach-gris-bord"><th class="text-left px-5 py-3 text-xs font-medium text-gray-500">Nom</th><th class="text-left px-5 py-3 text-xs font-medium text-gray-500">Application</th><th class="text-left px-5 py-3 text-xs font-medium text-gray-500">Version</th><th class="text-left px-5 py-3 text-xs font-medium text-gray-500">Statut</th><th class="text-left px-5 py-3 text-xs font-medium text-gray-500">Ajouté le</th><th class="text-right px-5 py-3 text-xs font-medium text-gray-500">Actions</th></tr></thead>
                            <tbody class="divide-y divide-sonatrach-gris-bord" id="manualsTableBody">
                            @forelse($manuals as $manual)
                                <tr class="hover:bg-sonatrach-gris-fond/50 transition-colors" id="manual-row-{{ $manual->id }}">
                                    <td class="px-5 py-3"><div class="flex items-center gap-2"><div class="w-8 h-8 rounded-lg bg-sonatrach-orange/10 flex items-center justify-center flex-shrink-0"><svg class="w-4 h-4 text-sonatrach-orange" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg></div><span class="font-medium text-sonatrach-noir text-xs">{{ $manual->name }}</span></div></td>
                                    <td class="px-5 py-3 text-xs text-gray-600">{{ $manual->application->name??'—' }}</td>
                                    <td class="px-5 py-3 text-xs text-gray-600">{{ $manual->version??'1.0' }}</td>
                                    <td class="px-5 py-3">@if($manual->status==='indexed')<span class="badge-indexed inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium"><span class="w-1.5 h-1.5 rounded-full bg-green-500"></span>Indexé</span>@elseif($manual->status==='processing')<span class="badge-processing inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium"><span class="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse"></span>En traitement</span>@elseif($manual->status==='failed')<span class="badge-failed inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium" title="{{ $manual->processing_error }}"><span class="w-1.5 h-1.5 rounded-full bg-red-500"></span>Échoué</span>@else<span class="badge-pending inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium"><span class="w-1.5 h-1.5 rounded-full bg-gray-400"></span>En attente</span>@endif</td>
                                    <td class="px-5 py-3 text-xs text-gray-500">{{ $manual->created_at->locale('fr')->isoFormat('D MMMM YYYY') }}</td>
                                    <td class="px-5 py-3 text-right"><div class="flex items-center justify-end gap-1">
                                            <button @click="editManual({{ $manual->id }})" class="icon-btn icon-btn-edit" title="Modifier"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg></button>
                                            <button @click="confirmAction('Supprimer le manuel &quot;{{ addslashes($manual->name) }}&quot; ? Cette action est irréversible.', ()=>deleteManual({{ $manual->id }},{{ json_encode($manual->name) }}))" class="icon-btn icon-btn-del" title="Supprimer"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg></button>
                                        </div></td>
                                </tr>
                            @empty
                                <tr><td colspan="6" class="text-center py-16 text-gray-400 text-sm">Aucun manuel. Cliquez sur <strong>Ajouter un manuel</strong>.</td></tr>
                            @endforelse
                            </tbody>
                        </table>
                        @if($manuals->hasPages())<div class="px-5 py-3 border-t border-sonatrach-gris-bord">{{ $manuals->links() }}</div>@endif
                    </div>
                </div>

                {{-- ═══════════════ FAQ ═══════════════ --}}
                <div x-show="activeSection==='faq'" class="p-6 space-y-6">
                    <div class="grid grid-cols-3 gap-4">
                        <div class="bg-white rounded-2xl border border-sonatrach-gris-bord p-4 flex items-center gap-3">
                            <span class="text-2xl font-bold text-sonatrach-noir" x-text="faqList.length"></span>
                            <span class="px-2 py-0.5 rounded-lg text-xs font-medium bg-gray-100 text-gray-700">Total FAQ</span>
                        </div>
                        <div class="bg-white rounded-2xl border border-sonatrach-gris-bord p-4 flex items-center gap-3">
                            <span class="text-2xl font-bold text-sonatrach-noir" x-text="faqList.reduce((a,f)=>a+(f.item_count||0),0)"></span>
                            <span class="px-2 py-0.5 rounded-lg text-xs font-medium bg-sonatrach-orange/15 text-sonatrach-orange">Entrées totales</span>
                        </div>
                        <div class="bg-white rounded-2xl border border-sonatrach-gris-bord p-4 flex items-center gap-3">
                            <span class="text-2xl font-bold text-sonatrach-noir" x-text="faqList.filter(f=>(f.version||'')!=='').length"></span>
                            <span class="px-2 py-0.5 rounded-lg text-xs font-medium bg-blue-100 text-blue-700">Avec version</span>
                        </div>
                    </div>

                    <div class="bg-white rounded-2xl border border-sonatrach-gris-bord overflow-hidden">
                        <div class="px-5 py-4 border-b border-sonatrach-gris-bord">
                            <h3 class="text-sm font-semibold text-sonatrach-noir">Fichiers FAQ indexés</h3>
                            <p class="text-xs text-gray-400 mt-0.5">Uniquement les FAQ de vos applications.</p>
                        </div>
                        <table class="w-full text-sm">
                            <thead><tr class="bg-sonatrach-gris-fond border-b border-sonatrach-gris-bord">
                                <th class="text-left px-5 py-3 text-xs font-medium text-gray-500">Fichier JSON</th>
                                <th class="text-left px-5 py-3 text-xs font-medium text-gray-500">Application</th>
                                <th class="text-left px-5 py-3 text-xs font-medium text-gray-500">Version manuel</th>
                                <th class="text-center px-5 py-3 text-xs font-medium text-gray-500">Entrées</th>
                                <th class="text-left px-5 py-3 text-xs font-medium text-gray-500">Modifié le</th>
                                <th class="text-right px-5 py-3 text-xs font-medium text-gray-500">Actions</th>
                            </tr></thead>
                            <tbody class="divide-y divide-sonatrach-gris-bord">
                            <template x-if="faqList.length===0">
                                <tr><td colspan="6" class="text-center py-14 text-gray-400 text-sm">
                                        Aucune FAQ. Cliquez sur <strong>Ajouter une FAQ</strong>.
                                    </td></tr>
                            </template>
                            <template x-for="(faq,fi) in faqList" :key="faq.slug">
                                <tr class="hover:bg-sonatrach-gris-fond/50 transition-colors">
                                    <td class="px-5 py-3">
                                        <div class="flex items-center gap-2">
                                            <div class="w-8 h-8 rounded-lg bg-sonatrach-orange/10 flex items-center justify-center flex-shrink-0">
                                                <svg class="w-4 h-4 text-sonatrach-orange" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                                            </div>
                                            <div>
                                                <p class="text-xs font-semibold text-sonatrach-noir" x-text="faq.slug+'.json'"></p>
                                                <p class="text-[10px] text-gray-400 font-mono" x-text="faq.slug"></p>
                                            </div>
                                        </div>
                                    </td>
                                    <td class="px-5 py-3 text-xs text-gray-600" x-text="faq.app_name||'—'"></td>
                                    <td class="px-5 py-3 text-xs text-gray-500" x-text="faq.version||'—'"></td>
                                    <td class="px-5 py-3 text-center">
                                        <span class="inline-flex items-center justify-center min-w-[2rem] px-2 py-0.5 rounded-full text-xs font-bold bg-sonatrach-orange/10 text-sonatrach-orange" x-text="faq.item_count||0"></span>
                                    </td>
                                    <td class="px-5 py-3 text-xs text-gray-500" x-text="faq.updated_at||'—'"></td>
                                    <td class="px-5 py-3 text-right">
                                        <div class="flex items-center justify-end gap-1">
                                            <button @click="openJsonViewModal(faq)" class="icon-btn icon-btn-view" title="Consulter le JSON">
                                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                                            </button>
                                            <button @click="openFaqEditInfosModal(faq)" class="icon-btn icon-btn-edit" title="Modifier les infos">
                                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg>
                                            </button>
                                            <button @click="confirmAction('Supprimer la FAQ &quot;'+faq.slug+'.json&quot; ? Cette action est irréversible.', ()=>deleteFaqFile(faq))" class="icon-btn icon-btn-del" title="Supprimer">
                                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            </template>
                            </tbody>
                        </table>
                    </div>

                    {{-- Conversations à valider, application par application (parmi mes apps uniquement) --}}
                    <div class="bg-white rounded-2xl border border-sonatrach-gris-bord overflow-hidden">
                        <div class="px-5 py-4 border-b border-sonatrach-gris-bord bg-sonatrach-gris-fond flex items-end gap-3">
                            <div class="flex-1 max-w-sm">
                                <label class="block text-xs font-semibold text-gray-700 mb-1.5">Application</label>
                                <select x-model="chatsAppId" @change="chatsAppName=$event.target.options[$event.target.selectedIndex].text; faqChats=[]"
                                        class="w-full px-3 py-2.5 text-sm border border-sonatrach-gris-bord rounded-xl focus:outline-none focus:ring-2 focus:ring-sonatrach-orange bg-white">
                                    <option value="">— Choisir une application —</option>
                                    @foreach($adminApplications as $app)
                                        <option value="{{ $app->id }}">{{ $app->name }}</option>
                                    @endforeach
                                </select>
                            </div>
                            <button @click="loadChats()" :disabled="!chatsAppId||chatsLoading"
                                    class="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold bg-sonatrach-orange text-white disabled:opacity-40 hover:bg-sonatrach-orange-dark transition-colors">
                                <svg x-show="chatsLoading" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                                <span x-text="chatsLoading?'Chargement...':'Charger les chats'"></span>
                            </button>
                            <span class="text-xs text-gray-500 pb-2.5" x-show="faqChats.length>0">
                                <span class="font-bold text-sonatrach-orange" x-text="faqChats.length"></span> conversation(s)
                            </span>
                        </div>

                        <div class="overflow-x-auto">
                            <table class="w-full text-sm">
                                <thead><tr class="bg-sonatrach-gris-fond border-b border-sonatrach-gris-bord">
                                    <th class="text-center px-4 py-3 text-xs font-medium text-gray-500 w-28">Statut</th>
                                    <th class="text-left px-4 py-3 text-xs font-medium text-gray-500">Question</th>
                                    <th class="text-left px-4 py-3 text-xs font-medium text-gray-500">Réponse chatbot</th>
                                    <th class="text-left px-4 py-3 text-xs font-medium text-gray-500 w-28">Application</th>
                                    <th class="text-right px-4 py-3 text-xs font-medium text-gray-500 w-24">Actions</th>
                                </tr></thead>
                                <tbody class="divide-y divide-sonatrach-gris-bord">
                                <template x-if="faqChats.length===0">
                                    <tr><td colspan="5" class="text-center py-12 text-gray-400 text-sm">
                                            <span x-text="chatsAppId?'Cliquez sur Charger les chats.':'Sélectionnez une application.'"></span>
                                        </td></tr>
                                </template>
                                <template x-for="(chat,ci) in faqChats" :key="ci">
                                    <tr class="hover:bg-sonatrach-gris-fond/40 transition-colors align-top">
                                        <td class="px-4 py-3 text-center">
                                            <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold"
                                                  :class="{
                                                    'status-badge-validated': chat.status==='validated',
                                                    'status-badge-rejected':  chat.status==='rejected',
                                                    'status-badge-pending':   chat.status==='pending' || !chat.status
                                                  }">
                                                <span class="w-1.5 h-1.5 rounded-full inline-block"
                                                      :class="{
                                                        'bg-green-500': chat.status==='validated',
                                                        'bg-red-500':   chat.status==='rejected',
                                                        'bg-amber-500': chat.status==='pending' || !chat.status
                                                      }"></span>
                                                <span x-text="chat.status_label||'En attente'"></span>
                                            </span>
                                        </td>
                                        <td class="px-4 py-3 max-w-xs">
                                            <p class="text-xs font-semibold text-sonatrach-noir line-clamp-2 cursor-pointer hover:text-sonatrach-orange"
                                               @click="openReadModal('Question', chat.question||'', chat)"
                                               x-text="chat.question||'—'"></p>
                                        </td>
                                        <td class="px-4 py-3 max-w-sm">
                                            <p class="text-xs text-gray-600 line-clamp-2 cursor-pointer hover:text-sonatrach-orange"
                                               @click="openReadModal('Réponse', chat.answer||'', chat)"
                                               x-text="chat.answer||'—'"></p>
                                        </td>
                                        <td class="px-4 py-3 text-xs text-gray-600" x-text="chatsAppName||'—'"></td>
                                        <td class="px-4 py-3 text-right">
                                            <div class="flex items-center justify-end gap-1">
                                                <template x-if="chat.status==='pending'||!chat.status">
                                                    <button @click="openValidateModal(chat, ci)"
                                                            class="icon-btn icon-btn-validate"
                                                            title="Valider et ajouter à la FAQ">
                                                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
                                                    </button>
                                                </template>
                                                <template x-if="chat.status==='pending'||!chat.status">
                                                    <button @click="rejectChat(chat, ci)"
                                                            class="icon-btn icon-btn-reject"
                                                            title="Rejeter cette réponse">
                                                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
                                                    </button>
                                                </template>
                                                <template x-if="chat.status==='validated'">
                                                    <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-green-100 text-green-700">Ajoutée à la FAQ</span>
                                                </template>
                                                <template x-if="chat.status==='rejected'">
                                                    <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-red-100 text-red-700">Rejetée</span>
                                                </template>
                                            </div>
                                        </td>
                                    </tr>
                                </template>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>

                {{-- ═══════════════ TICKETS ═══════════════ --}}
                <div x-show="activeSection==='tickets'" class="p-6 space-y-6">

                    <div class="grid grid-cols-3 gap-4">
                        <div class="bg-white rounded-2xl border border-sonatrach-gris-bord p-5 flex items-center gap-4">
                            <div class="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 bg-sonatrach-orange/10"><span class="text-xl font-bold text-sonatrach-orange">{{ number_format($s['tickets_total'] ?? 0) }}</span></div>
                            <p class="text-sm font-medium text-gray-600">Total tickets</p>
                        </div>
                        <div class="bg-white rounded-2xl border border-sonatrach-gris-bord p-5 flex items-center gap-4">
                            <div class="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 bg-amber-100"><span class="text-xl font-bold text-amber-600">{{ number_format($s['tickets_open'] ?? 0) }}</span></div>
                            <p class="text-sm font-medium text-gray-600">Ouverts</p>
                        </div>
                        <div class="bg-white rounded-2xl border border-sonatrach-gris-bord p-5 flex items-center gap-4">
                            <div class="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 bg-green-100"><span class="text-xl font-bold text-green-600">{{ number_format($s['tickets_closed'] ?? 0) }}</span></div>
                            <p class="text-sm font-medium text-gray-600">Résolus</p>
                        </div>
                    </div>

                    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <div class="bg-white rounded-2xl border border-sonatrach-gris-bord p-5">
                            <h3 class="text-sm font-semibold text-sonatrach-noir mb-5">Tickets par application</h3>
                            <div class="space-y-4">
                                @forelse(($s['tickets_by_app'] ?? []) as $i=>$r)
                                    <div>
                                        <div class="flex items-center justify-between mb-1.5">
                                            <div class="flex items-center gap-2">
                                                <span class="w-5 h-5 rounded-full flex items-center justify-center text-white text-[10px] font-bold" style="background:hsl({{ ($i*43)%360 }},60%,50%)">{{ $i+1 }}</span>
                                                <span class="text-xs font-medium text-gray-700">{{ $r->app_name }}</span>
                                            </div>
                                            <span class="text-xs font-bold text-sonatrach-noir">{{ number_format($r->total) }}</span>
                                        </div>
                                        <div class="h-2.5 bg-sonatrach-gris-bord rounded-full overflow-hidden"><div class="h-2.5 rounded-full bar-fill" style="width:{{ $r->percentage }}%;background:hsl({{ ($i*43)%360 }},60%,50%)"></div></div>
                                    </div>
                                @empty
                                    <p class="text-sm text-gray-400 py-6 text-center">Aucune donnée.</p>
                                @endforelse
                            </div>
                        </div>
                        <div class="bg-white rounded-2xl border border-sonatrach-gris-bord p-5">
                            <h3 class="text-sm font-semibold text-sonatrach-noir mb-5">Tickets par département</h3>
                            <div class="space-y-4">
                                @forelse(($s['tickets_by_dept'] ?? []) as $r)
                                    <div>
                                        <div class="flex items-center justify-between mb-1.5">
                                            <span class="text-xs font-medium text-gray-700 truncate max-w-[180px]">{{ $r->department }}</span>
                                            <span class="text-xs font-bold text-sonatrach-noir">{{ number_format($r->total) }}</span>
                                        </div>
                                        <div class="h-2.5 bg-sonatrach-gris-bord rounded-full overflow-hidden"><div class="h-2.5 rounded-full bg-purple-500 bar-fill" style="width:{{ $r->percentage }}%"></div></div>
                                    </div>
                                @empty
                                    <p class="text-sm text-gray-400 py-6 text-center">Aucune donnée.</p>
                                @endforelse
                            </div>
                        </div>
                    </div>

                    <div class="bg-white rounded-2xl border border-sonatrach-gris-bord overflow-hidden">
                        <table class="w-full text-sm"><thead><tr class="bg-sonatrach-gris-fond border-b border-sonatrach-gris-bord"><th class="text-left px-5 py-3 text-xs font-medium text-gray-500">#GLPI</th><th class="text-left px-5 py-3 text-xs font-medium text-gray-500">Titre</th><th class="text-left px-5 py-3 text-xs font-medium text-gray-500">Demandeur</th><th class="text-left px-5 py-3 text-xs font-medium text-gray-500">Priorité</th><th class="text-left px-5 py-3 text-xs font-medium text-gray-500">Statut</th><th class="text-left px-5 py-3 text-xs font-medium text-gray-500">Date</th></tr></thead>
                            <tbody class="divide-y divide-sonatrach-gris-bord">
                            @forelse($tickets as $t)@php $pc2=['Basse'=>'bg-blue-50 text-blue-700','Moyenne'=>'bg-amber-50 text-amber-700','Haute'=>'bg-orange-50 text-orange-700','Critique'=>'bg-red-50 text-red-700'][$t->priority]??'bg-gray-100 text-gray-600';@endphp
                            <tr class="hover:bg-sonatrach-gris-fond/50 transition-colors"><td class="px-5 py-3 text-xs text-gray-500 font-mono">#{{ $t->glpi_ticket_id??$t->id }}</td><td class="px-5 py-3 text-xs font-medium text-sonatrach-noir max-w-xs truncate">{{ $t->title }}</td><td class="px-5 py-3"><div class="flex items-center gap-2"><div class="w-6 h-6 rounded-full bg-sonatrach-gris-bord flex items-center justify-center text-[10px] font-bold">{{ strtoupper(substr($t->user->name??'U',0,2)) }}</div><span class="text-xs text-gray-600">{{ $t->user->name??'—' }}</span></div></td><td class="px-5 py-3"><span class="px-2 py-0.5 rounded-full text-xs font-medium {{ $pc2 }}">{{ $t->priority }}</span></td><td class="px-5 py-3 text-xs text-gray-500">{{ $t->glpi_status??'Envoyé' }}</td><td class="px-5 py-3 text-xs text-gray-400">{{ $t->created_at->locale('fr')->isoFormat('D MMMM YYYY HH:mm') }}</td></tr>
                            @empty
                                <tr><td colspan="6" class="text-center py-12 text-gray-400 text-sm">Aucun ticket.</td></tr>
                            @endforelse
                            </tbody>
                        </table>
                        @if($tickets->hasPages())<div class="px-5 py-3 border-t border-sonatrach-gris-bord">{{ $tickets->links() }}</div>@endif
                    </div>
                </div>

            </div>
        </main>

        {{-- ═══════════════════════ MODALS (identiques au dashboard super-admin) ═══════════════════════ --}}

        <template x-if="confirmOpen">
            <div class="fixed inset-0 z-[60] flex items-center justify-center px-4" style="background:rgba(0,0,0,0.5)">
                <div class="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
                    <div class="flex items-start gap-4 mb-6">
                        <div class="w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0">
                            <svg class="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/></svg>
                        </div>
                        <div><h3 class="text-sm font-semibold text-sonatrach-noir">Confirmation requise</h3><p class="text-xs text-gray-600 mt-1.5 leading-relaxed" x-html="confirmMessage"></p></div>
                    </div>
                    <div class="flex justify-end gap-2">
                        <button @click="confirmOpen=false;confirmCb=null" class="px-4 py-2 rounded-xl text-sm border border-gray-300 text-gray-600 hover:bg-gray-50">Annuler</button>
                        <button @click="confirmOpen=false;if(confirmCb)confirmCb();" class="px-4 py-2 rounded-xl text-sm font-semibold bg-sonatrach-orange text-white hover:bg-sonatrach-orange-dark">Confirmer</button>
                    </div>
                </div>
            </div>
        </template>

        {{-- Ajouter/Modifier manuel --}}
        <template x-if="manualModalOpen">
            <div class="fixed inset-0 z-50 flex items-center justify-center px-4" style="background:rgba(0,0,0,0.5)" @click.self="manualModalOpen=false">
                <div class="bg-white rounded-2xl shadow-2xl w-full max-w-lg p-6">
                    <div class="flex items-center justify-between mb-6"><div><h2 class="text-base font-semibold text-sonatrach-noir" x-text="editingManualId?'Modifier le manuel':'Ajouter un manuel'"></h2><p class="text-xs text-gray-400 mt-0.5">Le fichier sera extrait et indexé automatiquement.</p></div><button @click="manualModalOpen=false" class="text-gray-400 hover:text-gray-600"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg></button></div>
                    <div class="space-y-4">
                        <div><label class="block text-xs font-semibold text-gray-700 mb-1.5">Nom du manuel *</label><input type="text" x-model="manualForm.name" placeholder="Manuel utilisateur..." class="w-full px-3 py-2.5 text-sm border border-sonatrach-gris-bord rounded-xl focus:outline-none focus:ring-2 focus:ring-sonatrach-orange"></div>
                        <div class="grid grid-cols-2 gap-3">
                            <div>
                                <label class="block text-xs font-semibold text-gray-700 mb-1.5">Application *</label>
                                <select x-model="manualForm.app_name" class="w-full px-3 py-2.5 text-sm border border-sonatrach-gris-bord rounded-xl focus:outline-none focus:ring-2 focus:ring-sonatrach-orange bg-white">
                                    <option value="">— Choisir une application —</option>
                                    @foreach($adminApplications as $app)
                                        <option value="{{ $app->name }}">{{ $app->name }}</option>
                                    @endforeach
                                </select>
                                <p class="text-[10px] text-gray-400 mt-1">Seules vos applications sont proposées.</p>
                            </div>
                            <div><label class="block text-xs font-semibold text-gray-700 mb-1.5">Version du document</label><input type="text" x-model="manualForm.version" placeholder="1.0" class="w-full px-3 py-2.5 text-sm border border-sonatrach-gris-bord rounded-xl focus:outline-none focus:ring-2 focus:ring-sonatrach-orange"></div>
                        </div>
                        <div class="rounded-xl border border-sonatrach-gris-bord p-3 bg-sonatrach-gris-fond/40">
                            <label class="inline-flex items-start gap-3 cursor-pointer">
                                <input type="checkbox" x-model="manualForm.follows_internal_template" class="mt-0.5 w-4 h-4 text-sonatrach-orange border-gray-300 rounded focus:ring-sonatrach-orange">
                                <span><span class="block text-xs font-semibold text-gray-700">Le manuel suit la template interne *</span></span>
                            </label>
                        </div>
                        <div><label class="block text-xs font-semibold text-gray-700 mb-1.5">Fichier PDF <span x-text="editingManualId?'(laisser vide pour conserver)':'*'" class="font-normal text-gray-400"></span></label>
                            <label for="manualFile" class="flex flex-col items-center justify-center gap-2 p-5 border-2 border-dashed border-sonatrach-gris-bord rounded-xl cursor-pointer hover:border-sonatrach-orange transition-colors group">
                                <input type="file" id="manualFile" accept=".pdf" class="hidden" @change="manualForm.fileName=$event.target.files[0]?.name||''">
                                <svg class="w-8 h-8 text-gray-300 group-hover:text-sonatrach-orange" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/></svg>
                                <p class="text-sm font-medium text-gray-600" x-text="manualForm.fileName||'Glissez un PDF ou cliquez'"></p>
                            </label>
                        </div>
                        <template x-if="uploadError"><div class="flex items-center gap-2 p-3 rounded-xl bg-red-50 border border-red-200"><p class="text-xs text-red-600 flex-1" x-text="uploadError"></p><button @click="uploadError=''" class="text-red-400"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg></button></div></template>
                    </div>
                    <div class="flex gap-3 mt-6">
                        <button @click="manualModalOpen=false" class="flex-1 py-2.5 rounded-xl text-sm font-medium border border-sonatrach-gris-bord text-gray-600">Annuler</button>
                        <button @click="saveManual()" :disabled="!manualForm.name||!manualForm.app_name||manualSaving" class="flex-1 py-2.5 rounded-xl text-sm font-semibold text-white bg-sonatrach-orange disabled:opacity-50 flex items-center justify-center gap-2">
                            <svg x-show="manualSaving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                            <span x-text="manualSaving?'Traitement...':(editingManualId?'Enregistrer':'Ajouter et indexer')"></span>
                        </button>
                    </div>
                </div>
            </div>
        </template>

        {{-- Upload FAQ JSON --}}
        <template x-if="faqModalOpen">
            <div class="fixed inset-0 z-50 flex items-center justify-center px-4" style="background:rgba(0,0,0,0.5)" @click.self="faqModalOpen=false">
                <div class="bg-white rounded-2xl shadow-2xl w-full max-w-lg p-6">
                    <div class="flex items-center justify-between mb-6"><div><h2 class="text-base font-semibold text-sonatrach-noir">Ajouter une FAQ</h2><p class="text-xs text-gray-400 mt-0.5">Choisissez une de vos applications.</p></div><button @click="faqModalOpen=false" class="text-gray-400 hover:text-gray-600"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg></button></div>
                    <div class="space-y-4">
                        <div>
                            <label class="block text-xs font-semibold text-gray-700 mb-1.5">Application *</label>
                            <select x-model="faqForm.app_id" class="w-full px-3 py-2.5 text-sm border border-sonatrach-gris-bord rounded-xl focus:outline-none focus:ring-2 focus:ring-sonatrach-orange bg-white">
                                <option value="">— Choisir une application —</option>
                                @foreach($adminApplications as $app)<option value="{{ $app->id }}">{{ $app->name }}</option>@endforeach
                            </select>
                            <p class="text-[10px] text-gray-400 mt-1">Seules vos applications sont proposées.</p>
                        </div>
                        <div><label class="block text-xs font-semibold text-gray-700 mb-1.5">Fichier JSON *</label>
                            <label for="faqJsonFile" class="flex flex-col items-center justify-center gap-2 p-5 border-2 border-dashed border-sonatrach-gris-bord rounded-xl cursor-pointer hover:border-sonatrach-orange transition-colors group">
                                <input type="file" id="faqJsonFile" accept=".json,application/json" class="hidden" @change="faqForm.file=$event.target.files[0];faqForm.fileName=$event.target.files[0]?.name||''">
                                <svg class="w-8 h-8 text-gray-300 group-hover:text-sonatrach-orange" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/></svg>
                                <p class="text-sm font-medium text-gray-600" x-text="faqForm.fileName||'Glissez un JSON ou cliquez'"></p>
                            </label>
                        </div>
                        <template x-if="faqFormError"><div class="p-3 rounded-xl bg-red-50 border border-red-200"><p class="text-xs text-red-600" x-text="faqFormError"></p></div></template>
                    </div>
                    <div class="flex gap-3 mt-6">
                        <button @click="faqModalOpen=false" class="flex-1 py-2.5 rounded-xl text-sm font-medium border border-sonatrach-gris-bord text-gray-600">Annuler</button>
                        <button @click="uploadFaqFile()" :disabled="!faqForm.app_id||!faqForm.file||faqUploading" class="flex-1 py-2.5 rounded-xl text-sm font-semibold text-white bg-sonatrach-orange disabled:opacity-50 flex items-center justify-center gap-2">
                            <svg x-show="faqUploading" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                            <span x-text="faqUploading?'Upload...':'Ajouter et indexer'"></span>
                        </button>
                    </div>
                </div>
            </div>
        </template>

        {{-- Consulter JSON --}}
        <template x-if="jsonViewOpen">
            <div class="fixed inset-0 z-50 flex items-center justify-center px-4" style="background:rgba(0,0,0,0.5)" @click.self="jsonViewOpen=false">
                <div class="bg-white rounded-2xl shadow-2xl w-full max-w-4xl p-6 max-h-[90vh] flex flex-col">
                    <div class="flex items-center justify-between mb-4 flex-shrink-0">
                        <div><h2 class="text-base font-semibold text-sonatrach-noir" x-text="'JSON — '+jsonViewFaq.slug+'.json'"></h2><p class="text-xs text-gray-400 mt-0.5"><span x-text="jsonViewFaq.app_name"></span> · <span x-text="(jsonViewEntries.length)+' entrée(s)'"></span></p></div>
                        <button @click="jsonViewOpen=false" class="text-gray-400 hover:text-gray-600"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg></button>
                    </div>
                    <div class="flex-1 overflow-auto rounded-xl border border-sonatrach-gris-bord bg-gray-950 p-4">
                        <pre class="text-xs text-green-400 font-mono whitespace-pre-wrap" x-text="JSON.stringify(jsonViewEntries,null,2)"></pre>
                    </div>
                    <div class="flex-shrink-0 pt-4 border-t border-sonatrach-gris-bord mt-4 flex justify-end gap-2">
                        <button @click="jsonViewOpen=false" class="px-4 py-2 rounded-xl text-sm border border-gray-300 text-gray-600">Fermer</button>
                        <button @click="confirmAction('Modifier la FAQ &quot;'+jsonViewFaq.slug+'.json&quot; ?',()=>{jsonViewOpen=false;openFaqEditModal(jsonViewFaq)})" class="px-4 py-2 rounded-xl text-sm font-semibold bg-sonatrach-orange text-white flex items-center gap-2">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg>Modifier
                        </button>
                    </div>
                </div>
            </div>
        </template>

        {{-- Modifier FAQ (JSON) --}}
        <template x-if="faqEditOpen">
            <div class="fixed inset-0 z-50 flex items-center justify-center px-4" style="background:rgba(0,0,0,0.5)" @click.self="faqEditOpen=false">
                <div class="bg-white rounded-2xl shadow-2xl w-full max-w-4xl p-6 max-h-[92vh] flex flex-col">
                    <div class="flex items-center justify-between mb-4 flex-shrink-0">
                        <div>
                            <h2 class="text-base font-semibold text-sonatrach-noir" x-text="'Modifier — '+faqEditFaq.slug+'.json'"></h2>
                            <p class="text-xs text-gray-400 mt-0.5"><span x-text="faqEditFaq.app_name"></span> · <span x-text="faqEditEntries.length+' entrée(s)'"></span></p>
                        </div>
                        <button @click="faqEditOpen=false" class="text-gray-400 hover:text-gray-600"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg></button>
                    </div>
                    <div class="mb-2 flex-shrink-0 p-3 rounded-xl bg-blue-50 border border-blue-200">
                        <p class="text-xs text-blue-700"><strong>Note :</strong> Toute modification du JSON déclenchera automatiquement une réindexation complète de la collection FAQ.</p>
                    </div>
                    <div class="mb-3 flex-1 flex flex-col min-h-0">
                        <label class="block text-xs font-semibold text-gray-700 mb-1.5 flex-shrink-0">JSON complet (modifiable)</label>
                        <textarea x-model="faqEditRaw" class="flex-1 px-3 py-2.5 text-xs font-mono border border-sonatrach-gris-bord rounded-xl focus:outline-none focus:ring-2 focus:ring-sonatrach-orange resize-none bg-gray-50" style="min-height:300px"></textarea>
                        <p class="text-xs text-gray-400 mt-1 flex-shrink-0">Format attendu : <code class="bg-gray-100 px-1 rounded">[{"question":"...","answer":"..."}]</code> ou <code class="bg-gray-100 px-1 rounded">{"items":[...]}</code></p>
                    </div>
                    <template x-if="faqEditError"><div class="p-3 rounded-xl bg-red-50 border border-red-200 mb-3 flex-shrink-0"><p class="text-xs text-red-600" x-text="faqEditError"></p></div></template>
                    <div class="flex-shrink-0 flex justify-end gap-2 pt-3 border-t border-sonatrach-gris-bord">
                        <button @click="faqEditOpen=false" class="px-4 py-2 rounded-xl text-sm border border-gray-300 text-gray-600">Annuler</button>
                        <button @click="saveFaqEdit()" :disabled="faqEditSaving" class="px-5 py-2 rounded-xl text-sm font-semibold bg-sonatrach-orange text-white disabled:opacity-50 flex items-center gap-2">
                            <svg x-show="faqEditSaving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                            <span x-text="faqEditSaving?'Enregistrement + réindexation...':'Enregistrer et réindexer'"></span>
                        </button>
                    </div>
                </div>
            </div>
        </template>

        {{-- Modifier infos FAQ --}}
        <template x-if="faqEditInfosOpen">
            <div class="fixed inset-0 z-50 flex items-center justify-center px-4" style="background:rgba(0,0,0,0.5)" @click.self="faqEditInfosOpen=false">
                <div class="bg-white rounded-2xl shadow-2xl w-full max-w-lg p-6">
                    <div class="flex items-center justify-between mb-5"><div><h2 class="text-base font-semibold text-sonatrach-noir">Modifier les infos FAQ</h2><p class="text-xs text-gray-400 mt-0.5">Fichier : <span class="font-mono font-semibold text-sonatrach-orange" x-text="faqEditInfosFaq.slug+'.json'"></span></p></div><button @click="faqEditInfosOpen=false" class="text-gray-400 hover:text-gray-600"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg></button></div>
                    <div class="space-y-4">
                        <div>
                            <label class="block text-xs font-semibold text-gray-700 mb-1.5">Nom de l'application *</label>
                            <input type="text" x-model="faqEditInfosForm.app_name" placeholder="BDM, SAP FAQ, Parc Auto v2…" class="w-full px-3 py-2.5 text-sm border border-sonatrach-gris-bord rounded-xl focus:outline-none focus:ring-2 focus:ring-sonatrach-orange">
                            <p class="text-[10px] text-gray-400 mt-1">Le nom doit être unique. Le fichier JSON sera renommé en conséquence.</p>
                        </div>
                        <template x-if="faqEditInfosError"><div class="p-3 rounded-xl bg-red-50 border border-red-200"><p class="text-xs text-red-600" x-text="faqEditInfosError"></p></div></template>
                    </div>
                    <div class="flex gap-3 mt-6">
                        <button @click="faqEditInfosOpen=false" class="flex-1 py-2.5 rounded-xl text-sm font-medium border border-sonatrach-gris-bord text-gray-600">Annuler</button>
                        <button @click="saveFaqEditInfos()" :disabled="!faqEditInfosForm.app_name||faqEditInfosSaving" class="flex-1 py-2.5 rounded-xl text-sm font-semibold text-white bg-sonatrach-orange disabled:opacity-50 flex items-center justify-center gap-2">
                            <svg x-show="faqEditInfosSaving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                            <span x-text="faqEditInfosSaving?'Enregistrement...':'Enregistrer'"></span>
                        </button>
                    </div>
                </div>
            </div>
        </template>

        {{-- Lire question/réponse complète --}}
        <template x-if="readModalOpen">
            <div class="fixed inset-0 z-50 flex items-center justify-center px-4" style="background:rgba(0,0,0,0.5)" @click.self="readModalOpen=false">
                <div class="bg-white rounded-2xl shadow-2xl w-full max-w-2xl p-6 max-h-[80vh] flex flex-col">
                    <div class="flex items-center justify-between mb-4 flex-shrink-0"><h2 class="text-sm font-semibold text-sonatrach-noir" x-text="readModalTitle+' complète'"></h2><button @click="readModalOpen=false" class="text-gray-400 hover:text-gray-600"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg></button></div>
                    <div class="flex-1 overflow-y-auto"><p class="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap" x-text="readModalText"></p></div>
                    <div class="flex-shrink-0 pt-4 border-t border-sonatrach-gris-bord mt-4 flex justify-between items-center">
                        <p class="text-xs text-gray-400">Application : <span class="font-medium text-sonatrach-orange" x-text="chatsAppName"></span></p>
                        <template x-if="readModalChat && (readModalChat.status==='pending'||!readModalChat.status)">
                            <button @click="confirmAction('Valider cette réponse et l\'ajouter à la FAQ de &quot;'+chatsAppName+'&quot; ?',()=>{readModalOpen=false;openValidateModal(readModalChat,null)})" class="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold bg-sonatrach-orange text-white">
                                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>Valider → FAQ
                            </button>
                        </template>
                        <template x-if="readModalChat && readModalChat.status==='validated'">
                            <span class="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold bg-green-100 text-green-700">Déjà ajoutée à la FAQ</span>
                        </template>
                        <template x-if="readModalChat && readModalChat.status==='rejected'">
                            <span class="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold bg-red-100 text-red-700">Rejetée</span>
                        </template>
                    </div>
                </div>
            </div>
        </template>

        {{-- Valider chat → FAQ --}}
        <template x-if="validateOpen">
            <div class="fixed inset-0 z-50 flex items-center justify-center px-4" style="background:rgba(0,0,0,0.5)" @click.self="validateOpen=false">
                <div class="bg-white rounded-2xl shadow-2xl w-full max-w-2xl p-6">
                    <div class="flex items-center justify-between mb-5"><div><h2 class="text-base font-semibold text-sonatrach-noir">Valider → FAQ</h2><p class="text-xs text-gray-400 mt-0.5">Application : <span class="font-semibold text-sonatrach-orange" x-text="chatsAppName"></span></p></div><button @click="validateOpen=false" class="text-gray-400 hover:text-gray-600"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg></button></div>
                    <div class="mb-4 p-3 rounded-xl bg-amber-50 border border-amber-200">
                        <div class="flex items-start gap-2"><svg class="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/></svg>
                            <div><p class="text-xs font-semibold text-amber-800">Vérifiez avant de valider</p><p class="text-xs text-amber-700 mt-0.5">Cette réponse sera ajoutée à la FAQ et réindexée automatiquement dans Qdrant.</p></div></div>
                    </div>
                    <div class="space-y-3">
                        <div><label class="block text-xs font-semibold text-gray-700 mb-1">Question</label><textarea x-model="validateForm.question" rows="3" class="w-full px-3 py-2.5 text-sm border border-sonatrach-gris-bord rounded-xl focus:outline-none focus:ring-2 focus:ring-sonatrach-orange resize-y"></textarea></div>
                        <div><label class="block text-xs font-semibold text-gray-700 mb-1">Réponse <span class="font-normal text-gray-400">(modifiable)</span></label><textarea x-model="validateForm.answer" rows="7" class="w-full px-3 py-2.5 text-sm border border-sonatrach-gris-bord rounded-xl focus:outline-none focus:ring-2 focus:ring-sonatrach-orange resize-y"></textarea></div>
                        <template x-if="validateError"><div class="p-3 rounded-xl bg-red-50 border border-red-200"><p class="text-xs text-red-600" x-text="validateError"></p></div></template>
                    </div>
                    <div class="flex justify-end gap-2 mt-5">
                        <button @click="validateOpen=false" class="px-5 py-2.5 rounded-xl text-sm border border-gray-300 text-gray-600">Annuler</button>
                        <button @click="confirmValidate()" :disabled="!validateForm.question||!validateForm.answer||validateSaving" class="px-5 py-2.5 rounded-xl text-sm font-semibold bg-sonatrach-orange text-white disabled:opacity-50 flex items-center gap-2">
                            <svg x-show="validateSaving" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                            <span x-text="validateSaving?'Ajout + réindexation...':'Confirmer et ajouter à la FAQ'"></span>
                        </button>
                    </div>
                </div>
            </div>
        </template>

        <div id="toast-box"></div>

    </div>
@endsection

@push('scripts')
    <script>
        const PHP_FAQ_LIST = @json($faqList ?? []);
        const CSRF = document.querySelector('meta[name="csrf-token"]')?.content || '';

        function formatFrenchDate(value) {
            if (!value) return '—';
            let date = value instanceof Date ? value : null;
            if (!date) {
                const raw = String(value).trim();
                const dmY = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})(?:\s+(\d{1,2}):(\d{2}))?$/);
                if (dmY) {
                    const [, d, m, y, hh = '0', mm = '0'] = dmY;
                    date = new Date(Number(y), Number(m) - 1, Number(d), Number(hh), Number(mm));
                } else {
                    date = new Date(raw);
                }
            }
            if (Number.isNaN(date.getTime())) return value;
            return new Intl.DateTimeFormat('fr-FR', { day: '2-digit', month: 'long', year: 'numeric' }).format(date);
        }

        document.addEventListener('alpine:init', () => {
            Alpine.data('appAdminDashboard', () => ({
                activeSection: 'dashboard',

                get sectionLabel() {
                    return {dashboard:'Tableau de bord',manuals:'Manuels',faq:'FAQ',tickets:'Tickets'}[this.activeSection] || '';
                },

                confirmOpen: false, confirmMessage: '', confirmCb: null,
                confirmAction(msg, cb) { this.confirmMessage = msg; this.confirmCb = cb; this.confirmOpen = true; },

                manualModalOpen: false, editingManualId: null, manualSaving: false,
                manualForm: { name: '', app_name: '', version: '1.0', follows_internal_template: false, fileName: '' },
                uploadError: '',

                faqList: PHP_FAQ_LIST.map(f => ({ ...f, updated_at: formatFrenchDate(f.updated_at) })),

                faqModalOpen: false, faqUploading: false, faqFormError: '',
                faqForm: { app_id: '', file: null, fileName: '' },

                jsonViewOpen: false, jsonViewFaq: {}, jsonViewEntries: [],

                faqEditOpen: false, faqEditFaq: {}, faqEditEntries: [], faqEditRaw: '', faqEditError: '', faqEditSaving: false,

                faqEditInfosOpen: false, faqEditInfosFaq: {},
                faqEditInfosForm: { app_name: '' }, faqEditInfosError: '', faqEditInfosSaving: false,

                chatsAppId: '', chatsAppName: '', faqChats: [], chatsLoading: false,

                readModalOpen: false, readModalTitle: '', readModalText: '', readModalChat: null,

                validateOpen: false, validateChat: null, validateChatIdx: null,
                validateForm: { question: '', answer: '' }, validateSaving: false, validateError: '',

                init() {
                    const s = new URLSearchParams(window.location.search).get('section');
                    if (s && ['dashboard','manuals','faq','tickets'].includes(s)) this.activeSection = s;
                },

                toast(msg, ok = true) {
                    const box = document.getElementById('toast-box');
                    const el  = document.createElement('div');
                    el.className = 'toast-item ' + (ok ? 'bg-green-600' : 'bg-red-600');
                    el.textContent = msg;
                    box.appendChild(el);
                    setTimeout(() => el.remove(), 3500);
                },

                escapeHtml(str) {
                    if (!str) return '';
                    return str.replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
                },

                // ── Manuels ─────────────────────────────────────────────
                openManualModal(manual = null) {
                    this.editingManualId = manual?.id ?? null;
                    this.uploadError     = '';
                    this.manualForm = {
                        name: manual?.name ?? '',
                        app_name: manual?.app_name ?? '',
                        version: manual?.version ?? '1.0',
                        follows_internal_template: manual ? (manual.follows_internal_template === true || manual.follows_internal_template === 1 || manual.follows_internal_template === '1') : false,
                        fileName: ''
                    };
                    const fi = document.getElementById('manualFile');
                    if (fi) fi.value = '';
                    this.manualModalOpen = true;
                },

                editManual(id) {
                    fetch('/admin/manuals/' + id, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
                        .then(r => r.json())
                        .then(d => this.openManualModal(d))
                        .catch(() => this.toast('Erreur chargement', false));
                },

                saveManual() {
                    if (!this.manualForm.name || !this.manualForm.app_name) return;
                    const fi = document.getElementById('manualFile');
                    const hf = fi?.files[0] || null;
                    if (!this.editingManualId && !hf) { this.uploadError = 'Sélectionnez un PDF.'; return; }
                    if (hf && hf.size > 500 * 1024 * 1024) { this.uploadError = 'Fichier > 500 Mo.'; return; }

                    this.manualSaving = true;
                    this.uploadError  = '';

                    const appName = this.manualForm.app_name.trim();
                    const version = this.manualForm.version || '1.0';

                    fetch('/admin/manuals/check-app?app_name=' + encodeURIComponent(appName) + '&version=' + encodeURIComponent(version), {
                        headers: { 'X-Requested-With': 'XMLHttpRequest' }
                    })
                        .then(r => r.json())
                        .then(check => {
                            if (check.exists && check.conflict === 'same_version') {
                                this.uploadError = `L'application "${appName}" avec la version "${version}" existe déjà. Modifiez le nom ou la version.`;
                                this.manualSaving = false;
                                return;
                            }
                            if (check.exists && check.conflict === 'diff_version') {
                                this.showConflictResolutionModal(check, hf);
                                return;
                            }
                            this.submitManual(hf);
                        })
                        .catch(e => {
                            console.warn('Check error, proceeding', e);
                            this.submitManual(hf);
                        });
                },

                showConflictResolutionModal(check, hf) {
                    const modalId  = 'conflictModal_' + Date.now();
                    const appName  = this.escapeHtml(check.app_name);
                    const newVersion = this.escapeHtml(this.manualForm.version);

                    const modalHtml = `
                        <div class="fixed inset-0 z-[70] flex items-center justify-center" style="background:rgba(0,0,0,0.5)" id="${modalId}">
                            <div class="bg-white rounded-2xl max-w-md w-full m-4 p-6" style="box-shadow:0 25px 50px -12px rgba(0,0,0,0.25)">
                                <div class="flex items-start gap-4 mb-5">
                                    <div class="w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0">
                                        <svg class="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/></svg>
                                    </div>
                                    <div>
                                        <h3 class="text-sm font-semibold" style="color:#1a1a2e">Version différente détectée</h3>
                                        <p class="text-xs mt-1.5 leading-relaxed" style="color:#4b5563">
                                            L'application <strong>${appName}</strong> existe déjà avec la version <strong>${this.escapeHtml(check.existing_version)}</strong>.<br><br>
                                            Que souhaitez-vous faire avec la version <strong>${newVersion}</strong> ?
                                        </p>
                                    </div>
                                </div>
                                <div class="space-y-2 mb-5">
                                    <button id="complementaryChoice_${modalId}" class="w-full text-left px-4 py-3 rounded-xl border hover:border-orange-500 transition-colors" style="border-color:#e5e7eb">
                                        <p class="text-sm font-semibold" style="color:#1a1a2e">📄 Complémentaire</p>
                                        <p class="text-xs" style="color:#6b7280">Fusionner ce PDF à la fin du manuel existant (réindexation)</p>
                                    </button>
                                    <button id="contradictoryChoice_${modalId}" class="w-full text-left px-4 py-3 rounded-xl border hover:border-orange-500 transition-colors" style="border-color:#e5e7eb">
                                        <p class="text-sm font-semibold" style="color:#1a1a2e">🆕 Nouvelle version indépendante</p>
                                        <p class="text-xs" style="color:#6b7280">Conserver l'ancien, créer un nouveau avec un nom différent</p>
                                    </button>
                                </div>
                                <div class="flex justify-end gap-2">
                                    <button id="cancelConflict_${modalId}" class="px-4 py-2 rounded-xl text-sm border text-gray-600 hover:bg-gray-50" style="border-color:#d1d5db">Annuler</button>
                                </div>
                            </div>
                        </div>`;

                    const container = document.createElement('div');
                    container.innerHTML = modalHtml;
                    document.body.appendChild(container);

                    document.getElementById(`complementaryChoice_${modalId}`).onclick = () => {
                        container.remove();
                        this.submitManual(hf, 'complementary', check.existing_manual_id);
                    };


                    document.getElementById(`contradictoryChoice_${modalId}`).onclick = () => {
                        container.remove();
                        const cleanVersion = String(this.manualForm.version || 'v2').trim().replace(/\s+/g, '_');
                        const autoAppName  = `${check.app_name}_v${cleanVersion}`;

                        this.toast(`Nouvelle application créée automatiquement : "${autoAppName}"`);
                        this.submitManual(hf, null, null, autoAppName, true);
                    };

                    document.getElementById(`cancelConflict_${modalId}`).onclick = () => {
                        container.remove();
                        this.manualSaving = false;
                    };
                },

                submitManual(hf, resolution = null, existingManualId = null, overrideAppName = null, autoVersioned = false) {
                    const fd = new FormData();
                    if (this.editingManualId) fd.append('_method', 'PUT');
                    fd.append('name',     this.manualForm.name);
                    fd.append('app_name', overrideAppName || this.manualForm.app_name);
                    fd.append('version',  this.manualForm.version || '1.0');
                    fd.append('follows_internal_template', this.manualForm.follows_internal_template ? '1' : '0');
                    if (hf) fd.append('file', hf);
                    if (resolution) {
                        fd.append('conflict_resolution', resolution);
                        if (existingManualId) fd.append('existing_manual_id', existingManualId);
                    }
                    if (autoVersioned) {
                        fd.append('auto_versioned', '1');
                    }

                    fetch(this.editingManualId ? '/admin/manuals/' + this.editingManualId : '/admin/manuals', {
                        method: 'POST', body: fd,
                        headers: { 'X-CSRF-TOKEN': CSRF, 'X-Requested-With': 'XMLHttpRequest' }
                    })
                        .then(async r => {
                            const d = await r.json();
                            if (!r.ok) {
                                if (r.status === 409 && d.conflict === 'same_version') {
                                    throw new Error(`L'application "${d.app_name}" avec la version "${d.version}" existe déjà.`);
                                }
                                throw new Error(d.errors ? Object.values(d.errors).flat()[0] : (d.message || 'Erreur ' + r.status));
                            }
                            return d;
                        })
                        .then(d => {
                            if (d.success) {
                                this.manualModalOpen = false;
                                this.toast(d.message || (resolution === 'complementary' ? 'PDF fusionné, réindexation en cours' : 'Manuel ajouté, indexation en cours'));
                                setTimeout(() => location.reload(), 1500);
                            } else {
                                throw new Error(d.message || 'Erreur');
                            }
                        })
                        .catch(e => {
                            this.uploadError  = e.message;
                            this.manualSaving = false;
                        });
                },

                deleteManual(id, name) {
                    fetch('/admin/manuals/' + id, {
                        method: 'DELETE',
                        headers: { 'X-CSRF-TOKEN': CSRF, 'X-Requested-With': 'XMLHttpRequest' }
                    })
                        .then(r => r.json())
                        .then(d => {
                            if (d.success) {
                                const row = document.getElementById('manual-row-' + id);
                                if (row) row.remove();
                                this.toast('Manuel "' + name + '" supprimé');
                            } else {
                                this.toast('Erreur : ' + (d.message || 'inconnue'), false);
                            }
                        })
                        .catch(() => this.toast('Erreur réseau', false));
                },

                // ── FAQ upload ──────────────────────────────────────────
                openFaqUploadModal() {
                    this.faqFormError = '';
                    this.faqForm = { app_id: '', file: null, fileName: '' };
                    const fi = document.getElementById('faqJsonFile');
                    if (fi) fi.value = '';
                    this.faqModalOpen = true;
                },

                async uploadFaqFile() {
                    if (!this.faqForm.app_id || !this.faqForm.file) {
                        this.faqFormError = 'Choisissez une application et un fichier JSON.';
                        return;
                    }

                    this.faqUploading = true;
                    this.faqFormError = '';
                    try {
                        const fd = new FormData();
                        fd.append('app_id', this.faqForm.app_id);
                        fd.append('file', this.faqForm.file);

                        const r = await fetch('/admin/faq/upload', {
                            method: 'POST', body: fd,
                            headers: { 'X-CSRF-TOKEN': CSRF, 'X-Requested-With': 'XMLHttpRequest' }
                        });
                        const d = await r.json();
                        if (!r.ok || !d.success) throw new Error(d.error || 'Erreur upload');

                        const entry = {
                            slug: d.slug, app_name: d.app_name, app_id: d.app_id,
                            version: '—', item_count: d.item_count, updated_at: d.updated_at
                        };
                        const idx = this.faqList.findIndex(f => f.slug === d.slug);
                        if (idx >= 0) this.faqList.splice(idx, 1, entry);
                        else this.faqList.unshift(entry);
                        this.faqModalOpen = false;
                        this.toast('FAQ "' + d.slug + '.json" ajoutée — ' + d.item_count + ' entrée(s)');
                    } catch (e) {
                        this.faqFormError = e.message;
                    } finally {
                        this.faqUploading = false;
                    }
                },

                async openJsonViewModal(faq) {
                    this.jsonViewFaq = faq;
                    this.jsonViewEntries = [];
                    this.jsonViewOpen = true;
                    try {
                        const r = await fetch('/admin/faq/' + encodeURIComponent(faq.app_id || faq.slug), {
                            headers: { 'X-Requested-With': 'XMLHttpRequest' }
                        });
                        const d = await r.json();
                        this.jsonViewEntries = d.faq || [];
                    } catch (e) {
                        this.toast('Erreur chargement JSON', false);
                    }
                },

                async openFaqEditModal(faq) {
                    this.faqEditFaq = faq;
                    this.faqEditEntries = [];
                    this.faqEditRaw = '';
                    this.faqEditError = '';
                    this.faqEditSaving = false;
                    try {
                        const r = await fetch('/admin/faq/' + encodeURIComponent(faq.app_id || faq.slug), {
                            headers: { 'X-Requested-With': 'XMLHttpRequest' }
                        });
                        const d = await r.json();
                        this.faqEditEntries = d.faq || [];
                        this.faqEditRaw = JSON.stringify(this.faqEditEntries, null, 2);
                    } catch (e) {
                        this.toast('Erreur chargement', false);
                    }
                    this.faqEditOpen = true;
                },

                async saveFaqEdit() {
                    this.faqEditError = '';
                    let parsed;
                    try {
                        const raw = this.faqEditRaw.trim();
                        const obj = JSON.parse(raw);
                        parsed = Array.isArray(obj) ? obj : (obj.items || []);
                        if (!Array.isArray(parsed)) throw new Error('Format invalide');
                    } catch (e) {
                        this.faqEditError = 'JSON invalide : ' + e.message;
                        return;
                    }
                    this.confirmAction(
                        'Enregistrer les modifications de "' + this.faqEditFaq.slug + '.json" et relancer l\'indexation Qdrant ?',
                        async () => {
                            this.faqEditSaving = true;
                            try {
                                const r = await fetch('/admin/faq/' + encodeURIComponent(this.faqEditFaq.app_id || this.faqEditFaq.slug), {
                                    method: 'PUT',
                                    headers: { 'Content-Type': 'application/json', 'X-CSRF-TOKEN': CSRF, 'X-Requested-With': 'XMLHttpRequest' },
                                    body: JSON.stringify({ items: parsed, reindex: 1 })
                                });
                                const d = await r.json();
                                if (!r.ok || !d.success) throw new Error(d.error || 'Erreur');
                                const idx = this.faqList.findIndex(f => f.slug === this.faqEditFaq.slug);
                                if (idx >= 0) {
                                    this.faqList[idx].item_count = d.item_count || parsed.length;
                                    this.faqList[idx].updated_at = formatFrenchDate(new Date());
                                }
                                this.faqEditOpen = false;
                                this.toast('FAQ "' + this.faqEditFaq.slug + '.json" mise à jour (' + parsed.length + ' entrées) — réindexation lancée');
                            } catch (e) {
                                this.faqEditError = e.message;
                            } finally {
                                this.faqEditSaving = false;
                            }
                        }
                    );
                },

                openFaqEditInfosModal(faq) {
                    this.faqEditInfosFaq = faq;
                    this.faqEditInfosForm = { app_name: faq.app_name || '' };
                    this.faqEditInfosError = '';
                    this.faqEditInfosSaving = false;
                    this.faqEditInfosOpen = true;
                },

                async saveFaqEditInfos() {
                    if (!this.faqEditInfosForm.app_name) return;
                    this.faqEditInfosSaving = true;
                    this.faqEditInfosError = '';
                    try {
                        const r = await fetch(
                            '/admin/faq/' + encodeURIComponent(this.faqEditInfosFaq.app_id || this.faqEditInfosFaq.slug) + '/infos',
                            {
                                method: 'PUT',
                                headers: { 'Content-Type': 'application/json', 'X-CSRF-TOKEN': CSRF, 'X-Requested-With': 'XMLHttpRequest' },
                                body: JSON.stringify({ app_name: this.faqEditInfosForm.app_name })
                            }
                        );
                        const d = await r.json();
                        if (!r.ok || !d.success) throw new Error(d.error || 'Erreur');
                        const idx = this.faqList.findIndex(f =>
                            this.faqEditInfosFaq.app_id ? f.app_id === this.faqEditInfosFaq.app_id : f.slug === this.faqEditInfosFaq.slug
                        );
                        if (idx >= 0) {
                            this.faqList[idx].app_name = d.app_name;
                            this.faqList[idx].slug     = d.slug;
                            this.faqList[idx].app_id   = d.app_id;
                        }
                        this.faqEditInfosOpen = false;
                        this.toast('Infos FAQ mises à jour');
                    } catch (e) {
                        this.faqEditInfosError = e.message;
                    } finally {
                        this.faqEditInfosSaving = false;
                    }
                },

                async deleteFaqFile(faq) {
                    try {
                        const r = await fetch('/admin/faq/' + encodeURIComponent(faq.app_id || faq.slug), {
                            method: 'DELETE',
                            headers: { 'X-CSRF-TOKEN': CSRF, 'X-Requested-With': 'XMLHttpRequest' }
                        });
                        const d = await r.json();
                        if (!r.ok || !d.success) throw new Error(d.error || 'Erreur');
                        this.faqList = this.faqList.filter(f => f.slug !== faq.slug);
                        this.toast('FAQ "' + faq.slug + '.json" supprimée');
                    } catch (e) {
                        this.toast(e.message, false);
                    }
                },

                async loadChats() {
                    if (!this.chatsAppId) return;
                    this.chatsLoading = true;
                    this.faqChats = [];
                    try {
                        const r = await fetch('/admin/faq/' + encodeURIComponent(this.chatsAppId) + '/chats', {
                            headers: { 'X-Requested-With': 'XMLHttpRequest' }
                        });
                        const d = await r.json();
                        if (!r.ok) throw new Error(d.error || 'Erreur');
                        this.faqChats = d.chats || [];
                        if (!this.faqChats.length) this.toast('Aucune conversation valide pour cette application');
                    } catch (e) {
                        this.toast(e.message, false);
                    } finally {
                        this.chatsLoading = false;
                    }
                },

                openReadModal(title, text, chat) {
                    this.readModalTitle = title;
                    this.readModalText  = text;
                    this.readModalChat  = chat;
                    this.readModalOpen  = true;
                },

                async rejectChat(chat, idx) {
                    if (!chat || !chat.assistant_id) return;
                    this.confirmAction('Rejeter cette réponse ? Elle sera marquée comme rejetée et ne pourra plus être validée.', async () => {
                        try {
                            const r = await fetch(
                                '/admin/faq/' + encodeURIComponent(this.chatsAppId) + '/chats/' + chat.assistant_id + '/reject',
                                { method: 'POST', headers: { 'X-CSRF-TOKEN': CSRF, 'X-Requested-With': 'XMLHttpRequest' } }
                            );
                            const d = await r.json();
                            if (!r.ok) throw new Error(d.error || 'Erreur');
                            if (idx !== null && this.faqChats[idx]) {
                                this.faqChats[idx] = { ...this.faqChats[idx], status: 'rejected', status_label: 'Rejetée' };
                            }
                            this.toast('Réponse rejetée');
                        } catch (e) {
                            this.toast(e.message, false);
                        }
                    });
                },

                openValidateModal(chat, idx = null) {
                    this.validateChat    = chat;
                    this.validateChatIdx = idx;
                    this.validateForm    = { question: chat.question || '', answer: chat.answer || '' };
                    this.validateError   = '';
                    this.validateOpen    = true;
                },

                async confirmValidate() {
                    if (!this.chatsAppId || !this.validateForm.question || !this.validateForm.answer) return;
                    this.validateSaving = true;
                    this.validateError  = '';
                    try {
                        const payload = {
                            question: this.validateForm.question,
                            answer:   this.validateForm.answer
                        };
                        if (this.validateChat && this.validateChat.assistant_id) {
                            payload.assistant_message_id = this.validateChat.assistant_id;
                        }

                        const r = await fetch(
                            '/admin/faq/' + encodeURIComponent(this.chatsAppId) + '/chats/validate',
                            {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json', 'X-CSRF-TOKEN': CSRF, 'X-Requested-With': 'XMLHttpRequest' },
                                body: JSON.stringify(payload)
                            }
                        );
                        const d = await r.json();
                        if (!r.ok || !d.success) throw new Error(d.error || 'Erreur validation');

                        if (this.validateChatIdx !== null && this.faqChats[this.validateChatIdx]) {
                            this.faqChats[this.validateChatIdx] = {
                                ...this.faqChats[this.validateChatIdx],
                                status: 'validated',
                                status_label: 'Validée'
                            };
                        }

                        const slug     = d.slug;
                        const existing = this.faqList.findIndex(f => f.slug === slug);
                        if (existing >= 0) {
                            this.faqList[existing].item_count = d.item_count;
                            this.faqList[existing].updated_at = formatFrenchDate(new Date());
                        } else {
                            this.faqList.unshift({
                                slug, app_name: d.app_name, app_id: d.app_id || this.chatsAppId,
                                version: d.version || '—', item_count: d.item_count,
                                updated_at: formatFrenchDate(new Date())
                            });
                        }

                        this.validateOpen = false;
                        this.toast(d.is_new_faq
                            ? '✓ Nouvelle FAQ créée pour "' + d.app_name + '" — réindexation lancée'
                            : '✓ Ajouté à la FAQ "' + d.app_name + '" (' + d.item_count + ' entrées) — réindexation lancée'
                        );
                    } catch (e) {
                        this.validateError = e.message;
                    } finally {
                        this.validateSaving = false;
                    }
                },
            }));
        });
    </script>
@endpush
