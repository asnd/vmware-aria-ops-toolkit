"""Tests for CLI scripts."""

from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from scripts.ingest import main as ingest_main
from scripts.scrape import cli as scrape_cli


@pytest.fixture
def runner():
    """Create a Click CLI runner."""
    return CliRunner()


@pytest.fixture
def mock_scraper():
    """Mock the BroadcomKBScraper to avoid network calls."""
    with patch("scripts.scrape.BroadcomKBScraper") as mock_cls:
        mock_instance = AsyncMock()
        mock_instance.scrape = AsyncMock(return_value=[])
        mock_instance.state.failed = set()
        mock_instance.state.downloaded = set()
        mock_cls.return_value.__aenter__.return_value = mock_instance
        mock_cls.return_value.__aexit__.return_value = None
        yield mock_instance


# ── scrape search ──


def test_scrape_search_help(runner):
    """Test that the search subcommand help works."""
    result = runner.invoke(scrape_cli, ["search", "--help"])
    assert result.exit_code == 0
    assert "Search and download KB articles" in result.output
    assert "--auth" in result.output
    assert "--query" in result.output


def test_scrape_search_defaults(mock_scraper):
    """Test search with default parameters (public mode)."""
    runner = CliRunner()
    result = runner.invoke(scrape_cli, ["search"])
    assert result.exit_code == 0
    assert "public (default)" in result.output
    mock_scraper.scrape.assert_called_once()


def test_scrape_search_with_auth(mock_scraper):
    """Test search with --auth flag passes use_auth=True."""
    runner = CliRunner()
    result = runner.invoke(scrape_cli, ["search", "--auth"])
    assert result.exit_code == 0
    assert "authenticated" in result.output
    mock_scraper.scrape.assert_called_once()


def test_scrape_search_with_product(mock_scraper):
    """Test search with product filter."""
    runner = CliRunner()
    result = runner.invoke(
        scrape_cli, ["search", "--product", "vSphere", "--max", "10"]
    )
    assert result.exit_code == 0
    assert "vSphere" in result.output
    assert "10" in result.output
    mock_scraper.scrape.assert_called_once()


def test_scrape_search_verbose():
    """Test search with verbose flag doesn't crash."""
    runner = CliRunner()
    with patch("scripts.scrape.BroadcomKBScraper") as mock_cls:
        mock_instance = AsyncMock()
        mock_instance.scrape = AsyncMock(return_value=[])
        mock_instance.state.failed = set()
        mock_instance.state.downloaded = set()
        mock_cls.return_value.__aenter__.return_value = mock_instance
        mock_cls.return_value.__aexit__.return_value = None
        result = runner.invoke(scrape_cli, ["search", "--verbose"])
    assert result.exit_code == 0


# ── scrape fetch ──


def test_scrape_fetch_help(runner):
    """Test that the fetch subcommand help works."""
    result = runner.invoke(scrape_cli, ["fetch", "--help"])
    assert result.exit_code == 0
    assert "Download specific KB articles" in result.output
    assert "--numbers" in result.output


def test_scrape_fetch_required_numbers(runner):
    """Test that fetch without --numbers shows error."""
    result = runner.invoke(scrape_cli, ["fetch"])
    assert result.exit_code != 0
    assert "--numbers" in result.output


def test_scrape_fetch_with_auth(mock_scraper):
    """Test fetch with --auth flag."""
    runner = CliRunner()
    result = runner.invoke(scrape_cli, ["fetch", "--numbers", "12345,67890", "--auth"])
    assert result.exit_code == 0
    assert "authenticated" in result.output
    mock_scraper.download_article.assert_called()


def test_scrape_fetch_public_default(mock_scraper):
    """Test fetch defaults to public mode."""
    runner = CliRunner()
    result = runner.invoke(scrape_cli, ["fetch", "--numbers", "12345"])
    assert result.exit_code == 0
    assert "public" in result.output
    mock_scraper.download_article.assert_called()


# ── scrape parse ──


def test_scrape_parse_missing_dir(runner, tmp_path):
    """Test that parse with nonexistent directory shows error."""
    nonexistent = tmp_path / "nonexistent"
    result = runner.invoke(scrape_cli, ["parse", "--input", str(nonexistent)])
    assert result.exit_code != 0
    assert "does not exist" in result.output


def test_scrape_parse_empty_dir(runner, tmp_path):
    """Test that parse with empty directory shows no articles."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    result = runner.invoke(scrape_cli, ["parse", "--input", str(empty_dir)])
    assert result.exit_code == 0
    assert "No articles found" in result.output


def test_scrape_parse_with_files(runner, tmp_path):
    """Test that parse finds HTML files."""
    html_dir = tmp_path / "articles"
    html_dir.mkdir()
    (html_dir / "11111.html").write_text(
        "<html><head><title>Test KB</title></head>"
        "<body><h1>Test KB</h1><div class='article-content'>"
        "<h2>Symptoms</h2><p>Test symptom text for content area.</p>"
        "</div></body></html>"
    )
    result = runner.invoke(scrape_cli, ["parse", "--input", str(html_dir)])
    assert result.exit_code == 0
    assert "Parsed KB Articles" in result.output
    assert "11111" in result.output


# ── scrape status ──


def test_scrape_status(runner):
    """Test that status command works."""
    result = runner.invoke(scrape_cli, ["status"])
    assert result.exit_code == 0
    assert "Scraper Status" in result.output
    assert "Downloaded" in result.output


# ── ingest ──


def test_ingest_help(runner):
    """Test that the ingest help works."""
    result = runner.invoke(ingest_main, ["--help"])
    assert result.exit_code == 0
    assert "--source" in result.output
    assert "--reset" in result.output


def test_ingest_default(runner):
    """Test that ingest runs with defaults without hitting real LiteLLM."""
    with patch("src.ingestion.ingest_directory", return_value=0):
        result = runner.invoke(ingest_main, [])
    assert result.exit_code == 0
    assert "Ingestion" in result.output


def test_ingest_with_args(runner, tmp_path):
    """Test that ingest accepts arguments."""
    source_dir = tmp_path / "articles"
    source_dir.mkdir()
    result = runner.invoke(ingest_main, ["--source", str(source_dir), "--reset"])
    assert result.exit_code == 0
    assert "Reset" in result.output or "Ingestion" in result.output


def test_ingest_with_local_flag(runner, tmp_path):
    """Test that ingest with --local flag shows local embedding hint."""
    source_dir = tmp_path / "articles"
    source_dir.mkdir()
    result = runner.invoke(ingest_main, ["--source", str(source_dir), "--local"])
    assert result.exit_code == 0
    assert "local" in result.output.lower() or "Ingestion" in result.output


def test_ingest_error_handling(runner, tmp_path):
    """Test that ingest handles ingestion errors gracefully."""
    source_dir = tmp_path / "articles"
    source_dir.mkdir()
    with patch("src.ingestion.ingest_directory") as mock_ingest:
        mock_ingest.side_effect = RuntimeError("Embedding failed")
        result = runner.invoke(ingest_main, ["--source", str(source_dir), "--verbose"])
        assert result.exit_code == 1
        assert "Embedding failed" in result.output
