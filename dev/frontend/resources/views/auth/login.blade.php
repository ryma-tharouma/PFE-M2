@extends('layouts.app')

@section('title', 'Connexion — Sonatrach Assistant IA')

@push('styles')
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600&family=DM+Sans:wght@300;400;500;600&display=swap');

        :root {
            --orange: #E8590C;
            --orange-dark: #C24A09;
            --noir: #1a1a1a;
            --gris-bord: #E2E2E2;
        }

        * { box-sizing: border-box; }

        body {
            margin: 0;
            font-family: 'DM Sans', sans-serif;
        }

        /* ── Pattern LV-style : grille de logos répétés ── */
        .login-bg {
            position: relative;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            background-color: #f0ede8;
        }

        /* Couche 1 — petits logos en damier diagonal */
        .login-bg::before {
            content: '';
            position: absolute;
            inset: -10%;
            width: 120%;
            height: 120%;

            /* On génère le pattern via background-image répété */
            background-image: url("{{ asset('assets/images/logo.png') }}");
            background-repeat: repeat;
            background-size: 90px 90px;           /* taille de chaque logo dans la grille */
            background-position: 0 0;

            /* Rotation 30° pour l'effet LV */
            transform: rotate(30deg) scale(1.6);

            opacity: 0.055;
            filter: grayscale(100%) contrast(120%);
            pointer-events: none;
            z-index: 0;
        }

        /* Couche 2 — léger voile pour adoucir */
        .login-bg::after {
            content: '';
            position: absolute;
            inset: 0;
            background: linear-gradient(
                135deg,
                rgba(240, 237, 232, 0.5) 0%,
                rgba(240, 237, 232, 0.1) 50%,
                rgba(240, 237, 232, 0.5) 100%
            );
            pointer-events: none;
            z-index: 0;
        }

        /* ── Card ── */
        .login-card {
            position: relative;
            z-index: 1;
            width: 100%;
            max-width: 420px;
            padding: 0 1rem;
            animation: fadeUp 0.55s cubic-bezier(.22,1,.36,1) both;
        }

        @keyframes fadeUp {
            from { opacity: 0; transform: translateY(24px); }
            to   { opacity: 1; transform: translateY(0); }
        }

        /* ── Header logo ── */
        .login-header {
            text-align: center;
            margin-bottom: 2rem;
            display: flex;
            flex-direction: column;
            align-items: center;
        }

        .login-header img {
            height: 110px;
            width: auto;
            object-fit: contain;
            filter: drop-shadow(0 2px 10px rgba(232,89,12,0.15));
        }

        .login-header .subtitle {
            font-family: 'DM Sans', sans-serif;
            font-size: 0.78rem;
            font-weight: 400;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: #888;
            margin-top: 0.75rem;
        }

        /* ── Formulaire ── */
        .login-form-box {
            background: rgba(255,255,255,0.88);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.9);
            box-shadow:
                0 4px 6px -1px rgba(0,0,0,0.06),
                0 20px 60px -10px rgba(0,0,0,0.12),
                inset 0 1px 0 rgba(255,255,255,0.8);
            padding: 2.2rem 2rem;
        }

        /* Erreur */
        .error-block {
            margin-bottom: 1.25rem;
            padding: 0.75rem 1rem;
            background: #fef2f2;
            border: 1px solid #fecaca;
            border-radius: 10px;
            display: flex;
            align-items: flex-start;
            gap: 0.5rem;
        }
        .error-block svg { flex-shrink: 0; color: #ef4444; margin-top: 1px; }
        .error-block p { font-size: 0.82rem; color: #b91c1c; margin: 0; }

        /* Champs */
        .field { margin-bottom: 1.15rem; }

        .field label {
            display: block;
            font-size: 0.78rem;
            font-weight: 500;
            color: #555;
            letter-spacing: 0.04em;
            margin-bottom: 0.45rem;
        }

        .field-wrap {
            position: relative;
        }

        .field-wrap .icon {
            position: absolute;
            left: 12px;
            top: 50%;
            transform: translateY(-50%);
            color: #aaa;
            pointer-events: none;
            display: flex;
        }

        .field-wrap input {
            width: 100%;
            padding: 0.68rem 2.5rem 0.68rem 2.6rem;
            font-size: 0.875rem;
            font-family: 'DM Sans', sans-serif;
            border: 1.5px solid var(--gris-bord);
            border-radius: 10px;
            background: #fafafa;
            transition: border-color 0.2s, box-shadow 0.2s, background 0.2s;
            outline: none;
            color: var(--noir);
        }

        .field-wrap input::placeholder { color: #c0c0c0; }

        .field-wrap input:focus {
            border-color: var(--orange);
            background: #fff;
            box-shadow: 0 0 0 3px rgba(232,89,12,0.12);
        }

        .field-wrap input.has-error { border-color: #f87171; }

        .field-error {
            font-size: 0.73rem;
            color: #dc2626;
            margin-top: 0.3rem;
        }

        /* Bouton toggle mot de passe */
        .toggle-pass {
            position: absolute;
            right: 10px;
            top: 50%;
            transform: translateY(-50%);
            background: none;
            border: none;
            cursor: pointer;
            color: #bbb;
            padding: 4px;
            display: flex;
            transition: color 0.15s;
        }
        .toggle-pass:hover { color: #777; }

        /* Séparateur décoratif */
        .divider {
            height: 1px;
            background: linear-gradient(to right, transparent, #e5e5e5, transparent);
            margin: 1.5rem 0;
        }

        /* Bouton submit */
        .btn-submit {
            width: 100%;
            padding: 0.78rem 1rem;
            border-radius: 10px;
            font-family: 'DM Sans', sans-serif;
            font-size: 0.875rem;
            font-weight: 600;
            letter-spacing: 0.04em;
            color: #fff;
            background: linear-gradient(135deg, var(--orange) 0%, var(--orange-dark) 100%);
            border: none;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            box-shadow: 0 4px 14px rgba(232,89,12,0.35);
        }

        .btn-submit:hover:not(:disabled) {
            transform: translateY(-1px);
            box-shadow: 0 6px 20px rgba(232,89,12,0.45);
        }

        .btn-submit:active:not(:disabled) { transform: translateY(0); }
        .btn-submit:disabled { opacity: 0.6; cursor: not-allowed; }

        /* Spin */
        @keyframes spin { to { transform: rotate(360deg); } }
        .spin { animation: spin 0.8s linear infinite; }

        /* Note bas */
        .note-bas {
            text-align: center;
            font-size: 0.72rem;
            color: #aaa;
            letter-spacing: 0.06em;
            margin-top: 1.4rem;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.4rem;
        }
        .note-bas::before,
        .note-bas::after {
            content: '';
            flex: 1;
            height: 1px;
            background: linear-gradient(to right, transparent, #d5d5d5);
        }
        .note-bas::after { background: linear-gradient(to left, transparent, #d5d5d5); }
    </style>
@endpush

@section('content')
    <div class="login-bg">
        <div class="login-card" x-data="{ loading: false, showPass: false }">

            {{-- Logo principal (couleur) sans le mot Sonatrach --}}
            <div class="login-header">
                <img src="{{ asset('assets/images/logo.png') }}" alt="Sonatrach">
                <p class="subtitle">Assistant IA &mdash; Help Desk</p>
            </div>

            {{-- Carte formulaire --}}
            <div class="login-form-box">

                {{-- Erreur d'authentification --}}
                @if ($errors->has('username') || $errors->has('login'))
                    <div class="error-block">
                        <svg width="16" height="16" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>
                        </svg>
                        <p>{{ $errors->first('username') ?: $errors->first('login') }}</p>
                    </div>
                @endif

                <form method="POST" action="{{ route('auth.login') }}"
                      @submit="loading = true">
                    @csrf

                    {{-- Identifiant --}}
                    <div class="field">
                        <label for="username">Identifiant</label>
                        <div class="field-wrap">
                        <span class="icon">
                            <svg width="15" height="15" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                      d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>
                            </svg>
                        </span>
                            <input type="text"
                                   id="username"
                                   name="username"
                                   value="{{ old('username') }}"
                                   required
                                   autocomplete="username"
                                   placeholder="identifiant son"
                                   class="{{ $errors->has('username') ? 'has-error' : '' }}">
                        </div>
                        @error('username')
                        <p class="field-error">{{ $message }}</p>
                        @enderror
                    </div>

                    {{-- Mot de passe --}}
                    <div class="field">
                        <label for="password">Mot de passe</label>
                        <div class="field-wrap">
                        <span class="icon">
                            <svg width="15" height="15" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                      d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/>
                            </svg>
                        </span>
                            <input :type="showPass ? 'text' : 'password'"
                                   id="password"
                                   name="password"
                                   required
                                   autocomplete="current-password"
                                   placeholder="••••••••">
                            <button type="button"
                                    class="toggle-pass"
                                    @click="showPass = !showPass"
                                    tabindex="-1">
                                <svg x-show="!showPass" width="15" height="15" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                          d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                          d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>
                                </svg>
                                <svg x-show="showPass" width="15" height="15" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                          d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 4.411m0 0L21 21"/>
                                </svg>
                            </button>
                        </div>
                    </div>

                    <div class="divider"></div>

                    {{-- Bouton connexion --}}
                    <button type="submit"
                            class="btn-submit"
                            :disabled="loading">
                        <svg x-show="loading" class="spin" width="16" height="16" fill="none" viewBox="0 0 24 24">
                            <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" class="opacity-25"/>
                            <path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" class="opacity-75"/>
                        </svg>
                        <span x-text="loading ? 'Connexion en cours…' : 'Se connecter'">Se connecter</span>
                    </button>

                </form>
            </div>

            {{-- Note LDAP --}}
            <p class="note-bas">Authentification AD Sonatrach</p>

        </div>
    </div>
@endsection
