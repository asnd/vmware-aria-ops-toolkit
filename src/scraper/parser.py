"""HTML parser for VMware/Broadcom KB articles.

Extracts structured content from KB article HTML pages,
including sections (Symptom, Cause, Resolution), metadata,
and related articles.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

MAX_HTML_FILE_BYTES = 10 * 1024 * 1024


@dataclass
class KBSection:
    """A section within a KB article (e.g., Symptom, Cause, Resolution)."""

    heading: str
    content: str
    section_type: str = "general"  # symptom, cause, resolution, workaround, etc.


@dataclass
class ParsedKBArticle:
    """Fully parsed KB article with structured content."""

    article_number: str
    title: str
    url: str = ""
    product: str = ""
    version: str = ""
    last_updated: str = ""
    sections: list[KBSection] = field(default_factory=list)
    raw_text: str = ""
    related_articles: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """Get all section content concatenated."""
        if self.sections:
            return "\n\n".join(
                f"## {s.heading}\n{s.content}" for s in self.sections
            )
        return self.raw_text

    def to_dict(self) -> dict[str, object]:
        """Serialize to dictionary."""
        return {
            "article_number": self.article_number,
            "title": self.title,
            "url": self.url,
            "product": self.product,
            "version": self.version,
            "last_updated": self.last_updated,
            "sections": [
                {"heading": s.heading, "content": s.content, "section_type": s.section_type}
                for s in self.sections
            ],
            "raw_text": self.raw_text,
            "related_articles": self.related_articles,
            "tags": self.tags,
        }


# Known section headings in VMware KB articles
SECTION_TYPE_MAP: dict[str, str] = {
    "symptoms": "symptom",
    "symptom": "symptom",
    "cause": "cause",
    "root cause": "cause",
    "resolution": "resolution",
    "solution": "resolution",
    "workaround": "workaround",
    "additional information": "additional_info",
    "more information": "additional_info",
    "purpose": "purpose",
    "details": "details",
    "environment": "environment",
    "prerequisites": "prerequisites",
    "procedure": "procedure",
    "steps": "procedure",
}


class KBArticleParser:
    """Parser for VMware/Broadcom Knowledge Base HTML articles.

    Handles various KB article formats and extracts structured sections,
    metadata, and related article links.
    """

    def parse_file(self, html_path: Path) -> ParsedKBArticle:
        """Parse a KB article from an HTML file.

        Args:
            html_path: Path to the HTML file.

        Returns:
            ParsedKBArticle with structured content.
        """
        file_size = html_path.stat().st_size
        if file_size > MAX_HTML_FILE_BYTES:
            raise ValueError(
                f"HTML file is too large to parse safely: {html_path} "
                f"({file_size} bytes > {MAX_HTML_FILE_BYTES} bytes)"
            )
        html_content = html_path.read_text(encoding="utf-8")
        article_number = html_path.stem  # filename without extension

        # Load metadata sidecar if available
        meta_path = html_path.with_suffix(".meta.json")
        metadata: dict[str, object] = {}
        if meta_path.exists():
            try:
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning("Failed to parse metadata file: %s", meta_path)

        return self.parse_html(
            html_content=html_content,
            article_number=article_number,
            metadata=metadata,
        )

    def parse_html(
        self,
        html_content: str,
        article_number: str = "",
        metadata: dict | None = None,
    ) -> ParsedKBArticle:
        """Parse KB article HTML content.

        Args:
            html_content: Raw HTML string.
            article_number: KB article number.
            metadata: Optional metadata dict from sidecar file.

        Returns:
            ParsedKBArticle with structured content.
        """
        metadata = metadata or {}
        soup = BeautifulSoup(html_content, "lxml")

        # Extract title
        title = self._extract_title(soup, metadata)

        # Extract main content area
        content_area = self._find_content_area(soup)

        # Extract sections
        sections = self._extract_sections(content_area or soup)

        # Extract raw text as fallback
        raw_text = self._extract_raw_text(content_area or soup)

        # Extract metadata from page
        product, version = self._extract_product_info(soup, metadata)
        last_updated = self._extract_date(soup, metadata)
        related = self._extract_related_articles(soup)
        tags = self._extract_tags(soup)

        return ParsedKBArticle(
            article_number=article_number,
            title=title,
            url=metadata.get("url", ""),
            product=product,
            version=version,
            last_updated=last_updated,
            sections=sections,
            raw_text=raw_text,
            related_articles=related,
            tags=tags,
        )

    def _extract_title(self, soup: BeautifulSoup, metadata: dict) -> str:
        """Extract article title."""
        if metadata.get("title"):
            return metadata["title"]

        # knowledge.broadcom.com: title is in <h3 class="wolken-h3"> inside article-header
        wolken_h3 = soup.select_one(".article-header .wolken-h3, h3.wolken-h3")
        if wolken_h3:
            return wolken_h3.get_text(strip=True)

        title_tag = soup.find("title")
        if title_tag:
            text = title_tag.get_text(strip=True)
            for suffix in [" - VMware", " - Broadcom", " | Knowledge Base", " | Broadcom"]:
                text = text.removesuffix(suffix)
            return text

        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)

        return ""

    def _find_content_area(self, soup: BeautifulSoup) -> Tag | None:
        """Find the main content area of the KB article."""
        selectors = [
            # knowledge.broadcom.com structure
            ".wolken-content-container",
            ".article-container",
            ".article-page",
            # Legacy broadcom.com structure
            ".article-content",
            ".kb-article-content",
            "#article-content",
            ".content-body",
            'article[role="main"]',
            "article",
            ".main-content",
            "#main-content",
            'div[class*="article"]',
        ]

        for selector in selectors:
            element = soup.select_one(selector)
            if element and len(element.get_text(strip=True)) > 20:
                return element

        body = soup.find("body")
        if body:
            divs = body.find_all("div")
            if divs:
                largest = max(divs, key=lambda d: len(d.get_text(strip=True)))
                if len(largest.get_text(strip=True)) > 20:
                    return largest

        return None

    def _extract_sections(self, content: Tag | BeautifulSoup) -> list[KBSection]:
        """Extract structured sections from KB article content."""
        # knowledge.broadcom.com: each section is a div.article-detail-card
        cards = content.find_all("div", class_="article-detail-card")
        if cards:
            return self._parse_detail_cards(cards)

        # Legacy: headings followed by sibling content
        return self._parse_heading_sections(content)

    def _parse_detail_cards(self, cards: list[Tag]) -> list[KBSection]:
        """Parse knowledge.broadcom.com article-detail-card sections."""
        sections: list[KBSection] = []
        # Skip-list for non-content cards (Products card has no prose worth indexing)
        skip_headings = {"products"}

        for card in cards:
            header_el = card.select_one(
                ".article-detail-card-header h4, .article-detail-card-header h3"
            )
            heading = header_el.get_text(strip=True) if header_el else ""
            if not heading or heading.lower() in skip_headings:
                continue

            content_el = card.select_one(".article-detail-card-content")
            if not content_el:
                continue

            # Strip scripts/styles inside the card
            for tag in content_el.find_all(["script", "style"]):
                tag.decompose()

            text = content_el.get_text(separator="\n", strip=True)
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            if not text:
                continue

            sections.append(KBSection(
                heading=heading,
                content=text,
                section_type=self._classify_section(heading),
            ))

        return sections

    def _parse_heading_sections(self, content: Tag | BeautifulSoup) -> list[KBSection]:
        """Legacy parser: headings followed by sibling content."""
        sections: list[KBSection] = []
        headings = content.find_all(["h2", "h3", "h4", "strong", "b"])

        for heading in headings:
            heading_text = heading.get_text(strip=True).rstrip(":")
            if not heading_text:
                continue

            section_type = self._classify_section(heading_text)
            content_parts: list[str] = []
            sibling = heading.next_sibling

            while sibling:
                if isinstance(sibling, Tag):
                    if sibling.name in ["h2", "h3", "h4"]:
                        break
                    if sibling.name in ["strong", "b"]:
                        text = sibling.get_text(strip=True)
                        if text.rstrip(":").lower() in SECTION_TYPE_MAP:
                            break
                    content_parts.append(sibling.get_text(separator="\n", strip=True))
                elif isinstance(sibling, str) and sibling.strip():
                    content_parts.append(sibling.strip())
                sibling = sibling.next_sibling

            section_content = "\n".join(p for p in content_parts if p)
            if section_content:
                sections.append(KBSection(
                    heading=heading_text,
                    content=section_content,
                    section_type=section_type,
                ))

        return sections

    def _classify_section(self, heading_text: str) -> str:
        """Classify a section heading into a known type."""
        normalized = heading_text.lower().strip().rstrip(":")
        return SECTION_TYPE_MAP.get(normalized, "general")

    def _extract_raw_text(self, content: Tag | BeautifulSoup) -> str:
        """Extract clean text from content, removing scripts and styles."""
        # Remove script and style elements
        for element in content.find_all(["script", "style", "nav", "footer", "header"]):
            element.decompose()

        text = content.get_text(separator="\n", strip=True)
        # Normalize whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _extract_product_info(
        self, soup: BeautifulSoup, metadata: dict
    ) -> tuple[str, str]:
        """Extract product name and version from the article."""
        product = str(metadata.get("product", ""))
        version = str(metadata.get("version", ""))

        # knowledge.broadcom.com: products listed as <span class="product-chip">
        chips = soup.select(".product-chip")
        if chips and not product:
            product = ", ".join(c.get_text(strip=True) for c in chips if c.get_text(strip=True))

        if not product:
            meta_product = soup.find("meta", attrs={"name": re.compile(r"product", re.I)})
            if meta_product and isinstance(meta_product, Tag):
                product = str(meta_product.get("content", "") or meta_product.get("value", ""))

        if not product:
            vmware_products = ["vsphere", "vcenter", "esxi", "nsx", "vsan", "horizon", "aria"]
            legacy_sel = '.product-name, .breadcrumb a, [class*="product"], span[class*="label"]'
            for el in soup.select(legacy_sel):
                text = el.get_text(strip=True)
                if any(p in text.lower() for p in vmware_products):
                    product = text
                    break

        if not version:
            meta_version = soup.find("meta", attrs={"name": re.compile(r"version", re.I)})
            if meta_version and isinstance(meta_version, Tag):
                version = str(meta_version.get("content", "") or meta_version.get("value", ""))

        if not version:
            version_pattern = re.compile(
                r"(\d+\.\d+(?:\.\d+)?(?:\s*(?:U\d+|Update\s*\d+|Build\s*\d+))?)"
            )
            version_sel = '[class*="version"], .article-meta, .article-detail-card-content'
            for el in soup.select(version_sel):
                match = version_pattern.search(el.get_text())
                if match:
                    version = match.group(1)
                    break

        return product, version

    def _extract_date(self, soup: BeautifulSoup, metadata: dict) -> str:
        """Extract last updated date."""
        if metadata.get("last_updated"):
            return str(metadata["last_updated"])

        # knowledge.broadcom.com: "Updated On: <date>" inside .article-updated-time
        for el in soup.select(".article-updated-time"):
            text = el.get_text(strip=True)
            # Skip the "Article ID: XXXXXX" row
            if re.search(r"\d{4}", text):
                for prefix in ["Updated On:", "Updated:", "Last Updated:"]:
                    if text.startswith(prefix):
                        text = text[len(prefix):].strip()
                        break
                return text

        date_selectors = [
            'meta[name="last-modified"]',
            'meta[name="date"]',
            'meta[property="article:modified_time"]',
            ".last-updated",
            ".article-date",
            '[class*="date"]',
        ]
        for selector in date_selectors:
            el = soup.select_one(selector)
            if el:
                if isinstance(el, Tag) and el.name == "meta":
                    return str(el.get("content", ""))
                text = el.get_text(strip=True)
                for prefix in [
                    "Last Updated:", "Last Modified:", "Date:",
                    "Updated:", "Modified:", "Published:",
                ]:
                    if text.startswith(prefix):
                        text = text[len(prefix):].strip()
                        break
                return text

        return ""

    def _extract_related_articles(self, soup: BeautifulSoup) -> list[str]:
        """Extract related article numbers from the page."""
        related: list[str] = []

        # Look for links to other KB articles
        links = soup.find_all("a", href=re.compile(r"article.*\d{5,}"))
        for link in links:
            href = link.get("href", "")
            match = re.search(r"(\d{5,})", href)
            if match:
                article_num = match.group(1)
                if article_num not in related:
                    related.append(article_num)

        # Also look for KB article numbers mentioned in text (e.g., "KB123456")
        body_text = soup.get_text()
        text_refs = re.findall(r"KB(\d{5,})", body_text, re.IGNORECASE)
        for article_num in text_refs:
            if article_num not in related:
                related.append(article_num)

        return related[:20]  # Cap at 20 related articles

    def _extract_tags(self, soup: BeautifulSoup) -> list[str]:
        """Extract tags/categories from the article."""
        tags: list[str] = []

        tag_elements = soup.select(
            '.tag, .label, [class*="tag"], [class*="category"], '
            'meta[name="keywords"]'
        )

        for el in tag_elements:
            if isinstance(el, Tag) and el.name == "meta":
                content = el.get("content", "")
                if isinstance(content, str):
                    tags.extend(t.strip() for t in content.split(",") if t.strip())
            else:
                text = el.get_text(strip=True)
                if text and len(text) < 50:  # Skip overly long "tags"
                    tags.append(text)

        return list(set(tags))[:20]


def parse_directory(directory: Path) -> list[ParsedKBArticle]:
    """Parse all KB article HTML files in a directory.

    Args:
        directory: Path to directory containing HTML files.

    Returns:
        List of parsed articles.
    """
    parser = KBArticleParser()
    articles: list[ParsedKBArticle] = []

    html_files = sorted(directory.glob("*.html"))
    logger.info("Found %d HTML files in %s", len(html_files), directory)

    for html_path in html_files:
        try:
            article = parser.parse_file(html_path)
            articles.append(article)
            logger.debug(
                "Parsed KB %s: %s (%d sections)",
                article.article_number,
                article.title,
                len(article.sections),
            )
        except Exception as e:
            logger.error("Failed to parse %s: %s", html_path.name, e)

    logger.info("Successfully parsed %d articles", len(articles))
    return articles
