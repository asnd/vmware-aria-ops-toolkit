# EntRAG

EntRAG is a VMware/Broadcom knowledge-base assistant. It scrapes KB articles, parses them into structured sections, indexes them in LanceDB, and exposes a Chainlit chat where an LLM agent answers questions grounded in the indexed KB — with citations. Users can connect external MCP servers from the chat to extend the agent with extra tools.

## What is implemented

- Broadcom KB scraping with resumable state and checksum-based skip logic
- HTML parsing into structured sections such as Symptoms, Cause, and Resolution
- LanceDB-backed ingestion with metadata-preserving chunks
- Hybrid retrieval over the stored index, with lightweight reranking biased toward actionable sections
- An agentic LLM layer: the model calls a `kb_search` tool (and any connected MCP tools) and synthesises a cited answer
- A Chainlit chat UI with a native MCP button so users can connect MCP servers at runtime
- Pytest and Ruff coverage for config, scraping, parsing, retrieval, the agent loop, and container layout

## Current runtime behavior

The runtime is an agentic, retrieval-grounded chat:

1. The user asks a question in the Chainlit UI
2. The LLM is offered a `kb_search` tool plus any tools from connected MCP servers
3. For KB questions it calls `kb_search`, which runs LiteLLM query embedding → LanceDB hybrid search → reranking
4. Tool results are fed back and the model synthesises a cited answer, emitted progressively

This keeps responses grounded in indexed content while letting the agent reach beyond the KB through user-connected MCP tools.

## Architecture

### Runtime split

| Component | Responsibility |
| --- | --- |
| `rag-app` | Chainlit chat UI, agentic LLM, and retrieval |
| `litellm` | Model proxy for embeddings and optional generation |
| `scraper` | One-shot article collection job |
| `ingest` | One-shot parsing + embedding + indexing job |
| `litellm-local` | Optional isolated local-model sidecar |

### Data flow

```text
Broadcom KB search/download
  -> ./data/raw/*.html
  -> parser extracts sections + metadata
  -> ingestion chunks and embeds content
  -> LanceDB stores vectors + metadata
  -> retrieval queries LanceDB and reranks matches
  -> LLM agent (kb_search + connected MCP tools) synthesises a cited answer
  -> Chainlit streams the answer to the user
```

## Repository layout

```text
src/
  chat_app.py           Chainlit entrypoint (UI + MCP connect/disconnect handlers)
  agent.py              Agentic tool-calling loop (kb_search + MCP tools)
  config.py             Settings and runtime resolution helpers
  ingestion/            Parsing -> chunking -> LanceDB indexing
  retrieval/            Hybrid search and reranking
  scraper/              Broadcom KB scraper and parser
  mcp_server/           EntRAG-as-MCP-server (rag_query/scrape/ingest tools)
scripts/
  scrape.py             CLI wrapper for scraping
  ingest.py             CLI wrapper for ingestion
tests/                  Automated coverage
docs/                   Deeper notes on embeddings and reranking
```

## Quick start

### 1. Configure the environment

```bash
cp .env.example .env
```

At minimum set:

- `OPENAI_API_KEY`
- `LITELLM_API_KEY`
- optionally `LITELLM_MASTER_KEY`

The app now validates `LITELLM_API_KEY` before ingestion or retrieval starts.

### 2. Start the always-on services

```bash
docker compose up -d
```

### 3. Scrape articles

```bash
docker compose -f compose.yaml -f compose.jobs.yaml run --rm scraper search \
  --query "ESXi boot failure" \
  --max 25
```

### 4. Build the index

```bash
docker compose -f compose.yaml -f compose.jobs.yaml run --rm ingest \
  --source ./data/raw \
  --reset
```

### 5. Query the app

- Chainlit UI: http://localhost:7860
- LiteLLM health/API proxy: http://localhost:4000

Ask product, version, error, or symptom-specific questions such as:

- `How do I fix an ESXi host boot failure after a patch?`
- `What are the symptoms of vCenter certificate issues?`
- `Why does NSX Manager fail to start after upgrade?`

To extend the agent, click the **🔌 MCP** button in the chat input and connect an MCP
server (SSE, streamable-HTTP, or a stdio command). Its tools become available to the
assistant for the rest of the session — including EntRAG's own `entrag-mcp` server.

## CLI usage

### Scrape

```bash
python -m scripts.scrape search --query "vmware" --max 20
python -m scripts.scrape fetch --numbers 10001,10002
python -m scripts.scrape parse --input ./data/raw
python -m scripts.scrape status
```

### Ingest

```bash
python -m scripts.ingest --source ./data/raw --reset
python -m scripts.ingest --local
```

`--local` switches the ingestion command to the local LiteLLM endpoint/model aliases instead of mutating process environment variables. Ingestion validates `LITELLM_API_KEY` before building embeddings and uses the resolved embedding model/base URL, so `EMBEDDING_PROVIDER=local` consistently selects the local LiteLLM aliases.

## Configuration reference

| Variable | Default | Purpose |
| --- | --- | --- |
| `LITELLM_BASE_URL` | `http://localhost:4000` | LiteLLM endpoint used by the app |
| `LITELLM_API_KEY` | placeholder | Auth token used by the app to call LiteLLM |
| `LITELLM_MASTER_KEY` | `sk-entrag-dev` in example only | LiteLLM proxy master key |
| `LITELLM_MODEL` | `gpt-4o` | Optional generation model |
| `LITELLM_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model alias |
| `LANCEDB_PATH` | `./data/lancedb` | Vector store path |
| `SCRAPER_OUTPUT_DIR` | `./data/raw` | Downloaded article directory |
| `RETRIEVAL_SIMILARITY_TOP_K` | `10` | Candidate pool size from LanceDB |
| `RETRIEVAL_HYBRID_ALPHA` | `0.7` | LanceDB hybrid weighting |
| `RERANKER_TOP_N` | `5` | Final number of displayed matches |

## Security notes

- Do not keep real LiteLLM keys in tracked config files
- LiteLLM master keys are now sourced from environment instead of hardcoded in YAML
- Authenticated scraping is opt-in and should only be used when you understand the legal and operational implications
- Placeholder API keys are rejected before ingestion and retrieval start network calls
- HTML files larger than 10 MiB are skipped during parsing to prevent accidental memory exhaustion from corrupted or unexpected scraper output

## Retrieval quality notes

- Section metadata is stored with each chunk, which lets reranking prefer `resolution` content for fix-oriented questions and `cause` content for root-cause questions
- Hybrid search uses LanceDB first and falls back to vector-only mode if hybrid capabilities are unavailable
- Ingestion opens LanceDB in append mode unless `--reset` is passed, preventing accidental index replacement during normal updates

## Development

### Local checks

```bash
python -m ruff check src/ scripts/ tests/
python -m pytest tests/ -v --tb=short
```

### Test coverage

The test suite covers:

- configuration validation and runtime helpers
- scraper state, search, download, and auth behavior
- parser extraction and serialization
- retrieval ranking and answer formatting
- the agentic tool-calling loop and MCP tool wiring
- container and compose layout expectations

## Additional guides

- [docs/embedding.md](docs/embedding.md)
- [docs/reranking.md](docs/reranking.md)
