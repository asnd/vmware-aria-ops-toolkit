"""Tests for the ingestion module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.ingestion import _article_to_documents, ingest_directory
from src.scraper.parser import KBSection, ParsedKBArticle


class _FakeEmbedModel:
    def get_text_embedding(self, text):
        return [0.1, 0.2, 0.3]

    def get_query_embedding(self, query):
        return [0.1, 0.2, 0.3]


class _FakeVectorStore:
    def __init__(self):
        self.saved_documents = []

    def add(self, docs):
        self.saved_documents.extend(docs)


# --- _article_to_documents tests ---


def test_article_to_documents_with_sections():
    """Articles with sections should produce one Document per section."""
    article = ParsedKBArticle(
        article_number="12345",
        title="Test Article",
        url="https://kb.example.com/12345",
        product="vSphere",
        version="8.0",
        last_updated="2024-01-01",
        sections=[
            KBSection("Symptoms", "System fails to boot", "symptom"),
            KBSection("Resolution", "Apply patch", "resolution"),
        ],
    )

    docs = _article_to_documents(article)

    assert len(docs) == 2
    assert "## Symptoms" in docs[0].text
    assert "System fails to boot" in docs[0].text
    assert docs[0].metadata["section_type"] == "symptom"
    assert docs[0].metadata["article_number"] == "12345"

    assert "## Resolution" in docs[1].text
    assert docs[1].metadata["section_type"] == "resolution"


def test_article_to_documents_no_sections():
    """Articles without sections should produce a single Document from full_text."""
    article = ParsedKBArticle(
        article_number="67890",
        title="Simple Article",
        url="https://kb.example.com/67890",
        product="NSX",
        raw_text="This is the raw content of the article.",
        sections=[],
    )

    docs = _article_to_documents(article)

    assert len(docs) == 1
    assert "This is the raw content" in docs[0].text
    assert docs[0].metadata["article_number"] == "67890"
    assert "section_type" not in docs[0].metadata


def test_article_to_documents_metadata_propagation():
    """Base metadata should be propagated to all documents."""
    article = ParsedKBArticle(
        article_number="11111",
        title="Meta Test",
        url="https://kb.example.com/11111",
        product="vSAN",
        version="7.0",
        last_updated="2024-06-01",
        sections=[
            KBSection("Cause", "Bad driver", "cause"),
        ],
    )

    docs = _article_to_documents(article)

    for doc in docs:
        assert doc.metadata["article_number"] == "11111"
        assert doc.metadata["title"] == "Meta Test"
        assert doc.metadata["url"] == "https://kb.example.com/11111"
        assert doc.metadata["product"] == "vSAN"
        assert doc.metadata["version"] == "7.0"
        assert doc.metadata["last_updated"] == "2024-06-01"


# --- ingest_directory tests ---


def _create_test_html(tmp_path: Path, article_number: str, content: str) -> Path:
    """Helper to create a test HTML file."""
    html = f"""
    <html>
    <body>
        <h1>Article {article_number}</h1>
        <div class="article-content">
            <h2>Symptoms</h2>
            <p>{content}</p>
        </div>
    </body>
    </html>
    """
    html_file = tmp_path / f"{article_number}.html"
    html_file.write_text(html)
    return html_file


@patch("src.ingestion.VectorStoreIndex")
@patch("src.ingestion.LanceDBVectorStore")
@patch("src.ingestion.LiteLLMEmbedding")
def test_ingest_directory_success(
    mock_embed_cls, mock_vs_cls, mock_index_cls, tmp_path: Path
):
    """Successful ingestion should return chunk count."""
    _create_test_html(tmp_path, "12345", "Test symptom content")
    _create_test_html(tmp_path, "67890", "Another symptom here")

    mock_embed = MagicMock()
    mock_embed_cls.return_value = mock_embed

    mock_vs = MagicMock()
    mock_vs_cls.return_value = mock_vs

    mock_index_cls.from_documents.return_value = MagicMock()

    with patch("src.ingestion.get_settings") as mock_settings:
        mock_settings.return_value.lancedb_path = tmp_path / "lancedb"
        mock_settings.return_value.litellm_embedding_model = "test-model"
        mock_settings.return_value.litellm_base_url = "http://localhost:4000"
        mock_settings.return_value.litellm_api_key = "sk-test"
        mock_settings.return_value.resolved_embedding_model = MagicMock(return_value="test-model")
        mock_settings.return_value.resolved_litellm_base_url = MagicMock(
            return_value="http://localhost:4000"
        )

        count = ingest_directory(tmp_path)

        assert count > 0
        mock_index_cls.from_documents.assert_called_once()
        mock_settings.return_value.validate_litellm_api_key.assert_called_once()


@patch("src.ingestion.VectorStoreIndex")
@patch("src.ingestion.LanceDBVectorStore")
@patch("src.ingestion.LiteLLMEmbedding")
def test_ingest_directory_empty(mock_embed_cls, mock_vs_cls, mock_index_cls, tmp_path: Path):
    """Ingesting empty directory should return 0."""
    with patch("src.ingestion.get_settings") as mock_settings:
        mock_settings.return_value.lancedb_path = tmp_path / "lancedb"
        mock_settings.return_value.litellm_embedding_model = "test-model"
        mock_settings.return_value.litellm_base_url = "http://localhost:4000"
        mock_settings.return_value.litellm_api_key = "sk-test"

        count = ingest_directory(tmp_path)

        assert count == 0
        mock_index_cls.from_documents.assert_not_called()


@patch("src.ingestion.VectorStoreIndex")
@patch("src.ingestion.LanceDBVectorStore")
@patch("src.ingestion.LiteLLMEmbedding")
def test_ingest_directory_reset(
    mock_embed_cls, mock_vs_cls, mock_index_cls, tmp_path: Path
):
    """Reset flag should remove existing lancedb directory."""
    # Create fake existing lancedb directory
    existing_db = tmp_path / "lancedb" / "some_table"
    existing_db.mkdir(parents=True)

    _create_test_html(tmp_path, "12345", "Test content")

    mock_embed = MagicMock()
    mock_embed_cls.return_value = mock_embed

    mock_vs = MagicMock()
    mock_vs_cls.return_value = mock_vs

    mock_index_cls.from_documents.return_value = MagicMock()

    lancedb_path = tmp_path / "lancedb"

    with patch("src.ingestion.get_settings") as mock_settings:
        mock_settings.return_value.lancedb_path = lancedb_path
        mock_settings.return_value.litellm_embedding_model = "test-model"
        mock_settings.return_value.litellm_base_url = "http://localhost:4000"
        mock_settings.return_value.litellm_api_key = "sk-test"
        mock_settings.return_value.resolved_embedding_model = MagicMock(return_value="test-model")
        mock_settings.return_value.resolved_litellm_base_url = MagicMock(
            return_value="http://localhost:4000"
        )

        ingest_directory(tmp_path, reset=True)

        # Old directory should be removed and parent recreated
        assert lancedb_path.parent.exists()


@patch("src.ingestion.VectorStoreIndex")
@patch("src.ingestion.LanceDBVectorStore")
@patch("src.ingestion.LiteLLMEmbedding")
def test_ingest_directory_creates_lancedb_parent(
    mock_embed_cls, mock_vs_cls, mock_index_cls, tmp_path: Path
):
    """Ingestion should create parent directories for lancedb path."""
    _create_test_html(tmp_path, "12345", "Test content")

    mock_embed = MagicMock()
    mock_embed_cls.return_value = mock_embed

    mock_vs = MagicMock()
    mock_vs_cls.return_value = mock_vs

    mock_index_cls.from_documents.return_value = MagicMock()

    lancedb_path = tmp_path / "nested" / "dir" / "lancedb"

    with patch("src.ingestion.get_settings") as mock_settings:
        mock_settings.return_value.lancedb_path = lancedb_path
        mock_settings.return_value.litellm_embedding_model = "test-model"
        mock_settings.return_value.litellm_base_url = "http://localhost:4000"
        mock_settings.return_value.litellm_api_key = "sk-test"
        mock_settings.return_value.resolved_embedding_model = MagicMock(return_value="test-model")
        mock_settings.return_value.resolved_litellm_base_url = MagicMock(
            return_value="http://localhost:4000"
        )

        ingest_directory(tmp_path)

        assert lancedb_path.parent.exists()
