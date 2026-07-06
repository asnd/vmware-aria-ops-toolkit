"""Tests for the KB article HTML parser."""

import json
from pathlib import Path

import pytest

from src.scraper.parser import (
    KBArticleParser,
    KBSection,
    ParsedKBArticle,
    parse_directory,
)


def test_parse_empty_html():
    """Test parsing empty or minimal HTML."""
    parser = KBArticleParser()

    # Empty HTML
    article = parser.parse_html("<html></html>", "00000")
    assert article.article_number == "00000"
    assert article.title == ""
    assert article.sections == []
    assert article.raw_text == ""

    # HTML with just tags
    html = "<html><head><title>Test</title></head><body></body></html>"
    article = parser.parse_html(html, "00001")
    assert article.article_number == "00001"
    assert article.title == "Test"


def test_extract_title():
    """Test title extraction from various sources."""
    parser = KBArticleParser()

    # From metadata (highest priority)
    article = parser.parse_html(
        "<html><title>Wrong Title</title></html>",
        "00000",
        metadata={"title": "Correct Title from Meta"}
    )
    assert article.title == "Correct Title from Meta"

    # From h1 tag
    article = parser.parse_html(
        "<html><body><h1>Main Heading</h1></body></html>",
        "00001"
    )
    assert article.title == "Main Heading"

    # From title tag (fallback)
    article = parser.parse_html(
        "<html><head><title>Page Title - VMware</title></head><body></body></html>",
        "00002"
    )
    assert article.title == "Page Title"  # VMware suffix stripped

    # Empty fallback
    article = parser.parse_html("<html></html>", "00003")
    assert article.title == ""


def test_find_content_area():
    """Test finding the main content area."""
    parser = KBArticleParser()

    # Article with explicit content div
    html = """
    <html>
    <body>
        <div class="sidebar">Sidebar</div>
        <div class="article-content">
            <h1>Main Title</h1>
            <p>This is the main content that should be found by the parser.</p>
        </div>
        <div class="footer">Footer</div>
    </body>
    </html>
    """
    article = parser.parse_html(html, "00000")
    assert "main content" in article.full_text.lower()

    # Fallback to largest div
    html = """
    <html>
    <body>
        <div class="nav">Nav</div>
        <div>
            <h2>Big Content</h2>
            <p>This is a lot of content. </p> * 100
        </div>
        <div class="small">Small</div>
    </body>
    </html>
    """.replace("* 100", "This is a lot of content. " * 100)
    article = parser.parse_html(html, "00001")
    assert "Big Content" in article.full_text


def test_extract_sections():
    """Test section extraction from KB article structure."""
    parser = KBArticleParser()

    html = """
    <html>
    <body>
        <div class="article-content">
            <h1>Article Title</h1>

            <h2>Symptoms</h2>
            <p>The system fails to boot.</p>
            <p>Error message: "Disk not found"</p>

            <h2>Cause</h2>
            <p>The storage controller driver is outdated.</p>

            <h2>Resolution</h2>
            <p>Update the storage controller to the latest version.</p>
            <p>Reboot the system after update.</p>

            <h2>Workaround</h2>
            <p>Use a different storage controller temporarily.</p>

            <h2>Additional Information</h2>
            <p>This affects ESXi 7.0 U3 and earlier.</p>
        </div>
    </body>
    </html>
    """

    article = parser.parse_html(html, "12345")

    assert len(article.sections) == 5

    # Check section headings and types
    assert article.sections[0].heading == "Symptoms"
    assert article.sections[0].section_type == "symptom"
    assert "fails to boot" in article.sections[0].content

    assert article.sections[1].heading == "Cause"
    assert article.sections[1].section_type == "cause"
    assert "storage controller driver" in article.sections[1].content

    assert article.sections[2].heading == "Resolution"
    assert article.sections[2].section_type == "resolution"
    assert "Update the storage controller" in article.sections[2].content

    assert article.sections[3].heading == "Workaround"
    assert article.sections[3].section_type == "workaround"
    assert "different storage controller" in article.sections[3].content

    assert article.sections[4].heading == "Additional Information"
    assert article.sections[4].section_type == "additional_info"
    assert "ESXi 7.0 U3" in article.sections[4].content


def test_extract_sections_with_bold_headings():
    """Test section extraction when headings use bold tags."""
    parser = KBArticleParser()

    html = """
    <html>
    <body>
        <div class="article-content">
            <h1>Article Title</h1>

            <strong>Symptoms:</strong>
            <p>The virtual machine crashes randomly.</p>

            <b>Cause:</b>
            <p>Memory corruption in the hypervisor.</p>

            <h3>Resolution</h3>
            <p>Apply patch ESXi70U3c-1234567.</p>
        </div>
    </body>
    </html>
    """

    article = parser.parse_html(html, "54321")

    assert len(article.sections) == 3

    assert article.sections[0].heading == "Symptoms"
    assert article.sections[0].section_type == "symptom"
    assert "virtual machine crashes" in article.sections[0].content

    assert article.sections[1].heading == "Cause"
    assert article.sections[1].section_type == "cause"
    assert "Memory corruption" in article.sections[1].content

    assert article.sections[2].heading == "Resolution"
    assert article.sections[2].section_type == "resolution"
    assert "patch ESXi70U3c" in article.sections[2].content


def test_extract_raw_text():
    """Test raw text extraction cleaning scripts and styles."""
    parser = KBArticleParser()

    html = """
    <html>
    <body>
        <script>
            console.log("This should be removed");
            var tracking = "remove me too";
        </script>
        <style>
            .hidden { display: none; }
            body { font-family: sans-serif; }
        </style>
        <nav>Navigation menu</nav>
        <footer>Footer links</footer>
        <div class="content">
            <h1>Visible Title</h1>
            <p>This is the visible content.</p>
        </div>
    </body>
    </html>
    """

    article = parser.parse_html(html, "99999")

    # Scripts, styles, nav, footer should be removed
    assert "console.log" not in article.raw_text
    assert "tracking" not in article.raw_text
    assert "display: none" not in article.raw_text
    assert "Navigation menu" not in article.raw_text
    assert "Footer links" not in article.raw_text

    # Visible content should remain
    assert "Visible Title" in article.raw_text
    assert "visible content" in article.raw_text


def test_extract_product_info():
    """Test product and version extraction."""
    parser = KBArticleParser()

    # From metadata
    article = parser.parse_html(
        "<html></html>",
        "00000",
        metadata={"product": "vSphere", "version": "8.0 U2"}
    )
    assert article.product == "vSphere"
    assert article.version == "8.0 U2"

    # From meta tag (using content attribute)
    html = '''
    <html>
    <head>
        <meta name="product" content="NSX-T">
        <meta name="version" content="3.2.1">
    </head>
    <body></body>
    </html>
    '''
    article = parser.parse_html(html, "00001")
    assert article.product == "NSX-T"
    assert article.version == "3.2.1"

    # From text content with product-related class
    html = """
    <html>
    <body>
        <div class="product-info">
            <span class="product-name">VMware vSphere</span>
        </div>
        <div class="version-info">7.0 Update 3</div>
        <div class="article-content">
            <h1>Article</h1>
            <p>Content about the issue</p>
        </div>
    </body>
    </html>
    """
    article = parser.parse_html(html, "00002")
    assert "vSphere" in article.product
    assert "7.0" in article.version


def test_extract_date():
    """Test date extraction."""
    parser = KBArticleParser()

    # From metadata
    article = parser.parse_html(
        "<html></html>",
        "00000",
        metadata={"last_updated": "2024-01-15"}
    )
    assert article.last_updated == "2024-01-15"

    # From meta tag
    html = '''
    <html>
    <head>
        <meta name="last-modified" content="2024-03-20T10:30:00Z">
    </head>
    <body></body>
    </html>
    '''
    article = parser.parse_html(html, "00001")
    assert article.last_updated == "2024-03-20T10:30:00Z"

    # From visible element
    html = """
    <html>
    <body>
        <div class="article-meta">
            <span class="date">Last Updated: 2024-05-01</span>
        </div>
    </body>
    </html>
    """
    article = parser.parse_html(html, "00002")
    assert article.last_updated == "2024-05-01"


def test_extract_related_articles():
    """Test extraction of related article links."""
    parser = KBArticleParser()

    html = """
    <html>
    <body>
        <div class="article-content">
            <h1>Article</h1>
            <p>See also:</p>
            <ul>
                <li><a href="/external/article?articleNumber=111111">Related KB 111111</a></li>
                <li><a href="/external/article/222222">Related KB 222222</a></li>
                <li><a href="https://example.com">External link</a></li>
                <li><a href="/internal/page">Internal page</a></li>
            </ul>
            <p>Also check: KB333333 for more details.</p>
        </div>
    </body>
    </html>
    """

    article = parser.parse_html(html, "00000")

    # Should find the KB article numbers
    assert "111111" in article.related_articles
    assert "222222" in article.related_articles
    assert "333333" in article.related_articles  # From text

    # Should not include non-KB links
    assert "example.com" not in article.related_articles
    assert "internal/page" not in article.related_articles

    # Should be deduplicated and limited
    assert len(article.related_articles) <= 20


def test_extract_tags():
    """Test tag extraction."""
    parser = KBArticleParser()

    html = """
    <html>
    <head>
        <meta name="keywords" content="vsphere, storage, iscsi, performance">
    </head>
    <body>
        <div class="article-content">
            <h1>Article</h1>
            <p>Tags: <span class="tag">vmware</span> <span class="tag">esxi</span></p>
            <div class="tags">
                <span class="label">storage</span>
                <span class="label">networking</span>
            </div>
        </div>
    </body>
    </html>
    """

    article = parser.parse_html(html, "00000")

    # Should collect tags from various sources
    assert "vsphere" in article.tags
    assert "storage" in article.tags
    assert "iscsi" in article.tags
    assert "performance" in article.tags
    assert "vmware" in article.tags
    assert "esxi" in article.tags
    assert "networking" in article.tags

    # Should be deduplicated and reasonably sized
    assert len(article.tags) <= 20


def test_full_text_property():
    """Test the full_text property."""
    # When sections exist, full_text should combine them
    article = ParsedKBArticle(
        article_number="11111",
        title="Test",
        sections=[
            KBSection("Symptoms", "System fails", "symptom"),
            KBSection("Cause", "Bad driver", "cause"),
            KBSection("Resolution", "Update driver", "resolution"),
        ]
    )

    expected = "## Symptoms\nSystem fails\n\n## Cause\nBad driver\n\n## Resolution\nUpdate driver"
    assert article.full_text == expected

    # When no sections, fallback to raw_text
    article = ParsedKBArticle(
        article_number="22222",
        title="Test2",
        raw_text="This is the raw content.",
        sections=[]
    )
    assert article.full_text == "This is the raw content."


def test_to_dict():
    """Test serialization to dictionary."""
    article = ParsedKBArticle(
        article_number="12345",
        title="Test Article",
        url="https://kb.example.com/article/12345",
        product="vSphere",
        version="8.0",
        last_updated="2024-01-01",
        sections=[
            KBSection("Symptoms", "Problem here", "symptom"),
            KBSection("Resolution", "Fix it", "resolution"),
        ],
        raw_text="Fallback text",
        related_articles=["11111", "22222"],
        tags=["vmware", "storage"]
    )

    data = article.to_dict()

    assert data["article_number"] == "12345"
    assert data["title"] == "Test Article"
    assert data["url"] == "https://kb.example.com/article/12345"
    assert data["product"] == "vSphere"
    assert data["version"] == "8.0"
    assert data["last_updated"] == "2024-01-01"
    assert len(data["sections"]) == 2
    assert data["sections"][0]["heading"] == "Symptoms"
    assert data["sections"][0]["content"] == "Problem here"
    assert data["sections"][0]["section_type"] == "symptom"
    assert data["raw_text"] == "Fallback text"
    assert data["related_articles"] == ["11111", "22222"]
    assert data["tags"] == ["vmware", "storage"]


def test_parse_directory_empty(tmp_path: Path):
    """Test parsing an empty directory."""
    articles = parse_directory(tmp_path)
    assert articles == []


def test_parse_directory_with_files(tmp_path: Path):
    """Test parsing directory with HTML files."""
    # Create test HTML files
    (tmp_path / "11111.html").write_text("""
    <html>
    <head><title>Test Article 1</title></head>
    <body>
        <h1>Test Article 1</h1>
        <div class="article-content">
            <h2>Symptoms</h2>
            <p>Test symptom</p>
        </div>
    </body>
    </html>
    """)

    (tmp_path / "22222.html").write_text("""
    <html>
    <head><title>Test Article 2</title></head>
    <body>
        <h1>Test Article 2</h1>
        <div class="article-content">
            <h2>Cause</h2>
            <p>Test cause</p>
        </div>
    </body>
    </html>
    """)

    # Create a non-HTML file (should be ignored)
    (tmp_path / "readme.txt").write_text("Not an article")

    articles = parse_directory(tmp_path)

    assert len(articles) == 2

    # Check first article
    article1 = next(a for a in articles if a.article_number == "11111")
    assert article1.title == "Test Article 1"
    assert len(article1.sections) == 1
    assert article1.sections[0].heading == "Symptoms"
    assert "Test symptom" in article1.sections[0].content

    # Check second article
    article2 = next(a for a in articles if a.article_number == "22222")
    assert article2.title == "Test Article 2"
    assert len(article2.sections) == 1
    assert article2.sections[0].heading == "Cause"
    assert "Test cause" in article2.sections[0].content


def test_parse_file_with_metadata_sidecar(tmp_path: Path):
    """Test parse_file loads metadata from sidecar JSON."""
    html_file = tmp_path / "12345.html"
    html_file.write_text("<html><body><h1>Test</h1></body></html>")

    meta_file = tmp_path / "12345.meta.json"
    meta_file.write_text(json.dumps({
        "title": "Sidecar Title",
        "url": "https://kb.example.com/article/12345",
        "product": "vSphere",
        "last_updated": "2024-01-01",
    }))

    parser = KBArticleParser()
    article = parser.parse_file(html_file)

    assert article.article_number == "12345"
    assert article.title == "Sidecar Title"  # from metadata
    assert article.url == "https://kb.example.com/article/12345"
    assert article.product == "vSphere"
    assert article.last_updated == "2024-01-01"


def test_parse_file_with_corrupted_metadata(tmp_path: Path, caplog):
    """Test parse_file handles corrupted metadata gracefully."""
    html_file = tmp_path / "12345.html"
    html_file.write_text("<html><body><h1>Test</h1></body></html>")

    meta_file = tmp_path / "12345.meta.json"
    meta_file.write_text("{invalid json")

    parser = KBArticleParser()
    article = parser.parse_file(html_file)

    assert article.article_number == "12345"
    assert article.title == "Test"  # from HTML, not corrupted metadata
    assert "Failed to parse metadata" in caplog.text


def test_parse_file_rejects_oversized_html(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Oversized files should be rejected before reading into memory."""
    html_file = tmp_path / "12345.html"
    html_file.write_text("<html>oversized</html>")
    monkeypatch.setattr("src.scraper.parser.MAX_HTML_FILE_BYTES", 10)

    parser = KBArticleParser()
    with pytest.raises(ValueError, match="too large to parse safely"):
        parser.parse_file(html_file)


def test_parse_directory_mixed_valid_invalid(tmp_path: Path, caplog):
    """Test parse_directory with mix of valid and invalid HTML files."""
    # Valid HTML
    (tmp_path / "11111.html").write_text(
        "<html><body><h1>Valid</h1><div class='article-content'>"
        "<h2>Symptoms</h2><p>Content here.</p></div></body></html>"
    )
    # Invalid HTML (malformed)
    (tmp_path / "22222.html").write_text("<not html at all>")

    articles = parse_directory(tmp_path)

    assert len(articles) == 2  # Both files parsed (even malformed)
    assert articles[0].article_number == "11111"


def test_classify_section_all_mappings():
    """Test all known section type mappings."""
    parser = KBArticleParser()

    mappings = {
        "symptoms": "symptom",
        "Symptom": "symptom",
        "cause": "cause",
        "Root Cause": "cause",
        "resolution": "resolution",
        "Solution": "resolution",
        "workaround": "workaround",
        "Additional Information": "additional_info",
        "More Information": "additional_info",
        "purpose": "purpose",
        "details": "details",
        "environment": "environment",
        "prerequisites": "prerequisites",
        "procedure": "procedure",
        "Steps": "procedure",
        "Unknown Section": "general",
    }

    for heading, expected_type in mappings.items():
        assert parser._classify_section(heading) == expected_type, f"Failed for: {heading}"


def test_find_content_area_returns_none():
    """Test _find_content_area returns None when no content found."""
    parser = KBArticleParser()

    html = "<html><body><div>tiny</div></body></html>"
    article = parser.parse_html(html, "00000")

    # Should fallback to soup, not crash
    assert article.article_number == "00000"
