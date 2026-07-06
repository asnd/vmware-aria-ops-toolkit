"""CLI script for document ingestion into the vector store.

Usage:
    python -m scripts.ingest --source data/raw/ --reset
    python -m scripts.ingest --local  # Force local embeddings
"""

import logging
import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.config import get_settings

console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )


@click.command()
@click.option(
    "--source", "-s",
    default=None,
    type=click.Path(exists=True),
    help="Source directory with HTML files.",
)
@click.option("--reset", is_flag=True, help="Reset vector store before ingestion.")
@click.option(
    "--local", is_flag=True,
    help="Force local embedding model (overrides EMBEDDING_PROVIDER).",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
def main(source: str | None, reset: bool, local: bool, verbose: bool) -> None:
    """Ingest KB articles into LanceDB vector store."""
    setup_logging(verbose)
    settings = get_settings()

    source_dir = Path(source) if source else settings.scraper_output_dir
    console.print("\n[bold]EntRAG — Document Ingestion[/bold]")
    console.print(f"  Source: {source_dir}")
    console.print(f"  LanceDB: {settings.lancedb_path}")
    console.print(f"  Embedding: {settings.embedding_provider}")
    if local:
        console.print("  [yellow]Forcing local embedding model[/yellow]")
    console.print()

    if local:
        os.environ["EMBEDDING_PROVIDER"] = "local"
        get_settings.cache_clear()

    from src.ingestion import ingest_directory

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Ingesting documents...", total=None)
        try:
            count = ingest_directory(source_dir, reset=reset)
            progress.update(task, description=f"Ingested {count} document chunks")
            console.print(f"\n[green]Done![/green] Ingested {count} document chunks into LanceDB.")
        except Exception as e:
            console.print(f"\n[red]Error:[/red] {e}")
            if verbose:
                console.print_exception()
            sys.exit(1)


if __name__ == "__main__":
    main()
