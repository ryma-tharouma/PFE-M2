# rag.py
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from retriever import Retriever
from generator import Generator

logger = logging.getLogger(__name__)


# =============================================================================
# Rewriter
# =============================================================================

REWRITE_SYSTEM_PROMPT = (
     """
Résous les pronoms et ellipses de la question actuelle en utilisant la question précédente.
Si la question est déjà claire, retourne-la mot pour mot.
Retourne uniquement la question, sans explication.

Exemples :
"Comment créer un utilisateur ?" / "Comment lui modifier ses infos ?" → "Comment modifier les informations d'un utilisateur ?"
"Comment supprimer un utilisateur ?" / "Est-ce que c'est définitif ?" → "Est-ce que la suppression d'un utilisateur est définitive ?"
"Comment assigner un rôle ?" / "et pour le retirer ?" → "Comment retirer un rôle ?"
"Comment créer un utilisateur ?" / "Comment supprimer un utilisateur ?" → "Comment supprimer un utilisateur ?"
"""
)


class Rewriter:
    """
    Standalone query-rewriting model.

    Supports CPU inference via llama-cpp or GPU inference via HuggingFace
    Transformers.  The model is loaded lazily on the first rewrite() call.

    Config section: "rewriter"
        device         (str)   – "cpu" or "cuda"                   (default "cpu")
        max_new_tokens (int)   – tokens to generate                 (default 128)
        temperature    (float) – sampling temperature               (default 0.1)

        # CPU (llama-cpp)
        gguf_path      (str)   – path to GGUF file                  (required for cpu)
        n_ctx          (int)   – context window                     (default 2048)
        n_threads      (int)   – CPU threads                        (default 4)
        n_batch        (int)   – batch size                         (default 512)

        # GPU (HuggingFace)
        hf_model_name  (str)   – HuggingFace model id               (required for cuda)
        torch_dtype    (str)   – "float16" / "bfloat16" / "float32" (default "float16")
    """

    def __init__(self, config: Dict[str, Any]):
        cfg = config.get("rewriter", {})

        self.device         = cfg.get("device", "cpu")
        self.max_new_tokens = int(cfg.get("max_new_tokens", 128))
        self.temperature    = float(cfg.get("temperature", 0.1))

        # CPU
        self.gguf_path = cfg.get("gguf_path", "")
        self.n_ctx     = int(cfg.get("n_ctx", 2048))
        self.n_threads = int(cfg.get("n_threads", 4))
        self.n_batch   = int(cfg.get("n_batch", 512))

        # GPU
        self.hf_model_name = cfg.get("hf_model_name", "")
        self.torch_dtype   = cfg.get("torch_dtype", "float16")

        self._llm:       Any = None
        self._hf_model:  Any = None
        self._tokenizer: Any = None

    # ------------------------------------------------------------------
    # Lazy loaders
    # ------------------------------------------------------------------

    def _load_cpu(self) -> None:
        if self._llm is not None:
            return
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise RuntimeError(
                "llama-cpp-python is required for the CPU rewriter."
            ) from exc
        if not self.gguf_path:
            raise ValueError(
                "rewriter.gguf_path must be set in config.yaml when rewriter.device=cpu."
            )
        logger.info("Loading CPU rewriter from %s …", self.gguf_path)
        self._llm = Llama(
            model_path=self.gguf_path,
            n_ctx=self.n_ctx,
            n_threads=self.n_threads,
            n_batch=self.n_batch,
            verbose=False,
        )
        logger.info("CPU rewriter loaded.")

    def _load_gpu(self) -> None:
        if self._hf_model is not None:
            return
        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForCausalLM
        except ImportError as exc:
            raise RuntimeError(
                "torch and transformers are required for the GPU rewriter."
            ) from exc
        if not self.hf_model_name:
            raise ValueError(
                "rewriter.hf_model_name must be set in config.yaml when rewriter.device=cuda."
            )
        import torch
        dtype_map = {
            "float16":  torch.float16,
            "bfloat16": torch.bfloat16,
            "float32":  torch.float32,
        }
        dtype = dtype_map.get(self.torch_dtype, torch.float16)

        logger.info("Loading GPU rewriter %s …", self.hf_model_name)
        from transformers import AutoTokenizer, AutoModelForCausalLM
        self._tokenizer = AutoTokenizer.from_pretrained(self.hf_model_name)
        self._hf_model  = AutoModelForCausalLM.from_pretrained(
            self.hf_model_name,
            torch_dtype=dtype,
            device_map="auto",
        )
        self._hf_model.eval()
        logger.info("GPU rewriter loaded.")

    # ------------------------------------------------------------------
    # Inference helpers
    # ------------------------------------------------------------------

    def _build_messages(self, prev_query: str, current_query: str) -> List[Dict]:
        return [
            {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Question précédente: {prev_query}\n"
                    f"Question actuelle: {current_query}\n"
                    "Question reformulée:"
                ),
            },
        ]

    def _infer_cpu(self, prev_query: str, current_query: str) -> Tuple[str, float]:
        self._load_cpu()
        t0 = time.time()
        response = self._llm.create_chat_completion(
            messages=self._build_messages(prev_query, current_query),
            max_tokens=self.max_new_tokens,
            temperature=self.temperature,
            top_p=1.0,
            top_k=1,
            stream=False,
        )
        elapsed = time.time() - t0
        return response["choices"][0]["message"]["content"].strip(), elapsed

    def _infer_gpu(self, prev_query: str, current_query: str) -> Tuple[str, float]:
        import torch
        self._load_gpu()
        prompt = self._tokenizer.apply_chat_template(
            self._build_messages(prev_query, current_query),
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs    = self._tokenizer(prompt, return_tensors="pt").to(self._hf_model.device)
        input_len = inputs["input_ids"].shape[1]

        t0 = time.time()
        with torch.no_grad():
            outputs = self._hf_model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
                temperature=self.temperature,
                pad_token_id=self._tokenizer.eos_token_id,
                eos_token_id=self._tokenizer.eos_token_id,
            )
        elapsed   = time.time() - t0
        rewritten = self._tokenizer.decode(
            outputs[0][input_len:], skip_special_tokens=True
        ).strip()
        return rewritten, elapsed

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rewrite(self, prev_query: str, current_query: str) -> Tuple[str, float]:
        """
        Rewrite current_query into a standalone question.

        Args:
            prev_query    : last rewritten retrieval query (chained form)
            current_query : raw user input for this turn

        Returns:
            (rewritten_query, elapsed_seconds)
        """
        if self.device == "cuda":
            rewritten, elapsed = self._infer_gpu(prev_query, current_query)
        else:
            rewritten, elapsed = self._infer_cpu(prev_query, current_query)

        logger.debug(
            "Query rewritten in %.3fs | %r → %r", elapsed, current_query, rewritten
        )
        return rewritten, elapsed

    def cleanup(self) -> None:
        if self._llm is not None:
            try:
                self._llm.close()
            except Exception:
                pass
            self._llm = None
        self._hf_model  = None
        self._tokenizer = None


# =============================================================================
# Routing
# =============================================================================

def _determine_routing(
    section_ids: List[str],
    scores: List[float],
    threshold_1: float,
    threshold_2: float,
) -> str:
    """
    Return "faq" (fast path) when:
      1. The top score s1 exceeds the minimum relevance threshold θ (threshold_1).
      2. The absolute difference s1 - s2 exceeds the margin δ (threshold_2).
    Otherwise return "rag".
    """
    if not section_ids:
        return "rag"

    s1 = scores[0]

    # Condition 1: top section must be sufficiently relevant
    if s1 <= threshold_1:
        return "rag"

    # With only one section, condition 2 cannot be checked — fall back to rag
    if len(scores) < 2:
        return "rag"

    s2 = scores[1]

    # Condition 2: clear gap between top section and runner-up
    if (s1 - s2) > threshold_2:
        return "faq"

    return "rag"


# =============================================================================
# Section helpers
# =============================================================================

def _section_text(sec: Dict) -> str:
    if sec.get("source_type") == "faq":
        return sec.get("full_text", sec.get("answer", ""))
    return (
        f"[{sec.get('breadcrumb', '').upper()}]\n"
        f"{sec.get('content', '')}"
    ).strip()


def _section_source(sec: Dict) -> Dict:
    if sec.get("source_type") == "faq":
        return {"source": sec.get("source", "")}
    return {
        "source_pdf": sec.get("source_pdf", ""),
        "breadcrumb": sec.get("breadcrumb", ""),
    }


# =============================================================================
# RAG pipeline
# =============================================================================

class RAG:
    """
    Full retrieval-augmented generation pipeline.

    Query-context modes  (config section "query_context"):
        none    – retrieval uses the raw current query
        concat  – prepends the previous *original* user query via a template
        rewrite – a separate model rewrites the current query; the rewritten
                  form is stored and used as prev_query on the next turn
                  (always chaining from the last resolved phrasing)

    Sentinel dict (always the last item yielded by chat()):
        {
            "done"            : True,
            "sources"         : List[Dict],
            "retrieval_query" : str,        # echoed back for session storage
            # verbose only:
            "rewrite_sec"     : float,
            "embed_sec"       : float,
            "search_sec"      : float,
            "ttft_sec"        : float,
            "total_sec"       : float,
        }
    """

    def __init__(
        self,
        config: Dict[str, Any],
        retriever: Retriever,
        generator: Generator,
    ):
        rag_cfg = config.get("rag", {})
        self.routing_threshold = float(rag_cfg.get("routing_threshold", 3.0))

        qc_cfg = config.get("query_context", {})
        self.qc_mode: str = qc_cfg.get("mode", "none")
        self.qc_concat_template: str = qc_cfg.get(
            "concat_template",
            "requete precedente: {prev_query}. requete courante: {current_query}",
        )

        self.retriever = retriever
        self.generator = generator
        self._rewriter: Optional[Rewriter] = (
            Rewriter(config) if self.qc_mode == "rewrite" else None
        )

    # ------------------------------------------------------------------
    # Query context
    # ------------------------------------------------------------------

    def _build_retrieval_query(
        self,
        current_query: str,
        prev_original_query: str,
        prev_retrieval_query: str,
    ) -> Tuple[str, float]:
        """
        Build the query sent to the vector store.

        concat  uses prev_original_query  – raw user wording from the last turn
        rewrite uses prev_retrieval_query – already-resolved form from the last turn

        Returns (retrieval_query, rewrite_sec).
        """
        if self.qc_mode == "none":
            return current_query, 0.0

        if self.qc_mode == "concat":
            if not prev_original_query:          # first turn
                return current_query, 0.0
            q = self.qc_concat_template.format(
                prev_query=prev_original_query,
                current_query=current_query,
            )
            return q, 0.0

        if self.qc_mode == "rewrite":
            if not prev_retrieval_query:         # first turn
                return current_query, 0.0
            return self._rewriter.rewrite(
                prev_query=prev_retrieval_query,
                current_query=current_query,
            )

        logger.warning(
            "Unknown query_context.mode %r – using raw query.", self.qc_mode
        )
        return current_query, 0.0

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def chat(
        self,
        query: str,
        app_id: str,
        history: str = "",
        prev_original_query: str = "",
        prev_retrieval_query: str = "",
        verbose: bool = False,
    ):
        """
        Run one RAG turn.  Yields str tokens then a sentinel dict.

        Args:
            query                : raw user input this turn
            app_id               : Qdrant collection identifier
            history              : formatted history for the generator
            prev_original_query  : raw user query from the previous turn
                                   (concat mode; empty on first turn)
            prev_retrieval_query : rewritten retrieval query from the previous turn
                                   (rewrite mode; empty on first turn)
            verbose              : include timing fields in the sentinel
        """
        retrieval_query, rewrite_sec = self._build_retrieval_query(
            query, prev_original_query, prev_retrieval_query
        )

        section_ids, scores, metadatas, embed_sec, search_sec = self.retriever.retrieve(
            retrieval_query, app_id
        )

        if not section_ids:
            yield self._make_sentinel(
                sources=[], retrieval_query=retrieval_query, verbose=verbose,
                rewrite_sec=rewrite_sec, embed_sec=embed_sec, search_sec=search_sec,
            )
            return

        routing  = _determine_routing(section_ids, scores, self.routing_threshold)
        sections = metadatas

        if routing == "faq":
            yield from self._faq_path(
                sections, retrieval_query,
                embed_sec, search_sec, rewrite_sec, verbose,
            )
        else:
            yield from self._rag_path(
                query, sections, section_ids, retrieval_query,
                history, verbose, embed_sec, search_sec, rewrite_sec,
            )

    # ------------------------------------------------------------------
    # FAQ path
    # ------------------------------------------------------------------

    def _faq_path(
        self,
        sections: List[Dict],
        retrieval_query: str,
        embed_sec: float,
        search_sec: float,
        rewrite_sec: float,
        verbose: bool,
    ):
        top_sec = sections[0]
        answer  = top_sec.get("answer", top_sec.get("full_text", top_sec.get("content", "")))
        if answer:
            yield answer
        yield self._make_sentinel(
            sources=[_section_source(top_sec)],
            retrieval_query=retrieval_query,
            verbose=verbose,
            rewrite_sec=rewrite_sec,
            embed_sec=embed_sec,
            search_sec=search_sec,
        )

    # ------------------------------------------------------------------
    # RAG path
    # ------------------------------------------------------------------

    def _rag_path(
        self,
        query: str,
        sections: List[Dict],
        section_ids: List[str],
        retrieval_query: str,
        history: str,
        verbose: bool,
        embed_sec: float,
        search_sec: float,
        rewrite_sec: float,
    ):
        sources = [_section_source(sec) for sec in sections if sec]

        # Sort sections by id for a deterministic order passed to the generator
        sorted_sections = [
            sec for _, sec in sorted(
                ((sid, sec) for sid, sec in zip(section_ids, sections) if sec),
                key=lambda x: x[0],
            )
        ]
        section_texts = [_section_text(sec) for sec in sorted_sections]

        ttft_sec  = None
        total_sec = None

        # Always pass the original user query to the generator; retrieval has
        # already benefited from the enriched / rewritten form.
        for item in self.generator.generate(
            query=query,
            section_texts=section_texts,
            history=history,
            verbose=verbose,
        ):
            if isinstance(item, dict):
                ttft_sec  = item.get("ttft_sec")
                total_sec = item.get("total_sec")
            else:
                yield item

        yield self._make_sentinel(
            sources=sources,
            retrieval_query=retrieval_query,
            verbose=verbose,
            rewrite_sec=rewrite_sec,
            embed_sec=embed_sec,
            search_sec=search_sec,
            ttft_sec=ttft_sec,
            total_sec=total_sec,
        )

    # ------------------------------------------------------------------
    # Sentinel builder
    # ------------------------------------------------------------------

    @staticmethod
    def _make_sentinel(
        *,
        sources: List[Dict],
        retrieval_query: str,
        verbose: bool,
        rewrite_sec: float = 0.0,
        embed_sec: float   = 0.0,
        search_sec: float  = 0.0,
        ttft_sec:  Optional[float] = None,
        total_sec: Optional[float] = None,
    ) -> Dict:
        sentinel: Dict = {
            "done":             True,
            "sources":          sources,
            "retrieval_query":  retrieval_query,
        }
        if verbose:
            sentinel["rewrite_sec"] = rewrite_sec
            sentinel["embed_sec"]   = embed_sec
            sentinel["search_sec"]  = search_sec
            sentinel["ttft_sec"]    = ttft_sec
            sentinel["total_sec"]   = total_sec
        return sentinel

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        if self._rewriter is not None:
            self._rewriter.cleanup()