# EntRAG — VMware/Broadcom KB Assistant

Ask questions about VMware/Broadcom products (vSphere, vCenter, ESXi, NSX, vSAN, …).
Answers are grounded in indexed Knowledge Base articles via hybrid vector + keyword
search, with citations back to KB article numbers.

## Tools

- **`kb_search`** — searches the indexed KB. The assistant calls it automatically.
- **MCP servers** — connect external tools with the 🔌 MCP button in the chat input.
  Connected tools become available to the assistant for the rest of the session.

> Tip: connect EntRAG's own MCP server (`entrag-mcp`) to expose scrape/ingest tools.
