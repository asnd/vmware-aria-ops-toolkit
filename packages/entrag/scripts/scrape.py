"""CLI script for scraping Broadcom/VMware KB articles.

Usage:
    python -m scripts.scrape --query "vsphere" --product "vSphere" --max 100
    python -m scripts.scrape --article-numbers 12345,67890
"""

import asyncio
import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from src.config import get_settings
from src.scraper.broadcom_kb import BroadcomKBScraper, KBArticleMeta
from src.scraper.parser import parse_directory

console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging with rich handler."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


@click.group()
def cli() -> None:
    """EntRAG KB Article Scraper - Download and parse Broadcom/VMware KB articles."""


@cli.command()
@click.option("--query", "-q", default="vmware", help="Search query for KB articles.")
@click.option("--product", "-p", default=None, help="Filter by product (vSphere, NSX, vSAN, etc.).")
@click.option(
    "--max", "-m", "max_articles", default=None, type=int, help="Max articles to download."
)
@click.option("--output", "-o", default=None, type=click.Path(), help="Output directory.")
@click.option(
    "--auth", is_flag=True, default=False,
    help="Enable authenticated scraping (requires BROADCOM_USERNAME/PASSWORD in .env).",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
def search(
    query: str,
    product: str | None,
    max_articles: int | None,
    output: str | None,
    auth: bool,
    verbose: bool,
) -> None:
    """Search and download KB articles from Broadcom support portal.

    By default, only publicly accessible articles are scraped.
    Use --auth to enable authenticated access (may have legal implications).
    """
    setup_logging(verbose)
    settings = get_settings()

    output_dir = Path(output) if output else settings.scraper_output_dir

    console.print("\n[bold]EntRAG KB Scraper[/bold]")
    console.print("  Mode: %s", "authenticated" if auth else "public (default)")
    console.print("  Query: %s", query)
    console.print("  Product filter: %s", product or "all")
    console.print("  Max articles: %s", max_articles or settings.scraper_max_articles)
    console.print("  Output: %s", output_dir)
    if not auth:
        console.print("  [dim]Tip: Use --auth to access restricted articles[/dim]")
    console.print()

    asyncio.run(
        _run_scrape(
            query=query,
            product_filter=product,
            max_articles=max_articles,
            output_dir=output_dir,
            use_auth=auth,
        )
    )


async def _run_scrape(
    query: str,
    product_filter: str | None,
    max_articles: int | None,
    output_dir: Path,
    use_auth: bool = False,
) -> None:
    """Run the scraping pipeline."""
    paths: list[Path] = []
    async with BroadcomKBScraper(
        output_dir=output_dir,
        max_articles=max_articles or get_settings().scraper_max_articles,
        use_auth=use_auth,
    ) as scraper:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Scraping KB articles...", total=None)

            paths = await scraper.scrape(query=query, product_filter=product_filter)

            progress.update(task, description=f"Downloaded {len(paths)} articles")

    # Print summary
    console.print("\n[green]Done![/green] Downloaded %d articles to %s", len(paths), output_dir)

    if scraper.state.failed:
        console.print(
            f"[yellow]Warning:[/yellow] {len(scraper.state.failed)} articles failed to download."
        )


@cli.command()
@click.option(
    "--numbers", "-n",
    required=True,
    help="Comma-separated article numbers to download directly.",
)
@click.option("--output", "-o", default=None, type=click.Path(), help="Output directory.")
@click.option(
    "--auth", is_flag=True, default=False,
    help="Enable authenticated scraping (requires BROADCOM_USERNAME/PASSWORD in .env).",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
def fetch(numbers: str, output: str | None, auth: bool, verbose: bool) -> None:
    """Download specific KB articles by their article numbers.

    By default, fetches only publicly accessible articles.
    Use --auth to enable authenticated access.
    """
    setup_logging(verbose)
    settings = get_settings()

    article_numbers = [n.strip() for n in numbers.split(",") if n.strip()]
    output_dir = Path(output) if output else settings.scraper_output_dir

    mode = "authenticated" if auth else "public"
    console.print("\n[bold]Fetching %d articles (%s mode)[/bold]", len(article_numbers), mode)
    asyncio.run(_run_fetch(article_numbers, output_dir, use_auth=auth))


async def _run_fetch(article_numbers: list[str], output_dir: Path, use_auth: bool = False) -> None:
    """Fetch specific articles by number."""
    from src.scraper.broadcom_kb import BROADCOM_KB_ARTICLE_BASE

    async with BroadcomKBScraper(output_dir=output_dir, use_auth=use_auth) as scraper:
        if use_auth:
            await scraper.authenticate()

        for num in article_numbers:
            meta = KBArticleMeta(
                article_number=num,
                title="",
                url=f"{BROADCOM_KB_ARTICLE_BASE}/{num}",
            )
            try:
                path = await scraper.download_article(meta)
                if path:
                    console.print("  [green]OK[/green] KB%s → %s", num, path.name)
            except Exception as e:
                console.print("  [red]FAIL[/red] KB%s: %s", num, e)


@cli.command()
@click.option(
    "--input", "-i", "input_dir",
    default=None,
    type=click.Path(exists=True),
    help="Directory containing downloaded HTML files.",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
def parse(input_dir: str | None, verbose: bool) -> None:
    """Parse downloaded KB articles and show summary."""
    setup_logging(verbose)
    settings = get_settings()

    directory = Path(input_dir) if input_dir else settings.scraper_output_dir

    if not directory.exists():
        console.print(f"[red]Error:[/red] Directory {directory} does not exist.")
        sys.exit(1)

    articles = parse_directory(directory)

    if not articles:
        console.print("[yellow]No articles found to parse.[/yellow]")
        return

    # Display summary table
    table = Table(title=f"Parsed KB Articles ({len(articles)} total)")
    table.add_column("Article #", style="cyan")
    table.add_column("Title", max_width=50)
    table.add_column("Product", style="green")
    table.add_column("Sections", justify="right")
    table.add_column("Text Length", justify="right")

    for article in articles[:50]:  # Show first 50
        table.add_row(
            article.article_number,
            article.title[:50],
            article.product or "-",
            str(len(article.sections)),
            str(len(article.full_text)),
        )

    console.print(table)

    # Section type statistics
    section_types: dict[str, int] = {}
    for article in articles:
        for section in article.sections:
            section_types[section.section_type] = (
                section_types.get(section.section_type, 0) + 1
            )

    if section_types:
        console.print("\n[bold]Section type distribution:[/bold]")
        for stype, count in sorted(section_types.items(), key=lambda x: x[1], reverse=True):
            console.print(f"  {stype}: {count}")


@cli.command()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
def status(verbose: bool) -> None:
    """Show scraper state and progress."""
    setup_logging(verbose)
    settings = get_settings()

    from src.scraper.broadcom_kb import ScraperState

    state_file = settings.scraper_output_dir / ".scraper_state.json"
    state = ScraperState.load(state_file)

    console.print("\n[bold]Scraper Status[/bold]")
    console.print(f"  Output directory: {settings.scraper_output_dir}")
    console.print(f"  Total articles found: {state.total_found}")
    console.print(f"  Downloaded: {len(state.downloaded)}")
    console.print(f"  Failed: {len(state.failed)}")

    if state.failed:
        console.print(f"\n  [yellow]Failed articles:[/yellow] {', '.join(sorted(state.failed))}")

    # Count actual files
    if settings.scraper_output_dir.exists():
        html_files = list(settings.scraper_output_dir.glob("*.html"))
        console.print(f"\n  HTML files on disk: {len(html_files)}")


def main() -> None:
    """Entry point for the scraper CLI."""
    cli()


if __name__ == "__main__":
    main()
