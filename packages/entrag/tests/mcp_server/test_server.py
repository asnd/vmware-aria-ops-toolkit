"""Tests for the MCP server tool definitions and handlers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.mcp_server.server import (
    _handle_ingestion_status,
    _handle_rag_query,
    _handle_scrape_status,
    _handle_trigger_ingest,
    _handle_trigger_scrape,
    _tool_definitions,
    create_server,
)


class TestToolDefinitions:
    """Test that MCP tool definitions are well-formed."""

    def test_returns_five_tools(self):
        tools = _tool_definitions()
        assert len(tools) == 5

    def test_tool_names(self):
        tools = _tool_definitions()
        names = {t.name for t in tools}
        assert names == {
            "rag_query",
            "scrape_status",
            "trigger_scrape",
            "trigger_ingest",
            "ingestion_status",
        }

    def test_rag_query_requires_query_param(self):
        tools = _tool_definitions()
        rag_tool = next(t for t in tools if t.name == "rag_query")
        assert "query" in rag_tool.inputSchema["required"]

    def test_all_tools_have_descriptions(self):
        tools = _tool_definitions()
        for tool in tools:
            assert tool.description, f"Tool {tool.name} has no description"
            assert len(tool.description) > 20


class TestCreateServer:
    """Test MCP server creation."""

    def test_creates_server_instance(self):
        server = create_server()
        assert server is not None
        assert server.name == "entrag-mcp"


class TestRagQueryHandler:
    """Test the rag_query tool handler."""

    @pytest.mark.asyncio
    async def test_empty_query_returns_error(self):
        result = await _handle_rag_query({"query": ""})
        assert len(result) == 1
        assert "required" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_whitespace_only_query_returns_error(self):
        result = await _handle_rag_query({"query": "   "})
        assert len(result) == 1
        assert "required" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_missing_index_returns_not_available(self):
        """When LanceDB index doesn't exist, should return helpful error."""
        with patch("src.retrieval.RetrievalEngine") as mock_cls:
            mock_cls.side_effect = FileNotFoundError("Index not found")
            result = await _handle_rag_query({"query": "test query"})
        assert "not available" in result[0].text.lower() or "not found" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_successful_query_returns_json(self):
        """Mock a successful retrieval and verify output format."""
        mock_chunk = MagicMock()
        mock_chunk.score = 0.95
        mock_chunk.article_number = "12345"
        mock_chunk.title = "Test KB Article"
        mock_chunk.url = "https://example.com/kb/12345"
        mock_chunk.product = "vSphere"
        mock_chunk.section_type = "resolution"
        mock_chunk.section_heading = "Resolution"
        mock_chunk.text = "Apply the latest patch to resolve the issue."

        with patch("src.retrieval.RetrievalEngine") as mock_cls:
            mock_engine = MagicMock()
            mock_engine.search.return_value = [mock_chunk]
            mock_cls.return_value = mock_engine

            result = await _handle_rag_query({"query": "vSphere patch error"})

        assert len(result) == 1
        parsed = json.loads(result[0].text)
        assert len(parsed) == 1
        assert parsed[0]["rank"] == 1
        assert parsed[0]["article_number"] == "12345"
        assert parsed[0]["section_type"] == "resolution"

    @pytest.mark.asyncio
    async def test_no_results_returns_message(self):
        with patch("src.retrieval.RetrievalEngine") as mock_cls:
            mock_engine = MagicMock()
            mock_engine.search.return_value = []
            mock_cls.return_value = mock_engine

            result = await _handle_rag_query({"query": "obscure query"})

        assert "no kb content" in result[0].text.lower()


class TestScrapeStatusHandler:
    """Test the scrape_status tool handler."""

    @pytest.mark.asyncio
    async def test_returns_json_status(self, tmp_path: Path):
        """Test scrape status with a real temp directory."""
        # Create a fake output dir with some HTML files
        output_dir = tmp_path / "raw"
        output_dir.mkdir()
        (output_dir / "article1.html").write_text("<html></html>")
        (output_dir / "article2.html").write_text("<html></html>")

        # Mock get_settings to use our temp dir
        mock_settings = MagicMock()
        mock_settings.scraper_output_dir = output_dir

        mock_state = MagicMock()
        mock_state.total_found = 10
        mock_state.downloaded = {"1", "2"}
        mock_state.failed = {"3"}

        with (
            patch("src.mcp_server.server.get_settings", return_value=mock_settings),
            patch("src.scraper.broadcom_kb.ScraperState.load", return_value=mock_state),
        ):
            result = await _handle_scrape_status({})

        parsed = json.loads(result[0].text)
        assert parsed["total_articles_found"] == 10
        assert parsed["downloaded"] == 2
        assert parsed["failed"] == 1
        assert parsed["html_files_on_disk"] == 2


class TestTriggerScrapeHandler:
    """Test the trigger_scrape tool handler."""

    @pytest.mark.asyncio
    async def test_successful_scrape(self):
        mock_settings = MagicMock()
        mock_settings.scraper_output_dir = Path("/tmp/test-raw")
        mock_settings.scraper_max_articles = 50
        mock_settings.scraper_use_auth = False

        mock_scraper = MagicMock()

        async def mock_aenter(self_inner=None):
            return mock_scraper

        async def mock_aexit(self_inner=None, *args):
            return None

        async def mock_scrape(**kwargs):
            return [Path("/tmp/a.html"), Path("/tmp/b.html")]

        mock_scraper.__aenter__ = mock_aenter
        mock_scraper.__aexit__ = mock_aexit
        mock_scraper.scrape = mock_scrape
        mock_scraper.state = MagicMock(failed=set())

        with (
            patch("src.mcp_server.server.get_settings", return_value=mock_settings),
            patch("src.scraper.broadcom_kb.BroadcomKBScraper", return_value=mock_scraper),
        ):
            result = await _handle_trigger_scrape({"query": "nsx", "max_articles": 10})

        parsed = json.loads(result[0].text)
        assert parsed["status"] == "completed"
        assert parsed["articles_downloaded"] == 2
        assert parsed["query"] == "nsx"

    @pytest.mark.asyncio
    async def test_scrape_error_handling(self):
        mock_settings = MagicMock()
        mock_settings.scraper_output_dir = Path("/tmp/test-raw")
        mock_settings.scraper_max_articles = 50
        mock_settings.scraper_use_auth = False

        with (
            patch("src.mcp_server.server.get_settings", return_value=mock_settings),
            patch(
                "src.scraper.broadcom_kb.BroadcomKBScraper",
                side_effect=RuntimeError("Connection failed"),
            ),
        ):
            result = await _handle_trigger_scrape({})

        parsed = json.loads(result[0].text)
        assert parsed["status"] == "error"
        assert "Connection failed" in parsed["detail"]


class TestTriggerIngestHandler:
    """Test the trigger_ingest tool handler."""

    @pytest.mark.asyncio
    async def test_missing_source_dir(self, tmp_path: Path):
        nonexistent = tmp_path / "nonexistent"
        mock_settings = MagicMock()
        mock_settings.scraper_output_dir = nonexistent
        mock_settings.lancedb_path = tmp_path / "lancedb"

        with patch("src.mcp_server.server.get_settings", return_value=mock_settings):
            result = await _handle_trigger_ingest({})

        parsed = json.loads(result[0].text)
        assert parsed["status"] == "error"
        assert "does not exist" in parsed["detail"]

    @pytest.mark.asyncio
    async def test_successful_ingest(self, tmp_path: Path):
        source_dir = tmp_path / "raw"
        source_dir.mkdir()
        (source_dir / "test.html").write_text("<html></html>")

        mock_settings = MagicMock()
        mock_settings.scraper_output_dir = source_dir
        mock_settings.lancedb_path = tmp_path / "lancedb"

        with (
            patch("src.mcp_server.server.get_settings", return_value=mock_settings),
            patch("src.ingestion.ingest_directory", return_value=42),
        ):
            result = await _handle_trigger_ingest({"reset": True})

        parsed = json.loads(result[0].text)
        assert parsed["status"] == "completed"
        assert parsed["chunks_ingested"] == 42
        assert parsed["reset"] is True


class TestIngestionStatusHandler:
    """Test the ingestion_status tool handler."""

    @pytest.mark.asyncio
    async def test_index_not_exists(self, tmp_path: Path):
        mock_settings = MagicMock()
        mock_settings.lancedb_path = tmp_path / "nonexistent"

        with patch("src.mcp_server.server.get_settings", return_value=mock_settings):
            result = await _handle_ingestion_status({})

        parsed = json.loads(result[0].text)
        assert parsed["index_exists"] is False
        assert "does not exist" in parsed["detail"]

    @pytest.mark.asyncio
    async def test_index_exists(self, tmp_path: Path):
        # Create a fake LanceDB directory
        lancedb_dir = tmp_path / "lancedb"
        lancedb_dir.mkdir()
        (lancedb_dir / "data.lance").write_bytes(b"fake" * 100)

        mock_settings = MagicMock()
        mock_settings.lancedb_path = lancedb_dir

        mock_db = MagicMock()
        mock_db.table_names.return_value = ["vectors"]
        mock_table = MagicMock()
        mock_table.count_rows.return_value = 500
        mock_db.open_table.return_value = mock_table

        with (
            patch("src.mcp_server.server.get_settings", return_value=mock_settings),
            patch("lancedb.connect", return_value=mock_db),
        ):
            result = await _handle_ingestion_status({})

        parsed = json.loads(result[0].text)
        assert parsed["index_exists"] is True
        assert parsed["tables"] == ["vectors"]
        assert parsed["row_count"] == 500
