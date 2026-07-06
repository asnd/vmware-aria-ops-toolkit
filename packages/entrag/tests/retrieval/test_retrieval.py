"""Tests for hybrid retrieval and reranking."""

from dataclasses import dataclass

from llama_index.core.schema import TextNode
from llama_index.core.vector_stores.types import VectorStoreQueryMode, VectorStoreQueryResult

from src.config import Settings
from src.retrieval import RetrievalEngine, _normalize_scores, _tokenize


@dataclass
class _FakeEmbedModel:
    def get_query_embedding(self, query: str) -> list[float]:
        assert query
        return [0.1, 0.2, 0.3]


class _FakeVectorStore:
    def __init__(self, result: VectorStoreQueryResult):
        self.result = result
        self.seen_queries = []

    def query(self, query):
        self.seen_queries.append(query)
        return self.result


def test_search_uses_hybrid_query_and_reranks_results():
    """Resolution-heavy matches should outrank weaker symptom-only matches."""
    vector_store = _FakeVectorStore(
        VectorStoreQueryResult(
            nodes=[
                TextNode(
                    text="The resolution is to install the corrected ESXi boot patch.",
                    metadata={
                        "article_number": "10001",
                        "title": "Fix ESXi boot failure",
                        "url": "https://kb.example.com/10001",
                        "section_type": "resolution",
                        "section_heading": "Resolution",
                    },
                ),
                TextNode(
                    text="Symptoms include boot failure after the firmware upgrade.",
                    metadata={
                        "article_number": "10002",
                        "title": "Boot failure symptoms",
                        "url": "https://kb.example.com/10002",
                        "section_type": "symptom",
                        "section_heading": "Symptoms",
                    },
                ),
            ],
            similarities=[0.45, 0.9],
        )
    )
    engine = RetrievalEngine(
        settings=Settings(
            litellm_api_key="sk-live",
            reranker_top_n=2,
            retrieval_similarity_top_k=2,
            retrieval_hybrid_alpha=0.3,
        ),
        vector_store=vector_store,
        embed_model=_FakeEmbedModel(),
    )

    results = engine.search("how to fix ESXi boot failure", top_k=2)

    assert len(results) == 2
    assert results[0].article_number == "10001"
    assert vector_store.seen_queries[0].mode == VectorStoreQueryMode.HYBRID
    assert vector_store.seen_queries[0].alpha == 0.3
    assert vector_store.seen_queries[0].query_str == "how to fix ESXi boot failure"


def test_search_returns_empty_for_blank_query():
    """Blank user input should not call the vector store."""
    vector_store = _FakeVectorStore(VectorStoreQueryResult(nodes=[], similarities=[]))
    engine = RetrievalEngine(
        settings=Settings(litellm_api_key="sk-live"),
        vector_store=vector_store,
        embed_model=_FakeEmbedModel(),
    )

    assert engine.search("   ") == []
    assert vector_store.seen_queries == []


def test_answer_includes_sources_and_scores():
    """Formatted answers should include citations for the retrieved chunks."""
    vector_store = _FakeVectorStore(
        VectorStoreQueryResult(
            nodes=[
                TextNode(
                    text="Apply patch ESXi70U3c and reboot the host.",
                    metadata={
                        "article_number": "10003",
                        "title": "Apply the ESXi patch",
                        "url": "https://kb.example.com/10003",
                        "section_type": "resolution",
                        "section_heading": "Resolution",
                    },
                )
            ],
            similarities=[0.8],
        )
    )
    engine = RetrievalEngine(
        settings=Settings(litellm_api_key="sk-live", reranker_top_n=1),
        vector_store=vector_store,
        embed_model=_FakeEmbedModel(),
    )

    answer = engine.answer("apply ESXi patch")

    assert "Top KB matches for: apply ESXi patch" in answer
    assert "Source: https://kb.example.com/10003" in answer
    assert "score" in answer


# --- Unit tests for helper functions ---


def test_tokenize_empty_and_special_chars():
    """Tokenization should ignore short tokens and special characters."""
    assert _tokenize("") == set()
    assert _tokenize("a b c") == set()  # single chars ignored
    assert _tokenize("hello world") == {"hello", "world"}
    assert _tokenize("hello-world_123") == {"hello", "world", "123"}


def test_normalize_scores_empty():
    """Empty list should return empty list."""
    assert _normalize_scores([]) == []


def test_normalize_scores_single():
    """Single score should return [0.5]."""
    assert _normalize_scores([42.0]) == [0.5]


def test_normalize_scores_identical():
    """All identical scores should return 0.5 for each."""
    result = _normalize_scores([3.0, 3.0, 3.0])
    assert result == [0.5, 0.5, 0.5]


def test_normalize_scores_varied():
    """Varied scores should be normalized to 0-1 range."""
    result = _normalize_scores([0.0, 0.5, 1.0])
    assert result == [0.0, 0.5, 1.0]


def test_section_boost_resolution():
    """Resolution sections should be boosted for fix/how-to queries."""
    vector_store = _FakeVectorStore(VectorStoreQueryResult(nodes=[], similarities=[]))
    engine = RetrievalEngine(
        settings=Settings(litellm_api_key="sk-live"),
        vector_store=vector_store,
        embed_model=_FakeEmbedModel(),
    )
    from src.retrieval import RetrievedChunk

    chunk = RetrievedChunk(
        text="fix it", score=0.5, article_number="1", title="", url="",
        product="", section_type="resolution", section_heading="Resolution", metadata={},
    )
    assert engine._section_boost("how to fix", chunk) == 0.2
    assert engine._section_boost("error occurred", chunk) == 0.0


def test_section_boost_cause():
    """Cause sections should be boosted for cause/why queries."""
    vector_store = _FakeVectorStore(VectorStoreQueryResult(nodes=[], similarities=[]))
    engine = RetrievalEngine(
        settings=Settings(litellm_api_key="sk-live"),
        vector_store=vector_store,
        embed_model=_FakeEmbedModel(),
    )
    from src.retrieval import RetrievedChunk

    chunk = RetrievedChunk(
        text="cause info", score=0.5, article_number="1", title="", url="",
        product="", section_type="cause", section_heading="Cause", metadata={},
    )
    assert engine._section_boost("why does this happen", chunk) == 0.2
    assert engine._section_boost("root cause analysis", chunk) == 0.2


def test_answer_no_results():
    """Answer with no matching results should suggest ingestion."""
    vector_store = _FakeVectorStore(VectorStoreQueryResult(nodes=[], similarities=[]))
    engine = RetrievalEngine(
        settings=Settings(litellm_api_key="sk-live"),
        vector_store=vector_store,
        embed_model=_FakeEmbedModel(),
    )

    answer = engine.answer("obscure query")
    assert "No indexed KB content" in answer
    assert "entrag-ingest" in answer


def test_summarize_text_truncation():
    """Long text should be truncated with ellipsis."""
    vector_store = _FakeVectorStore(VectorStoreQueryResult(nodes=[], similarities=[]))
    engine = RetrievalEngine(
        settings=Settings(litellm_api_key="sk-live"),
        vector_store=vector_store,
        embed_model=_FakeEmbedModel(),
    )

    long_text = "x" * 500
    result = engine._summarize_text(long_text, limit=20)
    assert len(result) == 20
    assert result.endswith("...")


def test_summarize_text_short():
    """Short text should be returned as-is."""
    vector_store = _FakeVectorStore(VectorStoreQueryResult(nodes=[], similarities=[]))
    engine = RetrievalEngine(
        settings=Settings(litellm_api_key="sk-live"),
        vector_store=vector_store,
        embed_model=_FakeEmbedModel(),
    )

    result = engine._summarize_text("short", limit=280)
    assert result == "short"


def test_to_retrieved_chunks_mismatched_lengths():
    """Mismatched node/similarity lengths should fill scores with zeros."""
    vector_store = _FakeVectorStore(
        VectorStoreQueryResult(
            nodes=[TextNode(text="hello", metadata={})],
            similarities=[],  # missing similarity
        )
    )
    engine = RetrievalEngine(
        settings=Settings(litellm_api_key="sk-live"),
        vector_store=vector_store,
        embed_model=_FakeEmbedModel(),
    )

    results = engine.search("hello")
    assert len(results) == 1
    # Score is reranked: vector_weight * normalized + lexical_weight * overlap
    assert results[0].score > 0
