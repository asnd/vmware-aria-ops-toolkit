"""Retrieval engine with hybrid LanceDB search and lightweight reranking."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from llama_index.core.vector_stores.types import (
    VectorStoreQuery,
    VectorStoreQueryMode,
    VectorStoreQueryResult,
)
from llama_index.embeddings.litellm import LiteLLMEmbedding
from llama_index.vector_stores.lancedb import LanceDBVectorStore
from llama_index.vector_stores.lancedb.base import TableNotFoundError

from src.config import Settings, get_settings

logger = logging.getLogger(__name__)

TOKEN_PATTERN = re.compile(r"[a-z0-9]{2,}")
RESOLUTION_HINTS = ("fix", "resolve", "solution", "how to", "how do", "workaround")
CAUSE_HINTS = ("cause", "why", "root cause")
SYMPTOM_HINTS = ("issue", "error", "failure", "fails", "problem", "symptom")
RERANKING_VECTOR_WEIGHT = 0.15
RERANKING_LEXICAL_WEIGHT = 0.85
ELLIPSIS_LENGTH = 3


@dataclass(slots=True)
class RetrievedChunk:
    """Normalized search result returned by the retrieval engine."""

    text: str
    score: float
    article_number: str
    title: str
    url: str
    product: str
    section_type: str
    section_heading: str
    metadata: dict[str, Any]


def _tokenize(text: str) -> set[str]:
    """Tokenize free-form text into simple lowercase terms."""
    return set(TOKEN_PATTERN.findall(text.lower()))


def _normalize_scores(scores: list[float]) -> list[float]:
    """Normalize arbitrary scores to a stable 0-1 range."""
    if not scores:
        return []

    low = min(scores)
    high = max(scores)
    if high == low:
        return [0.5 for _ in scores]
    return [(score - low) / (high - low) for score in scores]


class RetrievalEngine:
    """Query LanceDB and rerank the returned chunks for KB-style questions."""

    def __init__(
        self,
        settings: Settings | None = None,
        vector_store: LanceDBVectorStore | None = None,
        embed_model: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._vector_store = vector_store or self._build_vector_store()
        self._embed_model = embed_model or self._build_embed_model()

    def _build_vector_store(self) -> LanceDBVectorStore:
        """Open the persisted LanceDB vector store, creating it if no data has been ingested yet."""
        import lancedb as _lancedb

        lancedb_path = Path(self.settings.lancedb_path)
        lancedb_path.mkdir(parents=True, exist_ok=True)

        db = _lancedb.connect(str(lancedb_path))
        mode = "append" if "vectors" in db.table_names() else "overwrite"

        store = LanceDBVectorStore(
            uri=str(lancedb_path),
            mode=mode,
            query_type="hybrid",
        )
        # FTS index is pre-built at ingest time; skip recreation on every query
        # to avoid RuntimeError commit conflicts under concurrent requests.
        store._fts_index_ready = True
        return store

    def _build_embed_model(self) -> LiteLLMEmbedding:
        """Create the LiteLLM embedding client used for query embeddings."""
        self.settings.validate_litellm_api_key()
        return LiteLLMEmbedding(
            model_name=self.settings.resolved_embedding_model(),
            api_base=self.settings.resolved_litellm_base_url(),
            api_key=self.settings.litellm_api_key,
        )

    def search(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        """Run hybrid search followed by lightweight reranking."""
        cleaned_query = query.strip()
        if not cleaned_query:
            return []

        similarity_top_k = top_k or self.settings.retrieval_similarity_top_k
        query_embedding = self._embed_model.get_query_embedding(cleaned_query)
        search_result = self._query_vector_store(
            cleaned_query=cleaned_query,
            query_embedding=query_embedding,
            similarity_top_k=similarity_top_k,
        )
        candidates = self._to_retrieved_chunks(search_result)
        if not candidates:
            return []
        reranked = self._rerank(cleaned_query, candidates)
        limit = min(self.settings.reranker_top_n, len(reranked))
        return reranked[:limit]

    def answer(self, query: str) -> str:
        """Format retrieved chunks into a concise KB-focused answer."""
        results = self.search(query)
        if not results:
            return (
                "No indexed KB content matched that query. Run `entrag-ingest` first or try a "
                "more specific VMware/Broadcom error, product, or version."
            )

        lines = [f"Top KB matches for: {query.strip()}"]
        for index, result in enumerate(results, start=1):
            source_label = result.url or f"KB{result.article_number}"
            title = result.title or f"KB{result.article_number}"
            section_label = result.section_heading or result.section_type or "match"
            snippet = self._summarize_text(result.text)
            lines.append(
                f"\n{index}. {title} [{section_label}] (score {result.score:.2f})\n"
                f"{snippet}\nSource: {source_label}"
            )
        return "\n".join(lines)

    def _query_vector_store(
        self,
        cleaned_query: str,
        query_embedding: list[float],
        similarity_top_k: int,
    ) -> VectorStoreQueryResult:
        """Query LanceDB, preferring hybrid mode and falling back to vector mode."""
        hybrid_query = VectorStoreQuery(
            query_embedding=query_embedding,
            query_str=cleaned_query,
            similarity_top_k=similarity_top_k,
            mode=VectorStoreQueryMode.HYBRID,
            alpha=self.settings.retrieval_hybrid_alpha,
            sparse_top_k=similarity_top_k,
            hybrid_top_k=similarity_top_k,
        )
        try:
            return self._vector_store.query(hybrid_query)
        except TableNotFoundError:
            return VectorStoreQueryResult(nodes=[], similarities=[], ids=[])
        except (AttributeError, NotImplementedError, RuntimeError) as exc:
            logger.warning("Hybrid search unavailable, falling back to vector search: %s", exc)
            fallback_query = VectorStoreQuery(
                query_embedding=query_embedding,
                query_str=cleaned_query,
                similarity_top_k=similarity_top_k,
                mode=VectorStoreQueryMode.DEFAULT,
            )
            return self._vector_store.query(fallback_query, query_type="vector")

    def _to_retrieved_chunks(self, result: VectorStoreQueryResult) -> list[RetrievedChunk]:
        """Convert raw vector-store results into normalized chunks."""
        nodes = list(result.nodes or [])
        similarities = list(result.similarities or [])
        if len(similarities) != len(nodes):
            similarities = [0.0] * len(nodes)
        normalized_scores = _normalize_scores(similarities)
        chunks: list[RetrievedChunk] = []

        for node, score in zip(nodes, normalized_scores, strict=True):
            metadata = dict(getattr(node, "metadata", {}) or {})
            chunks.append(
                RetrievedChunk(
                    text=node.get_content(metadata_mode="none"),
                    score=score,
                    article_number=str(metadata.get("article_number", "")),
                    title=str(metadata.get("title", "")),
                    url=str(metadata.get("url", "")),
                    product=str(metadata.get("product", "")),
                    section_type=str(metadata.get("section_type", "")),
                    section_heading=str(metadata.get("section_heading", "")),
                    metadata=metadata,
                )
            )
        return chunks

    def _rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Bias retrieved chunks toward exact matches and actionable sections."""
        query_tokens = _tokenize(query)
        reranked: list[RetrievedChunk] = []

        for candidate in candidates:
            lexical_score = self._lexical_score(query, query_tokens, candidate)
            reranked.append(
                RetrievedChunk(
                    text=candidate.text,
                    score=(
                        (RERANKING_VECTOR_WEIGHT * candidate.score)
                        + (RERANKING_LEXICAL_WEIGHT * lexical_score)
                    ),
                    article_number=candidate.article_number,
                    title=candidate.title,
                    url=candidate.url,
                    product=candidate.product,
                    section_type=candidate.section_type,
                    section_heading=candidate.section_heading,
                    metadata=candidate.metadata,
                )
            )

        return sorted(reranked, key=lambda item: item.score, reverse=True)

    def _lexical_score(
        self,
        query: str,
        query_tokens: set[str],
        candidate: RetrievedChunk,
    ) -> float:
        """Score chunk text/title overlap and boost contextually relevant sections."""
        haystack = " ".join(
            part
            for part in [
                candidate.title,
                candidate.section_heading,
                candidate.section_type,
                candidate.product,
                candidate.text,
            ]
            if part
        )
        candidate_tokens = _tokenize(haystack)
        if not query_tokens or not candidate_tokens:
            overlap_score = 0.0
        else:
            overlap_score = len(query_tokens & candidate_tokens) / len(query_tokens)

        query_lower = query.lower()
        text_lower = haystack.lower()
        phrase_bonus = 0.15 if query_lower and query_lower in text_lower else 0.0
        return min(1.0, overlap_score + phrase_bonus + self._section_boost(query, candidate))

    def _section_boost(self, query: str, candidate: RetrievedChunk) -> float:
        """Boost sections that are likely to answer the intent of the query."""
        query_lower = query.lower()
        section = candidate.section_type.lower()
        if section == "resolution" and any(hint in query_lower for hint in RESOLUTION_HINTS):
            return 0.2
        if section == "workaround" and any(hint in query_lower for hint in RESOLUTION_HINTS):
            return 0.15
        if section == "cause" and any(hint in query_lower for hint in CAUSE_HINTS):
            return 0.2
        if section == "symptom" and any(hint in query_lower for hint in SYMPTOM_HINTS):
            return 0.1
        return 0.0

    @staticmethod
    def _summarize_text(text: str, limit: int = 280) -> str:
        """Collapse whitespace and keep answer snippets short."""
        collapsed_whitespace = " ".join(text.split())
        if len(collapsed_whitespace) <= limit or limit <= ELLIPSIS_LENGTH:
            return collapsed_whitespace
        truncated_length = limit - ELLIPSIS_LENGTH
        return f"{collapsed_whitespace[:truncated_length].rstrip()}..."

def create_retrieval_engine() -> RetrievalEngine:
    """Create a retrieval engine from the current settings."""
    return RetrievalEngine()


__all__ = ["RetrievedChunk", "RetrievalEngine", "create_retrieval_engine"]
