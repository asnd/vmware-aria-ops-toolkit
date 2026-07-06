# Lean application image (~500MB)
# Contains: Chainlit UI, LlamaIndex, LanceDB, scraping tools
# Does NOT contain: PyTorch, sentence-transformers, Playwright

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml .

RUN uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv pip install -e ".[dev]"

COPY src/ src/
COPY scripts/ scripts/
COPY tests/ tests/
COPY .chainlit/ .chainlit/
COPY chainlit.md .

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

EXPOSE 7860

VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:7860/')" || exit 1

CMD ["chainlit", "run", "src/chat_app.py", "--host", "0.0.0.0", "--port", "7860", "--headless"]
