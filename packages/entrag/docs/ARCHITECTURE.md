# EntRAG — Architecture

VMware/Broadcom Knowledge Base RAG (Retrieval-Augmented Generation) application.

## Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| **Orchestration** | LlamaIndex | Purpose-built for RAG, native LiteLLM integration |
| **LLM Gateway** | LiteLLM Proxy | Unified API for any model, `/v1/chat` + `/v1/embeddings` |
| **Vector DB** | LanceDB | File-based, hybrid search (vector + BM25 FTS), scales to 100k+ |
| **Frontend** | Chainlit | Agentic chat with native MCP client (connect MCP servers from the UI) |
| **Agent** | LiteLLM tool calling | `kb_search` + connected MCP tools, tool-calling loop |
| **Scraper** | httpx + BeautifulSoup | Async HTTP with rate limiting, public-first default |
| **Config** | pydantic-settings | Env/file config with validation |
| **CLI** | Click + Rich | Structured commands with progress bars |

## System Components

```
┌──────────────────────────────────────────────────────────┐
│                    compose.yaml                          │
│                                                          │
│  ┌────────────────────────┐  ┌────────────────────────┐ │
│  │    entrag-app :7860    │  │  entrag-litellm :4000  │ │
│  │                        │  │                        │ │
│  │  Chainlit chat + MCP   │  │  LiteLLM Proxy         │ │
│  │  agent (tool calling)  │──►  /v1/chat/completions │ │
│  │   kb_search + MCP tools│  │  /v1/embeddings        │ │
│  │  LlamaIndex Pipeline   │  │                        │ │
│  │  ┌──────────────────┐  │  └────────────────────────┘ │
│  │  │ HybridRetriever  │  │                              │
│  │  │  - vector (cosine)│  │                              │
│  │  │  - BM25 (keyword) │  │                              │
│  │  └────────┬─────────┘  │                              │
│  │           │             │                              │
│  │  ┌────────▼─────────┐  │                              │
│  │  │ LanceDB          │  │                              │
│  │  │ /app/data/lancedb│  │                              │
│  │  └──────────────────┘  │                              │
│  └────────────────────────┘                              │
└──────────────────────────────────────────────────────────┘

Offline pipeline:
  scripts/scrape.py  →  BroadcomKBScraper  →  data/raw/*.html
  scripts/scrape.py parse →  KBArticleParser  →  ParsedKBArticle[]
  scripts/ingest.py  →  Chunker → Embedder → LanceDB (Phase 3)
```

## Data Flow

### Phase 1 — Config
`src/config.py` — pydantic-settings reads `.env` + environment variables. All values validated with `Field(ge=..., le=...)` constraints. Password protected with `SecretStr`.

### Phase 2 — Scrape
1. `scripts/scrape.py search` → `BroadcomKBScraper.search_articles()` — paginated search
2. `BroadcomKBScraper.download_article()` — save HTML + `.meta.json` sidecar
3. `scripts/scrape.py parse` → `KBArticleParser.parse_file()` — extract sections, metadata
4. `ParsedKBArticle.to_dict()` — ready for ingestion

**Rate limiting**: One `asyncio.sleep(delay)` per search page. No duplicate delay per article.

**Authentication**: Public-only by default. `--auth` flag enables login. Playwright fallback available if installed (`pip install -e ".[playwright]"`).

### Phase 3 — Ingest (planned)
- Section-aware chunking (respects Symptom/Cause/Resolution structure)
- Embedding via LiteLLM `/v1/embeddings`
- Hybrid index in LanceDB (vector + full-text)

### Phase 4-5 — Retrieve & Serve
- Hybrid retrieval (vector cosine + BM25 keyword)
- Cross-encoder reranking (via LiteLLM or local sentence-transformers)
- Agentic synthesis: the LLM calls `kb_search` (and connected MCP tools) and writes a cited answer (`src/agent.py`)
- Chainlit chat UI with a native MCP button; `@cl.on_mcp_connect` registers user-connected MCP servers (`src/chat_app.py`)

### Phase 6 — Evaluate (planned)
- Ragas metrics: context relevancy, faithfulness, answer relevancy
- Golden Q&A test set

## Dependency Graph

```
entrag (base, ~800MB container)
├── llama-index-core          RAG abstractions
├── llama-index-llms-litellm  LLM calls via proxy
├── llama-index-embeddings-litellm  Embeddings via proxy
├── llama-index-vector-stores-lancedb  LanceDB connector
├── lancedb                   File-based vector store
│   ├── pylance               Native columnar engine
│   └── pyarrow               Apache Arrow (in-memory)
├── chainlit                  Agentic chat UI + native MCP client
├── httpx                     Async HTTP client
├── beautifulsoup4 + lxml     HTML parsing
├── pydantic-settings         Env/file config
├── click                     CLI framework
├── rich                      Terminal formatting
└── tenacity                  Retry logic

entrag[local] (optional, +2GB)
├── sentence-transformers     Local reranker (pulls torch)
└── llama-index-embeddings-huggingface  Local embeddings

entrag[playwright] (optional, +700MB)
├── playwright                Browser automation
└── llama-index-readers-web   Web page readers

entrag[eval] (optional)
└── ragas                     RAG evaluation metrics

entrag[dev]
├── ruff                      Linter
├── pytest + pytest-asyncio   Test runner
└── mypy                      Type checker
```

## Configuration

All settings in `.env` (see `.env.example`):

```bash
# LiteLLM proxy
LITELLM_BASE_URL=http://localhost:4000
LITELLM_API_KEY=sk-your-key

# Embedding provider: "litellm" or "local" (requires [local] extras)
EMBEDDING_PROVIDER=litellm

# Scraper (public-only by default)
SCRAPER_USE_AUTH=false
SCRAPER_MAX_ARTICLES=100
SCRAPER_DELAY_SECONDS=3.0

# Reranker (via LiteLLM or local)
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
```

## CLI Commands

```bash
# Scrape public KB articles
python -m scripts.scrape search -q "vsphere" -p vSphere --max 100

# Fetch specific articles by ID
python -m scripts.scrape fetch -n 12345,67890

# Enable authenticated scraping (requires BROADCOM_USERNAME/PASSWORD)
python -m scripts.scrape search --auth

# Parse downloaded articles
python -m scripts.scrape parse

# Check scraper progress
python -m scripts.scrape status

# Ingest into vector store (Phase 3)
python -m scripts.ingest run --source data/raw --reset

# Start RAG app (Chainlit)
chainlit run src/chat_app.py
# or the console script
entrag-serve
```

## Container Build

```bash
# Build (multi-stage, ~800MB)
podman build --format docker -t entrag:dev .

# Run
podman run --rm -p 7860:7860 --env-file .env entrag:dev

# Full stack with LiteLLM
podman compose up
```

## Test Coverage

```
tests/config/             5 tests   Settings defaults, env, file, validation, caching
tests/scraper/           14 tests   Scraper state, auth, search, download, pipeline
tests/scraper/           14 tests   Parser: title, sections, metadata, text, tags
tests/scripts/           16 tests   CLI: scrape search/fetch/parse/status, ingest
─────────────────────────────────────────────────────────────
Total:                  49 tests
```
