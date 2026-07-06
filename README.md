# vmware-aria-ops-toolkit

VMware Aria Operations + NSX-T + AVI infrastructure toolkit. A Python uv workspace
containing five packages that form a layered AI-assisted operations platform.

## Architecture

```
        ai-ops-agent (LangGraph: collect→correlate→enrich→analyze→remediate)
             │ MCP                  │ MCP
             ▼                      ▼
        ariaops-mcp              entrag (KB RAG + MCP server)
             │ REST
             ▼
        VMware Aria Ops

        nsx-avi-gateway (FastAPI) → NSX-T/AVI sites (mutations, audit, allowlist)
        nsxt-robot (Robot FW)     → NSX-T (control+data plane validation via bbprobe)
```

## Packages

| Package | Purpose |
|---|---|
| `packages/ariaops-mcp/` | MCP data server for VMware Aria Operations (on-prem) |
| `packages/ai-ops-agent/` | LangGraph AI ops agent — predictive failure, root-cause, remediation |
| `packages/entrag/` | Enterprise RAG — KB retrieval, citations, MCP server |
| `packages/nsxt-robot/` | Robot Framework library for NSX-T 4.x testing (also published as `robotframework-nsxt` on PyPI) |
| `packages/nsx-avi-gateway/` | FastAPI multi-site gateway for NSX-T + AVI Load Balancer management |

## Quick start

```bash
uv sync
uv run --project packages/ariaops-mcp ariaops-mcp serve
```

## Development

```bash
uv run ruff check .
uv run mypy packages/
uv run pytest
```

## License

MIT
