<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Symfony\Component\HttpFoundation\Response;

/**
 * Middleware EnsureAuthenticated
 * Redirige vers la page de login si l'utilisateur n'est pas connecté.
 */
class EnsureAuthenticated
{
    public function handle(Request $request, Closure $next): Response
    {
        if (!Auth::check()) {
            if ($request->expectsJson()) {
                return response()->json(['error' => 'Non authentifié.'], 401);
            }
            return redirect()->route('login')
                ->with('intended', $request->fullUrl());
        }
        return $next($request);
    }
}
