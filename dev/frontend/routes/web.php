<?php

use App\Http\Controllers\Admin\AdminController;
use App\Http\Controllers\Auth\LdapAuthController;
use App\Http\Controllers\Chat\ChatController;
use App\Http\Controllers\GlpiWebhookController;
use App\Http\Controllers\TicketController;
use Illuminate\Support\Facades\Route;

// ── Publiques ─────────────────────────────────────────────────────────
Route::middleware(['guest'])->group(function () {
    Route::get('/login',  [LdapAuthController::class, 'showLogin'])->name('login');
    Route::post('/login', [LdapAuthController::class, 'login'])->name('auth.login');
});

Route::post('/logout', [LdapAuthController::class, 'logout'])
    ->middleware('auth')
    ->name('auth.logout');

Route::get('/', function () {
    return auth()->check()
        ? redirect()->route('chat.index')
        : redirect()->route('login');
});

// ── Webhook GLPI ──────────────────────────────────────────────────────
// Hors auth + hors CSRF car GLPI appelle depuis l'extérieur
Route::post('/webhook/glpi/response', [GlpiWebhookController::class, 'handle'])
    ->name('webhook.glpi.response')
    ->withoutMiddleware([\App\Http\Middleware\VerifyCsrfToken::class]);

// ── Protégées ─────────────────────────────────────────────────────────
Route::middleware(['auth', \App\Http\Middleware\EnsureAuthenticated::class])->group(function () {

    Route::prefix('chat')->name('chat.')->group(function () {
        Route::get('/',                     [ChatController::class, 'index'])            ->name('index');
        Route::get('/conversations',        [ChatController::class, 'getConversations']) ->name('conversations');
        Route::post('/conversation/new',    [ChatController::class, 'newConversation'])  ->name('conversation.new');
        Route::get('/conversation/{id}',    [ChatController::class, 'getConversation'])  ->name('conversation');
        Route::delete('/conversation/{id}', [ChatController::class, 'deleteConversation'])->name('conversation.delete');
        Route::post('/message/init',        [ChatController::class, 'initMessage'])      ->name('message.init');
        Route::post('/message/finalize',    [ChatController::class, 'finalizeMessage'])  ->name('message.finalize');
    });

    Route::post('/ticket/create', [TicketController::class, 'create'])->name('ticket.create');

    // ── Admin ─────────────────────────────────────────────────────────
    Route::middleware([\App\Http\Middleware\EnsureIsAdmin::class])
        ->prefix('admin')->name('admin.')
        ->group(function () {

            Route::get('/', [AdminController::class, 'dashboard'])->name('index');
            Route::get('/app-dashboard', [AdminController::class, 'adminDashboard'])->name('app-dashboard');
            // ── Admin Management ──────────────────────────────────────
            Route::get('/admins', [AdminController::class, 'getAdmins'])->name('getAdmins');
            Route::post('/admins', [AdminController::class, 'addAdmin'])->name('addAdmin');
            Route::delete('/admins/{user_id}', [AdminController::class, 'removeAdmin'])->name('removeAdmin');
            Route::get('/available-admins', [AdminController::class, 'getAvailableAdmins'])->name('getAvailableAdmins');
            Route::get('/applications/{id}', [AdminController::class, 'showApplication'])->name('showApplication');


            // ── Application Management ────────────────────────────────
            Route::get('/applications', [AdminController::class, 'getApplications'])->name('getApplications');
            Route::post('/applications', [AdminController::class, 'storeApplication'])->name('storeApplication');
            Route::put('/applications/{app_id}', [AdminController::class, 'updateApplication'])->name('updateApplication');
            Route::delete('/applications/{app_id}', [AdminController::class, 'destroyApplication'])->name('destroyApplication');

            // ── Application Users Management ──────────────────────────
            Route::get('/applications/{app_id}/users', [AdminController::class, 'getApplicationUsers'])->name('getApplicationUsers');
            Route::post('/applications/{app_id}/users', [AdminController::class, 'addApplicationUser'])->name('addApplicationUser');
            Route::delete('/applications/{app_id}/users/{user_id}', [AdminController::class, 'removeApplicationUser'])->name('removeApplicationUser');

            // ── Available Data for Forms ──────────────────────────────
            Route::get('/available-users', [AdminController::class, 'getAvailableUsers'])->name('getAvailableUsers');
            Route::get('/departments', [AdminController::class, 'getDepartments'])->name('getDepartments');

            Route::prefix('manuals')->name('manuals.')->group(function () {
                Route::get('/check-app',   [AdminController::class, 'checkAppVersion'])->name('check-app');
                Route::post('/',           [AdminController::class, 'storeManual'])    ->name('store');
                Route::get('/{id}',        [AdminController::class, 'showManual'])     ->name('show');
                Route::put('/{id}',        [AdminController::class, 'updateManual'])   ->name('update');
                Route::delete('/{id}',     [AdminController::class, 'destroyManual'])  ->name('destroy');
            });

            Route::prefix('faq')->name('faq.')->group(function () {
                Route::get('/',                                [AdminController::class, 'faqDashboard'])   ->name('dashboard');
                Route::post('/upload',                         [AdminController::class, 'faqUpload'])      ->name('upload');
                Route::get('/{app}',                           [AdminController::class, 'faqShow'])        ->name('show');
                Route::put('/{app}',                           [AdminController::class, 'faqUpdate'])      ->name('update');
                Route::put('/{app}/infos',                     [AdminController::class, 'faqUpdateInfos']) ->name('update.infos');
                Route::delete('/{app}',                        [AdminController::class, 'faqDestroy'])     ->name('destroy');
                Route::post('/{app}/index',                    [AdminController::class, 'faqIndex'])       ->name('index');
                Route::get('/{app}/chats',                     [AdminController::class, 'chatsShow'])      ->name('chats.show');
                Route::post('/{app}/chats/validate',           [AdminController::class, 'chatValidate'])   ->name('chats.validate');
                Route::post('/{app}/chats/{messageId}/reject', [AdminController::class, 'chatReject'])     ->name('chats.reject');
            });
        });
});


