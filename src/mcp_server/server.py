"""EntRAG MCP Server — exposes KB retrieval, scraping, and ingestion as MCP tools.

Tools:
- rag_query: Search the indexed VMware/Broadcom KB and return cited excerpts
- scrape_status: Get current scraper state (downloaded, failed, disk files)
- trigger_scrape: Start a KB scrape job with optional query/product filter
- trigger_ingest: Ingest scraped articles into the vector store
- ingestion_status: Check LanceDB index health and document counts
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from src.config import get_settings

logger = logging.getLogger(__name__)


def _tool_definitions() -> list[Tool]:
    """Define the MCP tools exposed by EntRAG."""
    return [
        Tool(
            name="rag_query",
            description=(
                "Search the indexed VMware/Broadcom knowledge base using hybrid vector + "
                "keyword search. Returns the top matching KB excerpts with article citations, "
                "section types (Symptom, Cause, Resolution), and relevance scores."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "The search query (error message, product name, symptom, etc.)"
                        ),
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 5)",
                        "minimum": 1,
                        "maximum": 20,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="scrape_status",
            description=(
                "Get the current state of the KB scraper: total articles found, "
                "downloaded, failed, and HTML files on disk."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="trigger_scrape",
            description=(
                "Start a KB article scrape from the Broadcom support portal. "
                "This runs asynchronously and downloads articles to the data directory."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for KB articles (default: 'vmware')",
                    },
                    "product_filter": {
                        "type": "string",
                        "description": "Filter by product (vSphere, NSX, vSAN, etc.)",
                    },
                    "max_articles": {
                        "type": "integer",
                        "description": "Maximum articles to download",
                        "minimum": 1,
                        "maximum": 1000,
                    },
                },
            },
        ),
        Tool(
            name="trigger_ingest",
            description=(
                "Ingest scraped KB articles into the LanceDB vector store. "
                "Parses HTML, chunks text, generates embeddings, and indexes them. "
                "Use reset=true to rebuild the entire index from scratch."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "reset": {
                        "type": "boolean",
                        "description": "Wipe and rebuild the vector store (default: false)",
                    },
                    "source_dir": {
                        "type": "string",
                        "description": "Source directory with HTML files (default: data/raw)",
                    },
                },
            },
        ),
        Tool(
            name="ingestion_status",
            description=(
                "Check the health and status of the LanceDB vector store: "
                "whether the index exists, path, and approximate document count."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


async def _handle_rag_query(arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a RAG query against the indexed KB."""
    query = arguments.get("query", "").strip()
    if not query:
        return [TextContent(
            type="text",
            text="Error: 'query' parameter is required and non-empty.",
        )]

    top_k = arguments.get("top_k")

    try:
        from src.retrieval import RetrievalEngine

        engine = RetrievalEngine()
        results = engine.search(query, top_k=top_k)
    except FileNotFoundError as exc:
        return [TextContent(type="text", text=f"Index not available: {exc}")]
    except ValueError as exc:
        return [TextContent(type="text", text=f"Configuration error: {exc}")]
    except Exception as exc:
        logger.exception("RAG query failed")
        return [TextContent(type="text", text=f"Query failed: {exc}")]

    if not results:
        return [TextContent(
            type="text",
            text=(
                "No KB content matched that query. "
                "Ensure the index is populated (run trigger_ingest)."
            ),
        )]

    # Format results as structured JSON for machine consumption
    output = []
    for i, r in enumerate(results, 1):
        output.append({
            "rank": i,
            "score": round(r.score, 4),
            "article_number": r.article_number,
            "title": r.title,
            "url": r.url,
            "product": r.product,
            "section_type": r.section_type,
            "section_heading": r.section_heading,
            "excerpt": r.text[:500],
        })

    return [TextContent(type="text", text=json.dumps(output, indent=2))]


async def _handle_scrape_status(_arguments: dict[str, Any]) -> list[TextContent]:
    """Return current scraper state."""
    settings = get_settings()

    from src.scraper.broadcom_kb import ScraperState

    state_file = settings.scraper_output_dir / ".scraper_state.json"
    state = ScraperState.load(state_file)

    html_count = 0
    if settings.scraper_output_dir.exists():
        html_count = len(list(settings.scraper_output_dir.glob("*.html")))

    status = {
        "output_directory": str(settings.scraper_output_dir),
        "total_articles_found": state.total_found,
        "downloaded": len(state.downloaded),
        "failed": len(state.failed),
        "failed_articles": sorted(state.failed)[:20],  # Cap at 20 for readability
        "html_files_on_disk": html_count,
    }
    return [TextContent(type="text", text=json.dumps(status, indent=2))]


async def _handle_trigger_scrape(arguments: dict[str, Any]) -> list[TextContent]:
    """Trigger a scrape job."""
    settings = get_settings()
    query = arguments.get("query", "vmware")
    product_filter = arguments.get("product_filter")
    max_articles = arguments.get("max_articles", settings.scraper_max_articles)

    try:
        from src.scraper.broadcom_kb import BroadcomKBScraper

        async with BroadcomKBScraper(
            output_dir=settings.scraper_output_dir,
            max_articles=max_articles,
            use_auth=settings.scraper_use_auth,
        ) as scraper:
            paths = await scraper.scrape(query=query, product_filter=product_filter)

        result = {
            "status": "completed",
            "query": query,
            "product_filter": product_filter,
            "articles_downloaded": len(paths),
            "output_directory": str(settings.scraper_output_dir),
            "failed": len(scraper.state.failed),
        }
    except Exception as exc:
        logger.exception("Scrape failed")
        result = {"status": "error", "detail": str(exc)}

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def _handle_trigger_ingest(arguments: dict[str, Any]) -> list[TextContent]:
    """Trigger document ingestion into the vector store."""
    settings = get_settings()
    reset = arguments.get("reset", False)
    source_dir_str = arguments.get("source_dir")
    source_dir = Path(source_dir_str) if source_dir_str else settings.scraper_output_dir

    if not source_dir.exists():
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "detail": f"Source directory {source_dir} does not exist.",
            }),
        )]

    try:
        from src.ingestion import ingest_directory

        # Run in thread to avoid blocking the event loop (embedding is CPU-heavy)
        count = await asyncio.to_thread(ingest_directory, source_dir, reset)
        result = {
            "status": "completed",
            "chunks_ingested": count,
            "source_directory": str(source_dir),
            "reset": reset,
            "lancedb_path": str(settings.lancedb_path),
        }
    except Exception as exc:
        logger.exception("Ingestion failed")
        result = {"status": "error", "detail": str(exc)}

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def _handle_ingestion_status(_arguments: dict[str, Any]) -> list[TextContent]:
    """Check the LanceDB index status."""
    settings = get_settings()
    lancedb_path = Path(settings.lancedb_path)

    status: dict[str, Any] = {
        "lancedb_path": str(lancedb_path),
        "index_exists": lancedb_path.exists(),
    }

    if lancedb_path.exists():
        # Approximate size from directory contents
        total_size = sum(f.stat().st_size for f in lancedb_path.rglob("*") if f.is_file())
        status["index_size_mb"] = round(total_size / (1024 * 1024), 2)

        # Try to get table info from LanceDB
        try:
            import lancedb as ldb

            db = ldb.connect(str(lancedb_path))
            tables = db.table_names()
            status["tables"] = tables
            if tables:
                table = db.open_table(tables[0])
                status["row_count"] = table.count_rows()
        except Exception as exc:
            status["detail"] = f"Could not read LanceDB tables: {exc}"
    else:
        status["detail"] = "Index does not exist. Run trigger_ingest to create it."

    return [TextContent(type="text", text=json.dumps(status, indent=2))]


# Tool handler dispatch
_TOOL_HANDLERS: dict[str, Any] = {
    "rag_query": _handle_rag_query,
    "scrape_status": _handle_scrape_status,
    "trigger_scrape": _handle_trigger_scrape,
    "trigger_ingest": _handle_trigger_ingest,
    "ingestion_status": _handle_ingestion_status,
}


def create_server() -> Server:
    """Create and configure the EntRAG MCP server."""
    server = Server("entrag-mcp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return _tool_definitions()

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
        handler = _TOOL_HANDLERS.get(name)
        if handler is None:
            return [TextContent(
                type="text",
                text=f"Unknown tool: {name}. Available: {', '.join(_TOOL_HANDLERS)}",
            )]
        return await handler(arguments or {})

    return server
