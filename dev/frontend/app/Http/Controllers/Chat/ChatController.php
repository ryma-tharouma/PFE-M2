<?php

namespace App\Http\Controllers\Chat;

use App\Http\Controllers\Controller;
use App\Models\Application;
use App\Models\Conversation;
use App\Models\Message;
use App\Models\Manual;
use App\Events\MessageCreated;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Log;

class ChatController extends Controller
{
    // ══════════════════════════════════════════════════════════════
    //  Page principale
    // ══════════════════════════════════════════════════════════════
    public function index()
    {
        // Uniquement les apps NON archivées et qui ont une collection Qdrant prête
        // (qdrant_collection est rempli par le pipeline après indexation)
        $applications = Application::whereNotNull('qdrant_collection')
            ->where('archived', false)
            ->orderBy('name')
            ->get();

        $conversations = Conversation::where('user_id', Auth::id())
            ->with('application')
            ->orderByDesc('last_message_at')
            ->orderByDesc('updated_at')
            ->take(50)
            ->get()
            ->map(fn($c) => [
                'id'         => $c->id,
                'app_id'     => $c->application_id,
                'app_name'   => $c->application->name  ?? 'App',
                'app_color'  => $c->application->color ?? '#F26522',
                'app_icon'   => $c->application->icon  ?? '📄',
                'title'      => $c->title ?? 'Conversation',
                'archived'   => (bool) optional($c->application)->archived,
                'updated_at' => $c->last_message_at?->toDateTimeString()
                    ?? $c->updated_at?->toDateTimeString(),
            ]);

        return view('chat.index', compact('applications', 'conversations'));
    }

    // ══════════════════════════════════════════════════════════════
    //  Nouvelle conversation vierge
    // ══════════════════════════════════════════════════════════════
    public function newConversation(Request $request): JsonResponse
    {
        $request->validate([
            'app_id' => ['required', 'integer', 'exists:applications,id'],
        ]);

        $conversation = Conversation::create([
            'user_id'         => Auth::id(),
            'application_id'  => $request->integer('app_id'),
            'title'           => null,
            'started_at'      => now(),
            'last_message_at' => now(),
        ]);

        return response()->json([
            'success'         => true,
            'conversation_id' => $conversation->id,
        ]);
    }

    // ══════════════════════════════════════════════════════════════
    //  ÉTAPE 1 — Init message
    // ══════════════════════════════════════════════════════════════
    public function initMessage(Request $request): JsonResponse
    {
        $request->validate([
            'message'         => ['required', 'string', 'max:4000'],
            'app_id'          => ['required', 'integer', 'exists:applications,id'],
            'conversation_id' => ['nullable', 'integer'],
        ]);

        try {
            $userId  = Auth::id();
            $appId   = $request->integer('app_id');
            $text    = trim($request->string('message'));
            $convId  = $request->integer('conversation_id') ?: null;
            $askedAt = now();

            // ── Récupère la collection Qdrant depuis la DB ─────────────
            $app        = Application::findOrFail($appId);
            $collection = $app->qdrant_collection;

            if (!$collection) {
                return response()->json([
                    'success' => false,
                    'error'   => "L'application « {$app->name} » n'est pas encore indexée. Veuillez patienter.",
                ], 422);
            }

            // ── Retrouver le manual_id depuis la collection ─────────────
            $manual = Manual::where('application_id', $appId)
                ->whereNotNull('cleaned_json_path')
                ->where('status', 'indexed')
                ->first();
            $manualId = $manual?->id;

            $conversation = $this->resolveConversation($userId, $appId, $convId, $manualId);

            Message::create([
                'conversation_id' => $conversation->id,
                'role'            => 'user',
                'content'         => $text,
                'manual_id'       => $manualId,
                'asked_at'        => $askedAt,
            ]);

            if (!$conversation->title) {
                $conversation->update([
                    'title'           => mb_substr($text, 0, 60),
                    'started_at'      => $conversation->started_at ?? $askedAt,
                    'last_message_at' => $askedAt,
                ]);
            } else {
                $conversation->update(['last_message_at' => $askedAt]);
            }

            return response()->json([
                'success'         => true,
                'conversation_id' => $conversation->id,
                'collection'      => $collection,       // ← nom exact Qdrant
                'user_id'         => (string) $userId,
                'ws_url'          => config('services.chatbot.ws_url', 'ws://127.0.0.1:8000/ws/chat'),
                'asked_at'        => $askedAt->toDateTimeString(),
            ]);

        } catch (\Exception $e) {
            Log::error('initMessage', ['error' => $e->getMessage()]);
            return response()->json(['success' => false, 'error' => $e->getMessage()], 500);
        }
    }

    // ══════════════════════════════════════════════════════════════
    //  ÉTAPE 2 — Finalize
    // ══════════════════════════════════════════════════════════════
    public function finalizeMessage(Request $request): JsonResponse
    {
        $request->validate([
            'conversation_id'   => ['required', 'integer'],
            'response'          => ['required', 'string'],
            'collection'        => ['required', 'string', 'max:255'],
            'sources'           => ['nullable', 'array'],
            'asked_at'          => ['nullable', 'string'],
            'response_time_sec' => ['nullable', 'numeric'],
        ]);

        try {
            $conversation = Conversation::where('id', $request->integer('conversation_id'))
                ->where('user_id', Auth::id())
                ->firstOrFail();

            $answeredAt      = now();
            $askedAt         = $request->string('asked_at')
                ? \Carbon\Carbon::parse($request->string('asked_at'))
                : null;
            $responseTimeSec = $request->float('response_time_sec')
                ?? ($askedAt ? $answeredAt->diffInSeconds($askedAt) : null);

            $msg = Message::create([
                'conversation_id'   => $conversation->id,
                'role'              => 'assistant',
                'content'           => (string) $request->string('response'),
                'sources'           => $request->input('sources', []),
                'collection'        => (string) $request->string('collection'),
                'manual_id'         => $conversation->manual_id,
                'confidence'        => 0.0,
                'needs_escalation'  => false,
                'answered_at'       => $answeredAt,
                'asked_at'          => $askedAt,
                'response_time_sec' => $responseTimeSec,
            ]);

            $conversation->update(['last_message_at' => $answeredAt]);

            try { event(new MessageCreated($msg)); }
            catch (\Exception $e) { Log::warning('Broadcast: ' . $e->getMessage()); }

            return response()->json(['success' => true, 'message_id' => $msg->id]);

        } catch (\Exception $e) {
            Log::error('finalizeMessage', ['error' => $e->getMessage()]);
            return response()->json(['success' => false, 'error' => $e->getMessage()], 500);
        }
    }

    // ══════════════════════════════════════════════════════════════
    //  Charger une conversation
    // ══════════════════════════════════════════════════════════════
    public function getConversation(int $id): JsonResponse
    {
        $conv = Conversation::where('id', $id)
            ->where('user_id', Auth::id())
            ->with(['messages', 'application'])
            ->firstOrFail();

        return response()->json([
            'id'       => $conv->id,
            'app_id'   => $conv->application_id,
            'app_name' => $conv->application->name ?? 'App',
            'archived' => (bool) optional($conv->application)->archived,
            'title'    => $conv->title,
            'messages' => $conv->messages->map(fn($m) => [
                'id'                => $m->id,
                'role'              => $m->role,
                'content'           => $m->content,
                'sources'           => $m->sources ?? [],
                'collection'        => $m->collection,
                'response_time_sec' => $m->response_time_sec,
                'asked_at'          => $m->asked_at?->toDateTimeString(),
                'answered_at'       => $m->answered_at?->toDateTimeString(),
                'time'              => $m->created_at->format('H:i'),
            ]),
        ]);
    }

    // ══════════════════════════════════════════════════════════════
    //  Liste conversations (sidebar)
    // ══════════════════════════════════════════════════════════════
    public function getConversations(): JsonResponse
    {
        $conversations = Conversation::where('user_id', Auth::id())
            ->with('application')
            ->orderByDesc('last_message_at')
            ->orderByDesc('updated_at')
            ->take(50)
            ->get()
            ->map(fn($c) => [
                'id'        => $c->id,
                'app_id'    => $c->application_id,
                'app_name'  => $c->application->name  ?? 'App',
                'app_color' => $c->application->color ?? '#F26522',
                'app_icon'  => $c->application->icon  ?? '📄',
                'title'     => $c->title ?? 'Conversation',
                'archived'  => (bool) optional($c->application)->archived,
                'updated_at'=> $c->last_message_at?->toDateTimeString()
                    ?? $c->updated_at?->toDateTimeString(),
            ]);

        return response()->json(['conversations' => $conversations]);
    }

    // ══════════════════════════════════════════════════════════════
    //  Supprimer une conversation
    // ══════════════════════════════════════════════════════════════
    public function deleteConversation(int $id): JsonResponse
    {
        try {
            $conversation = Conversation::with('application')
                ->where('id', $id)
                ->where('user_id', Auth::id())
                ->firstOrFail();

            if (optional($conversation->application)->archived) {
                return response()->json([
                    'success' => false,
                    'error'   => "Cette conversation est archivée et ne peut plus être supprimée (traçabilité).",
                ], 403);
            }

            $conversation->delete();

            return response()->json(['success' => true]);

        } catch (\Illuminate\Database\Eloquent\ModelNotFoundException) {
            return response()->json(['success' => false, 'error' => 'Conversation non trouvée'], 404);
        } catch (\Exception $e) {
            Log::error('deleteConversation', ['error' => $e->getMessage()]);
            return response()->json(['success' => false, 'error' => 'Erreur lors de la suppression'], 500);
        }
    }

    // ══════════════════════════════════════════════════════════════
    //  Helper
    // ══════════════════════════════════════════════════════════════
    private function resolveConversation(int $userId, int $appId, ?int $convId, ?int $manualId = null): Conversation
    {
        if ($convId) {
            $c = Conversation::where('id', $convId)
                ->where('user_id', $userId)
                ->where('application_id', $appId)
                ->first();
            if ($c) return $c;
        }

        return Conversation::create([
            'user_id'         => $userId,
            'application_id'  => $appId,
            'manual_id'       => $manualId,
            'title'           => null,
            'started_at'      => now(),
            'last_message_at' => now(),
        ]);
    }
}
