<?php

namespace App\Jobs;

use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Facades\Log;

class ProcessFaqPipeline implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    public int $timeout = 900;
    public int $tries = 3;

    public function __construct(private readonly string $action = 'sync') {}

    public function handle(): void
    {
        $backendUrl = rtrim((string) config('services.backend.url', 'http://127.0.0.1:8000'), '/');
        $endpoint = $this->action === 'delete'
            ? $backendUrl . '/api/admin/faq/sync'
            : $backendUrl . '/api/admin/faq/sync';

        try {
            $client = new \GuzzleHttp\Client(['timeout' => 120]);
            $response = $client->post($endpoint);
            $data = json_decode((string) $response->getBody(), true);

            Log::info('[FAQ Pipeline] Synchronisation terminée', [
                'action' => $this->action,
                'success' => $data['success'] ?? null,
                'count' => $data['count'] ?? null,
            ]);
        } catch (\Throwable $e) {
            Log::warning('[FAQ Pipeline] Synchronisation échouée', [
                'action' => $this->action,
                'error' => $e->getMessage(),
            ]);
            throw $e;
        }
    }
}

