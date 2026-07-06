"""Broadcom Knowledge Base scraper with authenticated session management.

Handles login to the Broadcom support portal and downloads KB articles
with rate limiting and exponential backoff.
"""

import asyncio
import hashlib
import json
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import get_settings

logger = logging.getLogger(__name__)

# Broadcom KB portal endpoints
BROADCOM_LOGIN_URL = "https://support.broadcom.com/auth/login"
BROADCOM_KB_SEARCH_URL = "https://knowledge.broadcom.com/external/search"
BROADCOM_KB_ARTICLE_BASE = "https://knowledge.broadcom.com/external/article"
# Legacy alias kept for any external references
BROADCOM_KB_ARTICLE_URL = BROADCOM_KB_ARTICLE_BASE


@dataclass
class KBArticleMeta:
    """Metadata for a KB article before full download."""

    article_number: str
    title: str
    url: str
    product: str = ""
    last_updated: str = ""
    relevance_score: float = 0.0


@dataclass
class ScraperState:
    """Tracks scraper progress for resumability."""

    downloaded: set[str] = field(default_factory=set)
    failed: set[str] = field(default_factory=set)
    total_found: int = 0
    checksums: dict[str, str] = field(default_factory=dict)  # article_number -> sha256 hexdigest

    def save(self, path: Path) -> None:
        """Persist state to disk for resume capability."""
        state = {
            "downloaded": list(self.downloaded),
            "failed": list(self.failed),
            "total_found": self.total_found,
            "checksums": self.checksums,
        }
        path.write_text(json.dumps(state, indent=2))

    @classmethod
    def load(cls, path: Path) -> "ScraperState":
        """Load state from disk."""
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        return cls(
            downloaded=set(data.get("downloaded", [])),
            failed=set(data.get("failed", [])),
            total_found=data.get("total_found", 0),
            checksums=data.get("checksums", {}),
        )


class BroadcomKBScraper:
    """Authenticated scraper for Broadcom/VMware Knowledge Base articles.

    Uses httpx for async HTTP with session cookies and playwright
    as fallback for JavaScript-rendered pages.
    """

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        output_dir: Path | None = None,
        delay_seconds: float | None = None,
        max_articles: int | None = None,
        use_auth: bool | None = None,
    ):
        settings = get_settings()
        self.username: str = username or settings.broadcom_username
        self.password: str = (
            password if password is not None
            else settings.broadcom_password.get_secret_value()
        )
        self.output_dir = output_dir or settings.scraper_output_dir
        self.delay_seconds = (
            delay_seconds if delay_seconds is not None else settings.scraper_delay_seconds
        )
        self.max_articles = (
            max_articles if max_articles is not None else settings.scraper_max_articles
        )
        self.use_auth = use_auth if use_auth is not None else settings.scraper_use_auth

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.output_dir / ".scraper_state.json"
        self.state = ScraperState.load(self.state_file)

        self._client: httpx.AsyncClient | None = None
        self._authenticated = False

    async def __aenter__(self) -> "BroadcomKBScraper":
        """Initialize HTTP client with session and connection pooling."""
        self._client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
        )
        return self

    async def __aexit__(self, *args: object) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()

    async def authenticate(self) -> bool:
        """Authenticate with Broadcom support portal.

        The Broadcom portal uses OAuth/SAML flow. This method handles
        the authentication and stores session cookies.

        Returns:
            True if authentication succeeded.
        """
        if not self.username or not self.password:
            logger.warning(
                "No credentials provided. Will attempt to scrape public articles only."
            )
            return False

        if self._client is None:
            raise RuntimeError("HTTP client not initialized. Use the scraper as a context manager.")

        logger.info("Authenticating with Broadcom support portal...")

        try:
            # Step 1: Get the login page to obtain CSRF token / session cookie
            login_page = await self._client.get(BROADCOM_LOGIN_URL)
            login_page.raise_for_status()

            # Step 2: Submit credentials
            # Note: Broadcom's exact auth flow may vary. This handles the common
            # form-based POST. If they use OAuth redirect, we may need playwright.
            auth_payload = {
                "username": self.username,
                "password": self.password,
            }

            response = await self._client.post(
                BROADCOM_LOGIN_URL,
                data=auth_payload,
            )

            if response.status_code in (200, 302):
                self._authenticated = True
                logger.info("Successfully authenticated with Broadcom portal.")
                return True
            else:
                logger.error(
                    "Authentication failed with status %s. "
                    "Falling back to public articles.",
                    response.status_code,
                )
                return False

        except httpx.HTTPError as e:
            logger.error("Authentication error: %s. Falling back to public articles.", e)
            return False

    async def authenticate_with_playwright(self) -> bool:
        """Fallback: Use playwright for JavaScript-heavy auth flows.

        Some Broadcom portal pages require JavaScript execution for
        proper authentication (OAuth redirects, CAPTCHA, etc.).
        """
        if self._client is None:
            raise RuntimeError("HTTP client not initialized. Use the scraper as a context manager.")

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("playwright not installed. Run: playwright install chromium")
            return False

        logger.info("Using playwright for browser-based authentication...")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            try:
                await page.goto(BROADCOM_LOGIN_URL, wait_until="networkidle")

                # Fill login form
                await page.fill('input[name="username"], input[type="email"]', self.username)
                await page.fill('input[name="password"], input[type="password"]', self.password)
                await page.click('button[type="submit"], input[type="submit"]')

                # Wait for redirect after login
                await page.wait_for_load_state("networkidle", timeout=30000)

                # Extract cookies and transfer to httpx client
                cookies = await context.cookies()
                for cookie in cookies:
                    self._client.cookies.set(  # type: ignore[union-attr]
                        cookie["name"],
                        cookie["value"],
                        domain=cookie.get("domain", ""),
                    )

                self._authenticated = True
                logger.info("Browser-based authentication successful.")
                return True

            except Exception as e:
                logger.error("Playwright authentication failed: %s", e)
                return False
            finally:
                await browser.close()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    )
    async def _fetch_page(self, url: str, **kwargs: object) -> httpx.Response:
        """Fetch a page with retry logic."""
        if self._client is None:
            raise RuntimeError("HTTP client not initialized. Use the scraper as a context manager.")
        response = await self._client.get(url, **kwargs)  # type: ignore[arg-type]
        response.raise_for_status()
        return response

    @staticmethod
    def _calculate_checksum(content: str) -> str:
        """Calculate SHA256 checksum of content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _read_cached_article(output_path: Path) -> str:
        """Read a cached article from disk for checksum validation."""
        return output_path.read_text(encoding="utf-8")

    def _has_matching_cached_article(self, article_number: str, output_path: Path) -> bool:
        """Return True when a cached article exists and still matches stored state."""
        if article_number not in self.state.downloaded or not output_path.exists():
            return False
        if article_number not in self.state.checksums:
            logger.debug("Skipping already downloaded: %s", article_number)
            return True
        try:
            current_checksum = self._calculate_checksum(self._read_cached_article(output_path))
        except OSError as exc:
            logger.info(
                "Cached article %s is unavailable, re-downloading: %s",
                article_number,
                str(exc),
            )
            return False
        if current_checksum == self.state.checksums[article_number]:
            logger.debug("Skipping unchanged article: %s", article_number)
            return True
        logger.info("Article changed, re-downloading: %s", article_number)
        return False

    async def search_articles(
        self,
        query: str = "vmware",
        product_filter: str | None = None,
        max_results: int | None = None,
    ) -> AsyncIterator[KBArticleMeta]:
        """Search KB articles and yield metadata.

        Args:
            query: Search query string.
            product_filter: Filter by product name (e.g., "vSphere", "NSX", "vSAN").
            max_results: Maximum number of results to return.

        Yields:
            KBArticleMeta for each found article.
        """
        max_results = max_results or self.max_articles
        page = 0
        page_size = 20
        yielded = 0

        while yielded < max_results:
            # Build search URL with pagination
            params: dict[str, str | int] = {
                "q": query,
                "offset": page * page_size,
                "limit": page_size,
            }
            if product_filter:
                params["product"] = product_filter

            try:
                response = await self._fetch_page(
                    BROADCOM_KB_SEARCH_URL,
                    params=params,
                )
            except httpx.HTTPError as e:
                logger.error("Search failed at page %d: %s", page, e)
                break

            content_type = response.headers.get("content-type", "")

            if "application/json" in content_type:
                data = response.json()
                # knowledge.broadcom.com returns {"articles": [...], "total": N}
                articles = data.get("articles", data.get("results", []))
                total = data.get("total", data.get("totalCount", 0))
                self.state.total_found = total

                if not articles:
                    break

                for article in articles:
                    if yielded >= max_results:
                        return
                    article_id = str(
                        article.get("id", article.get("articleNumber", ""))
                    )
                    meta = KBArticleMeta(
                        article_number=article_id,
                        title=article.get("title", ""),
                        url=article.get(
                            "url", f"{BROADCOM_KB_ARTICLE_BASE}/{article_id}"
                        ),
                        product=article.get("product", ""),
                        last_updated=article.get("lastUpdated", article.get("updatedOn", "")),
                        relevance_score=float(article.get("score", 0)),
                    )
                    yield meta
                    yielded += 1
            else:
                # HTML response — parse article links from the page
                soup = BeautifulSoup(response.text, "lxml")
                article_links = soup.select(
                    'a[href*="/external/article"], '
                    'a[href*="articleNumber"], '
                    '.search-result a, '
                    '.article-link'
                )

                if not article_links:
                    logger.warning("No articles found on search page %d", page)
                    break

                for link in article_links:
                    if yielded >= max_results:
                        return
                    href = link.get("href", "")
                    title = link.get_text(strip=True)
                    article_number = self._extract_article_number(href)
                    if not article_number:
                        continue
                    meta = KBArticleMeta(
                        article_number=article_number,
                        title=title,
                        url=href if href.startswith("http") else f"https://knowledge.broadcom.com{href}",
                    )
                    yield meta
                    yielded += 1

            page += 1
            await asyncio.sleep(self.delay_seconds)

    @staticmethod
    def _extract_article_number(url: str) -> str:
        """Extract article number from KB URL."""
        match = re.search(r"articleNumber=(\d+)", url)
        if match:
            return match.group(1)
        match = re.search(r"/article/(\d+)", url)
        if match:
            return match.group(1)
        return ""

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    )
    async def download_article(self, meta: KBArticleMeta) -> Path | None:
        """Download a single KB article and save to disk.

        Args:
            meta: Article metadata from search results.

        Returns:
            Path to saved HTML file, or None on failure.
        """
        output_path = self.output_dir / f"{meta.article_number}.html"

        # Incremental scraping: skip if already downloaded and checksum matches
        if self._has_matching_cached_article(meta.article_number, output_path):
            return output_path

        if self._client is None:
            raise RuntimeError("HTTP client not initialized. Use the scraper as a context manager.")
        logger.info("Downloading KB %s: %s", meta.article_number, meta.title)

        try:
            response = await self._client.get(meta.url)
            response.raise_for_status()

            # Save HTML
            html_content = response.text
            output_path.write_text(html_content, encoding="utf-8")

            # Calculate and save checksum
            checksum = self._calculate_checksum(html_content)
            self.state.checksums[meta.article_number] = checksum

            # Save metadata sidecar
            meta_path = self.output_dir / f"{meta.article_number}.meta.json"
            meta_path.write_text(
                json.dumps(
                    {
                        "article_number": meta.article_number,
                        "title": meta.title,
                        "url": meta.url,
                        "product": meta.product,
                        "last_updated": meta.last_updated,
                        "download_url": str(response.url),
                        "checksum": checksum,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            self.state.downloaded.add(meta.article_number)
            self.state.save(self.state_file)
            return output_path

        except httpx.HTTPError as e:
            logger.error("Failed to download KB %s: %s", meta.article_number, e)
            self.state.failed.add(meta.article_number)
            self.state.save(self.state_file)
            raise

    async def scrape(
        self,
        query: str = "vmware",
        product_filter: str | None = None,
    ) -> list[Path]:
        """Run the full scraping pipeline.

        Args:
            query: Search query.
            product_filter: Optional product filter.

        Returns:
            List of paths to downloaded articles.
        """
        downloaded_paths: list[Path] = []

        # Only attempt authentication if explicitly enabled
        if self.use_auth:
            auth_success = await self.authenticate()
            if not auth_success:
                # Try playwright fallback
                auth_success = await self.authenticate_with_playwright()
                if not auth_success:
                    logger.warning(
                        "Authentication failed. Proceeding with public articles only."
                    )
        else:
            logger.info("Running in public mode (no authentication). Use --auth to enable.")

        # Search and download
        async for meta in self.search_articles(
            query=query, product_filter=product_filter
        ):
            try:
                path = await self.download_article(meta)
                if path:
                    downloaded_paths.append(path)
            except Exception as e:
                logger.error("Skipping KB %s after retries: %s", meta.article_number, e)

        logger.info(
            "Scraping complete. Downloaded: %d, Failed: %d, Total found: %d",
            len(downloaded_paths),
            len(self.state.failed),
            self.state.total_found,
        )
        return downloaded_paths
