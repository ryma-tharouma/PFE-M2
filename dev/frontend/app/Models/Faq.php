<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Support\Str;

class Faq extends Model
{
    use HasFactory;

    protected $table = 'faq_items';

    protected $fillable = [
        'section_id',
        'application_id',
        'problem',
        'answer',
        'full_text',
        'source_type',
        'source',
        'title',
        'applies_to',
    ];

    // ----------------------------------------------------------------
    // Hooks
    // ----------------------------------------------------------------

    protected static function boot(): void
    {
        parent::boot();

        static::creating(function (self $item) {
            if (empty($item->section_id)) {
                $item->section_id = 'faq_' . Str::uuid();
            }
            // full_text : ne recalculer que s'il est vide
            if (empty($item->full_text)) {
                $item->full_text = static::buildFullText(
                    $item->problem,
                    $item->answer,
                    $item->title,
                    $item->applies_to
                );
            }
        });

        static::updating(function (self $item) {
            // Recalculer seulement si un champ source a changé
            // ET que full_text n'a pas été fourni explicitement
            $dirty = ['problem', 'answer', 'title', 'applies_to'];
            $hasDirtySource = collect($dirty)->contains(fn($f) => $item->isDirty($f));

            if ($hasDirtySource && !$item->isDirty('full_text')) {
                $item->full_text = static::buildFullText(
                    $item->problem,
                    $item->answer,
                    $item->title,
                    $item->applies_to
                );
            }
        });
    }

    // ----------------------------------------------------------------
    // Helper : construction du full_text selon les champs disponibles
    //
    // Règles :
    //  1. Si full_text déjà fourni → conservé tel quel (géré dans boot)
    //  2. Si title + applies_to présents :
    //       "Title: {title}\nApplies to: {applies_to}\n\nProblem:\n{problem}\n\nAnswer:\n{answer}"
    //  3. Si title seul :
    //       "Title: {title}\n\nProblem:\n{problem}\n\nAnswer:\n{answer}"
    //  4. Si rien :
    //       "problem: {problem}\nanswer: {answer}"
    // ----------------------------------------------------------------

    public static function buildFullText(
        string  $problem,
        string  $answer,
        ?string $title     = null,
        ?string $appliesTo = null
    ): string {
        $title     = $title     !== null ? trim($title)     : null;
        $appliesTo = $appliesTo !== null ? trim($appliesTo) : null;

        $hasTitle     = $title     !== null && $title     !== '';
        $hasAppliesTo = $appliesTo !== null && $appliesTo !== '';

        if ($hasTitle && $hasAppliesTo) {
            return "Title: {$title}\nApplies to: {$appliesTo}\n\nProblem:\n{$problem}\n\nAnswer:\n{$answer}";
        }

        if ($hasTitle) {
            return "Title: {$title}\n\nProblem:\n{$problem}\n\nAnswer:\n{$answer}";
        }

        // Format minimal — JSON manuels sans title
        return "problem: {$problem}\nanswer: {$answer}";
    }

    // ----------------------------------------------------------------
    // Relation
    // ----------------------------------------------------------------

    public function application(): BelongsTo
    {
        return $this->belongsTo(Application::class);
    }

    // ----------------------------------------------------------------
    // syncFromJson
    // ----------------------------------------------------------------

    /**
     * Importe (upsert) un tableau d'items FAQ pour une application donnée.
     *
     * Formats supportés :
     *  - JSON manuel  : section_id=UUID, pas de title/applies_to/full_text
     *  - JSON scrappé : section_id=int, title=string, applies_to=tableau,
     *                   full_text déjà calculé → conservé tel quel
     *
     * @param  int    $applicationId
     * @param  array  $items
     * @param  string $defaultSource
     * @return int    Nombre d'items importés/mis à jour
     */
    public static function syncFromJson(
        int    $applicationId,
        array  $items,
        string $defaultSource = 'admin'
    ): int {
        $count = 0;

        foreach ($items as $raw) {
            // ── Champs obligatoires ──────────────────────────────────
            $problem = trim((string) ($raw['problem'] ?? $raw['question'] ?? $raw['q'] ?? ''));
            $answer  = trim((string) ($raw['answer']  ?? $raw['a']        ?? ''));

            if ($problem === '' || $answer === '') {
                continue;
            }

            // ── section_id : rejeter les entiers → UUID ──────────────
            $sectionIdRaw = $raw['section_id'] ?? $raw['id'] ?? '';
            $sectionId    = is_array($sectionIdRaw) ? '' : trim((string) $sectionIdRaw);
            if ($sectionId === '' || is_numeric($sectionId)) {
                $sectionId = 'faq_' . Str::uuid();
            }

            // ── source ───────────────────────────────────────────────
            $rawSource = $raw['source'] ?? '';
            $source    = (is_array($rawSource) || trim((string) $rawSource) === '')
                ? $defaultSource
                : trim((string) $rawSource);

            // ── title : optionnel, jamais un tableau ─────────────────
            $titleRaw = $raw['title'] ?? null;
            $title    = null;
            if (isset($titleRaw) && !is_array($titleRaw)) {
                $t = trim((string) $titleRaw);
                $title = $t !== '' ? $t : null;
            }

            // ── applies_to : optionnel, tableau → string joint ───────
            $appliesToRaw = $raw['applies_to'] ?? null;
            $appliesTo    = null;
            if (is_array($appliesToRaw) && count($appliesToRaw) > 0) {
                $appliesTo = implode(', ', array_filter(array_map('trim', $appliesToRaw)));
            } elseif (is_string($appliesToRaw) && trim($appliesToRaw) !== '') {
                $appliesTo = trim($appliesToRaw);
            }

            // ── full_text : conserver si déjà présent dans le JSON ───
            // Sinon calculer selon les champs disponibles
            $fullTextRaw = $raw['full_text'] ?? null;
            $fullText    = (isset($fullTextRaw) && is_string($fullTextRaw) && trim($fullTextRaw) !== '')
                ? trim($fullTextRaw)
                : static::buildFullText($problem, $answer, $title, $appliesTo);

            self::updateOrCreate(
                ['section_id' => $sectionId],
                [
                    'application_id' => $applicationId,
                    'problem'        => $problem,
                    'answer'         => $answer,
                    'full_text'      => $fullText,
                    'source_type'    => 'faq',
                    'source'         => $source,
                    'title'          => $title,
                    'applies_to'     => $appliesTo,
                ]
            );

            $count++;
        }

        return $count;
    }

    // ----------------------------------------------------------------
    // Sérialisation → JSON FAQ (pipeline Python + disque)
    // ----------------------------------------------------------------

    public function toFaqArray(): array
    {
        return [
            'section_id'  => $this->section_id,
            'problem'     => $this->problem,
            'answer'      => $this->answer,
            'full_text'   => $this->full_text,
            'source_type' => $this->source_type,
            'source'      => $this->source,
            'title'       => $this->title,
            'applies_to'  => $this->applies_to,
        ];
    }
}
