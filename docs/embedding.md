# Embeddings in EntRAG

## Purpose

Embeddings turn KB chunks and user queries into vectors so LanceDB can do semantic search.

## Current pipeline

1. Parsed KB sections are turned into chunkable documents
2. LiteLLM serves the configured embedding model
3. LanceDB stores vectors plus article metadata
4. Retrieval generates a query embedding and performs hybrid search

## Why this matters

Keyword search alone misses semantic matches such as:

- `host won't boot`
- `ESXi startup failure`
- `server fails after firmware update`

Embeddings help treat those as related even when the wording differs.

## Runtime model selection

EntRAG always talks to LiteLLM at runtime.

### Remote default

```bash
LITELLM_BASE_URL=http://litellm:4000
LITELLM_EMBEDDING_MODEL=text-embedding-3-small
```

### Local alias mode

```bash
python -m scripts.ingest --local
```

That switches ingestion to the local LiteLLM endpoint/model alias resolution instead of editing environment variables in-process.

## Metadata stored with each chunk

Each indexed chunk carries:

- article number
- title
- URL
- product
- version
- last updated
- section type
- section heading

That metadata is reused during reranking and citation formatting.

## Operational guidance

- Re-ingest after changing embedding models
- Use `--reset` when rebuilding the full index from scratch
- Keep `RETRIEVAL_SIMILARITY_TOP_K` large enough to give reranking useful candidates
- Validate LiteLLM credentials before large ingestion runs
