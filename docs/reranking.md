# Reranking in EntRAG

## Purpose

Hybrid retrieval gets a strong candidate pool, but the final answer quality still depends on ordering the candidates correctly.

EntRAG currently uses a lightweight reranker that is fast, deterministic, and grounded in KB structure.

## What it reranks on

For each candidate chunk, the reranker considers:

- the LanceDB retrieval score
- exact token overlap with the query
- title and section-heading overlap
- section intent boosts

## Section intent boosts

The reranker prefers:

- `resolution` and `workaround` sections for fix-oriented questions
- `cause` sections for root-cause questions
- `symptom` sections for issue-description questions

This is useful for KB content because Broadcom/VMware articles are often structured around those section names.

## Why this helps

Two chunks may both mention `ESXi boot failure`, but the one that actually contains the fix should rank above a symptom-only description when the user asks `how do I fix`.

## Current trade-off

The reranker is intentionally lightweight:

- no extra heavyweight model dependency in the base app image
- fully testable with deterministic fixtures
- easy to inspect and tune

If you later add a cross-encoder behind LiteLLM or another service, the retrieval module is the right integration point for a stronger second-pass scorer.

## Tuning levers

- `RETRIEVAL_SIMILARITY_TOP_K` controls how many candidates are pulled from LanceDB
- `RETRIEVAL_HYBRID_ALPHA` controls the vector/keyword blend at retrieval time
- `RERANKER_TOP_N` controls how many reranked results are shown in the UI

## Practical guidance

- increase `SIMILARITY_TOP_K` before making reranking more complex
- keep product/version/error terms in the query when possible
- inspect returned citations to see whether the parser and chunker preserved the right context
