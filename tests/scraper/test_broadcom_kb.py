"""Tests for the Broadcom KB scraper."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.scraper.broadcom_kb import (
    BroadcomKBScraper,
    KBArticleMeta,
    ScraperState,
)


@pytest.fixture
def temp_dir(tmp_path: Path):
    """Provide a temporary directory for tests."""
    return tmp_path


def _make_mock_client():
    """Create a properly configured AsyncMock for httpx.AsyncClient."""
    mock_client = AsyncMock()
    mock_client.aclose = AsyncMock()
    return mock_client


@pytest.fixture
def scraper(temp_dir: Path):
    """Create a scraper instance for testing."""
    return BroadcomKBScraper(
        output_dir=temp_dir,
        max_articles=10,
        use_auth=False,
    )


# --- State Tests ---


def test_scraper_state_persistence(temp_dir: Path):
    """Test that scraper state is saved and loaded correctly."""
    state_file = temp_dir / ".scraper_state.json"

    # Create initial state
    state = ScraperState()
    state.downloaded = {"12345", "67890"}
    state.failed = {"54321"}
    state.total_found = 1000
    state.save(state_file)

    # Load state
    loaded_state = ScraperState.load(state_file)
    assert loaded_state.downloaded == {"12345", "67890"}
    assert loaded_state.failed == {"54321"}
    assert loaded_state.total_found == 1000


def test_scraper_state_empty_file(temp_dir: Path):
    """Test loading state from non-existent file returns empty state."""
    state_file = temp_dir / ".scraper_state.json"
    assert not state_file.exists()

    state = ScraperState.load(state_file)
    assert state.downloaded == set()
    assert state.failed == set()
    assert state.total_found == 0


# --- URL Parsing Tests ---


def test_extract_article_number():
    """Test article number extraction from URLs."""
    test_cases = [
        ("https://kb.vmware.com/s/article/123456", "123456"),
        ("https://knowledge.broadcom.com/external/article?articleNumber=789012", "789012"),
        ("/external/article/345678", "345678"),
        ("articleNumber=901234&src=search", "901234"),
        ("no article number here", ""),
        ("", ""),
    ]

    for url, expected in test_cases:
        assert BroadcomKBScraper._extract_article_number(url) == expected


# --- Initialization Tests ---


def test_scraper_init_without_auth(temp_dir: Path):
    """Test scraper initialization in public mode (default)."""
    scraper = BroadcomKBScraper(
        output_dir=temp_dir,
        use_auth=False,
    )

    assert scraper.use_auth is False
    assert scraper._client is None
    assert scraper._authenticated is False


def test_scraper_init_with_auth(temp_dir: Path):
    """Test scraper initialization with auth enabled."""
    scraper = BroadcomKBScraper(
        output_dir=temp_dir,
        username="test@example.com",
        password="secret",
        use_auth=True,
    )

    assert scraper.use_auth is True
    assert scraper.username == "test@example.com"
    assert scraper.password == "secret"


# --- Authentication Tests ---


@pytest.mark.asyncio
async def test_authenticate_no_credentials(temp_dir: Path):
    """Test authentication when no credentials are provided."""
    scraper = BroadcomKBScraper(
        output_dir=temp_dir,
        use_auth=True,  # Auth enabled but no credentials
    )

    # Manually set client (bypass __aenter__)
    scraper._client = _make_mock_client()

    result = await scraper.authenticate()
    assert result is False  # Should fail gracefully — no creds
    assert scraper._authenticated is False


@pytest.mark.asyncio
async def test_authenticate_success(temp_dir: Path):
    """Test successful authentication."""
    scraper = BroadcomKBScraper(
        output_dir=temp_dir,
        username="test@example.com",
        password="secret",
        use_auth=True,
    )

    mock_client = _make_mock_client()

    # Mock login page GET
    login_page_resp = AsyncMock()
    login_page_resp.status_code = 200
    login_page_resp.raise_for_status = MagicMock()

    # Mock login POST
    login_post_resp = AsyncMock()
    login_post_resp.status_code = 200

    mock_client.get = AsyncMock(return_value=login_page_resp)
    mock_client.post = AsyncMock(return_value=login_post_resp)

    scraper._client = mock_client

    result = await scraper.authenticate()
    assert result is True
    assert scraper._authenticated is True


@pytest.mark.asyncio
async def test_authenticate_failure(temp_dir: Path):
    """Test authentication failure."""
    scraper = BroadcomKBScraper(
        output_dir=temp_dir,
        username="test@example.com",
        password="wrong",
        use_auth=True,
    )

    mock_client = _make_mock_client()

    # Mock login page GET
    login_page_resp = AsyncMock()
    login_page_resp.status_code = 200
    login_page_resp.raise_for_status = MagicMock()

    # Mock failed login POST (401)
    login_post_resp = AsyncMock()
    login_post_resp.status_code = 401

    mock_client.get = AsyncMock(return_value=login_page_resp)
    mock_client.post = AsyncMock(return_value=login_post_resp)

    scraper._client = mock_client

    result = await scraper.authenticate()
    assert result is False
    assert scraper._authenticated is False


# --- Fetch/Retry Tests ---


@pytest.mark.asyncio
async def test_fetch_page_success(temp_dir: Path):
    """Test successful page fetch."""
    scraper = BroadcomKBScraper(output_dir=temp_dir, use_auth=False)

    mock_client = _make_mock_client()
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    scraper._client = mock_client

    result = await scraper._fetch_page("http://example.com")
    assert result == mock_resp
    mock_client.get.assert_called_once_with("http://example.com")


# --- Search Tests ---


@pytest.mark.asyncio
async def test_search_articles_json_response(temp_dir: Path):
    """Test searching articles when API returns JSON."""
    scraper = BroadcomKBScraper(output_dir=temp_dir, max_articles=10, use_auth=False)
    scraper.delay_seconds = 0.0  # No delay for tests

    mock_client = _make_mock_client()

    # First page: returns 2 results
    search_resp_page1 = AsyncMock()
    search_resp_page1.status_code = 200
    search_resp_page1.headers = {"content-type": "application/json"}
    search_resp_page1.raise_for_status = MagicMock()
    search_resp_page1.json = MagicMock(return_value={
        "results": [
            {
                "articleNumber": "123456",
                "title": "Test Article 1",
                "url": "https://kb.example.com/article/123456",
                "product": "vSphere",
                "lastUpdated": "2024-01-01",
                "score": 0.95,
            },
            {
                "articleNumber": "789012",
                "title": "Test Article 2",
                "url": "https://kb.example.com/article/789012",
                "product": "NSX",
                "lastUpdated": "2024-01-02",
                "score": 0.87,
            }
        ],
        "total": 2
    })

    # Second page: empty (signals end of results)
    search_resp_page2 = AsyncMock()
    search_resp_page2.status_code = 200
    search_resp_page2.headers = {"content-type": "application/json"}
    search_resp_page2.raise_for_status = MagicMock()
    search_resp_page2.json = MagicMock(return_value={
        "results": [],
        "total": 2
    })

    mock_client.get = AsyncMock(side_effect=[search_resp_page1, search_resp_page2])
    scraper._client = mock_client

    articles = []
    async for meta in scraper.search_articles(
        query="test", product_filter="vSphere", max_results=5
    ):
        articles.append(meta)

    assert len(articles) == 2
    assert articles[0].article_number == "123456"
    assert articles[0].title == "Test Article 1"
    assert articles[0].product == "vSphere"
    assert articles[1].article_number == "789012"
    assert articles[1].title == "Test Article 2"
    assert articles[1].product == "NSX"


@pytest.mark.asyncio
async def test_search_articles_html_response(temp_dir: Path):
    """Test searching articles when API returns HTML (fallback parsing)."""
    scraper = BroadcomKBScraper(output_dir=temp_dir, max_articles=10, use_auth=False)
    scraper.delay_seconds = 0.0

    mock_client = _make_mock_client()

    # First page: HTML with article links
    search_resp_page1 = AsyncMock()
    search_resp_page1.status_code = 200
    search_resp_page1.headers = {"content-type": "text/html"}
    search_resp_page1.raise_for_status = MagicMock()
    search_resp_page1.text = """
    <html>
    <body>
        <div class="search-results">
            <a href="/external/article?articleNumber=111111">VMware ESXi Issue</a>
            <a href="/external/article?articleNumber=222222">vCenter Problem</a>
            <a href="/other/link">Not an article</a>
        </div>
    </body>
    </html>
    """

    # Second page: no article links (signals end)
    search_resp_page2 = AsyncMock()
    search_resp_page2.status_code = 200
    search_resp_page2.headers = {"content-type": "text/html"}
    search_resp_page2.raise_for_status = MagicMock()
    search_resp_page2.text = "<html><body><div>No results</div></body></html>"

    mock_client.get = AsyncMock(side_effect=[search_resp_page1, search_resp_page2])
    scraper._client = mock_client

    articles = []
    async for meta in scraper.search_articles(query="test", max_results=5):
        articles.append(meta)

    assert len(articles) == 2  # Only article links with valid numbers
    assert articles[0].article_number == "111111"
    assert articles[0].title == "VMware ESXi Issue"
    assert articles[1].article_number == "222222"
    assert articles[1].title == "vCenter Problem"


# --- Download Tests ---


@pytest.mark.asyncio
async def test_download_article_success(temp_dir: Path):
    """Test successful article download."""
    scraper = BroadcomKBScraper(output_dir=temp_dir, use_auth=False)

    mock_client = _make_mock_client()

    # Mock article response
    article_resp = AsyncMock()
    article_resp.status_code = 200
    article_resp.text = "<html><body><h1>Test Article</h1><p>Content</p></body></html>"
    article_resp.url = "https://kb.example.com/article/12345"
    article_resp.raise_for_status = MagicMock()
    mock_client.get = AsyncMock(return_value=article_resp)

    scraper._client = mock_client

    meta = KBArticleMeta(
        article_number="12345",
        title="Test Article",
        url="https://kb.example.com/article/12345",
    )

    path = await scraper.download_article(meta)

    assert path == temp_dir / "12345.html"
    assert path.exists()

    # Check HTML was saved
    html_content = path.read_text()
    assert "<h1>Test Article</h1>" in html_content

    # Check metadata sidecar was created
    meta_path = temp_dir / "12345.meta.json"
    assert meta_path.exists()
    meta_data = json.loads(meta_path.read_text())
    assert meta_data["article_number"] == "12345"
    assert meta_data["title"] == "Test Article"

    # State updated
    assert "12345" in scraper.state.downloaded


@pytest.mark.asyncio
async def test_download_article_skip_if_exists(temp_dir: Path):
    """Test that existing articles are not re-downloaded."""
    scraper = BroadcomKBScraper(
        output_dir=temp_dir,
        use_auth=False,
    )

    # Create the HTML file and add to state with matching checksum
    html_content = "<html><body>Pre-existing Article</body></html>"
    (temp_dir / "54321.html").write_text(html_content)
    checksum = scraper._calculate_checksum(html_content)
    scraper.state.downloaded.add("54321")
    scraper.state.checksums["54321"] = checksum
    scraper.state.save(scraper.state_file)

    mock_client = _make_mock_client()
    scraper._client = mock_client

    meta = KBArticleMeta(
        article_number="54321",
        title="Pre-existing Article",
        url="https://kb.example.com/article/54321",
    )

    path = await scraper.download_article(meta)

    assert path == temp_dir / "54321.html"
    # Should not have made any HTTP requests
    mock_client.get.assert_not_called()

@pytest.mark.asyncio
async def test_scrape_public_mode(temp_dir: Path):
    """Test full scrape pipeline in public mode (no auth)."""
    scraper = BroadcomKBScraper(
        output_dir=temp_dir,
        max_articles=5,
        use_auth=False,
        delay_seconds=0.0,  # No delay for tests
    )

    mock_client = _make_mock_client()

    # Page 1: search response (JSON) with 1 result
    search_resp_page1 = AsyncMock()
    search_resp_page1.status_code = 200
    search_resp_page1.headers = {"content-type": "application/json"}
    search_resp_page1.raise_for_status = MagicMock()
    search_resp_page1.json = MagicMock(return_value={
        "results": [
            {
                "articleNumber": "111111",
                "title": "First Article",
                "url": "https://kb.example.com/article/111111",
                "product": "TestProduct",
                "lastUpdated": "2024-01-01",
                "score": 0.9,
            }
        ],
        "total": 1
    })

    # Page 2: empty search response (signals end)
    search_resp_page2 = AsyncMock()
    search_resp_page2.status_code = 200
    search_resp_page2.headers = {"content-type": "application/json"}
    search_resp_page2.raise_for_status = MagicMock()
    search_resp_page2.json = MagicMock(return_value={
        "results": [],
        "total": 1
    })

    # Article download response
    article_resp = AsyncMock()
    article_resp.status_code = 200
    article_resp.text = "<html><body><h1>First Article</h1><p>Details</p></body></html>"
    article_resp.url = "https://kb.example.com/article/111111"
    article_resp.raise_for_status = MagicMock()

    # Call order: search page1, download article, search page2 (empty)
    mock_client.get = AsyncMock(side_effect=[search_resp_page1, article_resp, search_resp_page2])
    scraper._client = mock_client

    # Directly call scrape (bypass __aenter__/__aexit__)
    paths = await scraper.scrape(query="test")

    assert len(paths) == 1
    assert paths[0] == temp_dir / "111111.html"
    assert paths[0].exists()
    assert "111111" in scraper.state.downloaded
    assert scraper.state.total_found == 1


# --- Checksum Tests ---


def test_calculate_checksum():
    """Test SHA256 checksum calculation."""
    from src.scraper.broadcom_kb import BroadcomKBScraper

    # Same content should produce same checksum
    content1 = "<html><body>Test Article</body></html>"
    content2 = "<html><body>Test Article</body></html>"
    checksum1 = BroadcomKBScraper._calculate_checksum(content1)
    checksum2 = BroadcomKBScraper._calculate_checksum(content2)
    assert checksum1 == checksum2
    assert len(checksum1) == 64  # SHA256 hex digest length

    # Different content should produce different checksums
    content3 = "<html><body>Different Article</body></html>"
    checksum3 = BroadcomKBScraper._calculate_checksum(content3)
    assert checksum1 != checksum3


def test_scraper_state_with_checksums(temp_dir: Path):
    """Test that scraper state persists checksums correctly."""
    state_file = temp_dir / ".scraper_state.json"

    # Create state with checksums
    state = ScraperState()
    state.downloaded = {"12345", "67890"}
    state.failed = {"54321"}
    state.total_found = 1000
    state.checksums = {"12345": "abc123", "67890": "def456"}
    state.save(state_file)

    # Load state
    loaded = ScraperState.load(state_file)
    assert loaded.downloaded == {"12345", "67890"}
    assert loaded.failed == {"54321"}
    assert loaded.total_found == 1000
    assert loaded.checksums == {"12345": "abc123", "67890": "def456"}


# --- Incremental Scraping Tests ---


@pytest.mark.asyncio
async def test_skip_unchanged_article(temp_dir: Path):
    """Test that unchanged articles are skipped during incremental scraping."""
    scraper = BroadcomKBScraper(output_dir=temp_dir, use_auth=False)
    scraper.delay_seconds = 0.0

    # Create existing article with matching checksum
    article_html = "<html><body><h1>Test</h1></body></html>"
    (temp_dir / "99999.html").write_text(article_html)
    checksum = scraper._calculate_checksum(article_html)
    scraper.state.downloaded.add("99999")
    scraper.state.checksums["99999"] = checksum
    scraper.state.save(scraper.state_file)

    mock_client = _make_mock_client()
    scraper._client = mock_client

    meta = KBArticleMeta(
        article_number="99999",
        title="Test",
        url="https://kb.example.com/article/99999",
    )

    path = await scraper.download_article(meta)

    assert path == temp_dir / "99999.html"
    # Should not have made HTTP request
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_redownload_changed_article(temp_dir: Path):
    """Test that changed articles are re-downloaded."""
    scraper = BroadcomKBScraper(output_dir=temp_dir, use_auth=False)
    scraper.delay_seconds = 0.0

    # Create existing article with OLD checksum
    old_html = "<html><body><h1>Old Version</h1></body></html>"
    (temp_dir / "88888.html").write_text(old_html)
    scraper.state.downloaded.add("88888")
    scraper.state.checksums["88888"] = "old_checksum_value"
    scraper.state.save(scraper.state_file)

    # Mock new content from server
    new_html = "<html><body><h1>Updated Version</h1></body></html>"
    new_checksum = scraper._calculate_checksum(new_html)
    assert new_checksum != "old_checksum_value"

    mock_client = _make_mock_client()
    article_resp = AsyncMock()
    article_resp.status_code = 200
    article_resp.text = new_html
    article_resp.url = "https://kb.example.com/article/88888"
    article_resp.raise_for_status = MagicMock()
    mock_client.get = AsyncMock(return_value=article_resp)
    scraper._client = mock_client

    meta = KBArticleMeta(
        article_number="88888",
        title="Updated",
        url="https://kb.example.com/article/88888",
    )

    path = await scraper.download_article(meta)

    assert path == temp_dir / "88888.html"
    assert scraper.state.checksums["88888"] == new_checksum
    # Should have made HTTP request
    mock_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_skip_nonexistent_file(temp_dir: Path):
    """Test that articles marked as downloaded but missing on disk are re-downloaded."""
    scraper = BroadcomKBScraper(output_dir=temp_dir, use_auth=False)
    scraper.delay_seconds = 0.0

    # Mark as downloaded but don't create the file
    scraper.state.downloaded.add("77777")
    scraper.state.save(scraper.state_file)

    mock_client = _make_mock_client()
    article_resp = AsyncMock()
    article_resp.status_code = 200
    article_resp.text = "<html><body><h1>New</h1></body></html>"
    article_resp.url = "https://kb.example.com/article/77777"
    article_resp.raise_for_status = MagicMock()
    mock_client.get = AsyncMock(return_value=article_resp)
    scraper._client = mock_client

    meta = KBArticleMeta(
        article_number="77777",
        title="New",
        url="https://kb.example.com/article/77777",
    )

    path = await scraper.download_article(meta)

    assert path == temp_dir / "77777.html"
    assert path.exists()
    # Should have made HTTP request since file didn't exist
    mock_client.get.assert_called_once()


# --- Failure Path Tests ---


@pytest.mark.asyncio
async def test_download_article_http_error(temp_dir: Path):
    """Test that download failure tracks in state after retries."""
    scraper = BroadcomKBScraper(output_dir=temp_dir, use_auth=False)

    mock_client = _make_mock_client()
    mock_client.get = AsyncMock(side_effect=httpx.HTTPError("Connection failed"))
    scraper._client = mock_client

    meta = KBArticleMeta(
        article_number="99999",
        title="Fail Article",
        url="https://kb.example.com/article/99999",
    )

    with pytest.raises(Exception):  # tenacity.RetryError wrapping HTTPError
        await scraper.download_article(meta)

    assert "99999" in scraper.state.failed


@pytest.mark.asyncio
async def test_search_articles_http_error(temp_dir: Path):
    """Test that search failure breaks the loop after retries."""
    scraper = BroadcomKBScraper(output_dir=temp_dir, max_articles=10, use_auth=False)
    scraper.delay_seconds = 0.0

    mock_client = _make_mock_client()
    mock_client.get = AsyncMock(side_effect=httpx.HTTPError("Server error"))
    scraper._client = mock_client

    articles = []
    with pytest.raises(Exception):  # tenacity.RetryError wrapping HTTPError
        async for meta in scraper.search_articles(query="test"):
            articles.append(meta)

    assert articles == []


@pytest.mark.asyncio
async def test_authenticate_with_playwright_import_error(temp_dir: Path):
    """Test playwright auth fallback when playwright is not installed."""
    scraper = BroadcomKBScraper(
        output_dir=temp_dir,
        username="test@example.com",
        password="secret",
        use_auth=True,
    )
    scraper._client = _make_mock_client()

    with patch.dict("sys.modules", {"playwright": None, "playwright.async_api": None}):
        import sys
        # Force reimport to trigger ImportError
        if "src.scraper.broadcom_kb" in sys.modules:
            del sys.modules["src.scraper.broadcom_kb"]

        result = await scraper.authenticate_with_playwright()
        assert result is False


@pytest.mark.asyncio
async def test_authenticate_with_playwright_requires_client(temp_dir: Path):
    """Playwright auth should fail clearly if the HTTP client is not initialized."""
    scraper = BroadcomKBScraper(
        output_dir=temp_dir,
        username="test@example.com",
        use_auth=True,
    )

    with pytest.raises(RuntimeError, match="HTTP client not initialized"):
        await scraper.authenticate_with_playwright()


@pytest.mark.asyncio
async def test_cache_read_race_redownloads_article(
    temp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """If a cached file disappears while being checked, it should be re-downloaded."""
    scraper = BroadcomKBScraper(output_dir=temp_dir, use_auth=False)
    cached_path = temp_dir / "66666.html"
    cached_path.write_text("<html><body>Cached</body></html>")
    scraper.state.downloaded.add("66666")
    scraper.state.checksums["66666"] = "cached-checksum"
    monkeypatch.setattr(
        scraper,
        "_read_cached_article",
        MagicMock(side_effect=FileNotFoundError(cached_path)),
    )

    article_resp = AsyncMock()
    article_resp.status_code = 200
    article_resp.text = "<html><body>Fresh</body></html>"
    article_resp.url = "https://kb.example.com/article/66666"
    article_resp.raise_for_status = MagicMock()

    mock_client = _make_mock_client()
    mock_client.get = AsyncMock(return_value=article_resp)
    scraper._client = mock_client

    meta = KBArticleMeta(
        article_number="66666",
        title="Fresh",
        url="https://kb.example.com/article/66666",
    )

    path = await scraper.download_article(meta)

    assert path == cached_path
    mock_client.get.assert_called_once()


def test_scraper_init_with_zero_delay(tmp_path: Path):
    """Test that delay_seconds=0.0 is respected (not treated as falsy)."""
    scraper = BroadcomKBScraper(
        output_dir=tmp_path,
        delay_seconds=0.0,
        use_auth=False,
    )
    assert scraper.delay_seconds == 0.0


def test_scraper_init_with_zero_max_articles(tmp_path: Path):
    """Test that max_articles=0 is respected (not treated as falsy)."""
    scraper = BroadcomKBScraper(
        output_dir=tmp_path,
        max_articles=0,
        use_auth=False,
    )
    assert scraper.max_articles == 0


def test_scraper_state_load_corrupted_json(tmp_path: Path):
    """Test loading corrupted state file."""
    state_file = tmp_path / ".scraper_state.json"
    state_file.write_text("{invalid json")

    with pytest.raises(json.JSONDecodeError):
        ScraperState.load(state_file)
