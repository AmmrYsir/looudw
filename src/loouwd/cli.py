import asyncio
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import uvicorn

from loouwd.core.config import settings
from loouwd.core.context import SourceExecutionContext, default_context
from loouwd import adapters  # Ensures auto-registration
from loouwd.core.registry import registry
from loouwd.core.schemas import SourceBrowseRequest
from loouwd.core.cache import global_cache

app = typer.Typer(
    name="loouwd",
    help="CLI Controller for loouwd FastAPI Source Adapter Registry",
    add_completion=False,
)

sources_app = typer.Typer(help="Manage and inspect source adapters")
unified_app = typer.Typer(help="Unified multi-source search and aggregation operations")
cache_app = typer.Typer(help="Manage caching layer")

app.add_typer(sources_app, name="sources")
app.add_typer(unified_app, name="unified")
app.add_typer(cache_app, name="cache")

console = Console()


@app.command()
def serve(
    host: str = typer.Option(settings.HOST, "--host", "-h", help="Bind host address"),
    port: int = typer.Option(settings.PORT, "--port", "-p", help="Bind port number"),
    reload: bool = typer.Option(settings.DEBUG, "--reload", "-r", help="Enable auto-reload"),
):
    """Start the FastAPI Uvicorn web server."""
    console.print(
        Panel.fit(
            f"[bold green]Starting loouwd API Server[/bold green]\n"
            f"Host: [cyan]http://{host}:{port}[/cyan]\n"
            f"Active Adapters: [yellow]{len(registry.list_sources())}[/yellow]\n"
            f"Docs URL: [cyan]http://{host}:{port}/docs[/cyan]",
            title="loouwd CLI",
        )
    )
    uvicorn.run("loouwd.main:app", host=host, port=port, reload=reload)


@sources_app.command("list")
def list_sources():
    """List all registered source adapters."""
    table = Table(title="Registered Source Adapters", show_header=True, header_style="bold magenta")
    table.add_column("Source ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="green")
    table.add_column("Version", style="yellow")
    table.add_column("Media Types", style="blue")
    table.add_column("Website", style="white")

    for manifest in registry.list_manifests():
        table.add_row(
            manifest.id,
            manifest.name,
            manifest.version,
            ", ".join(manifest.supported_media_types),
            manifest.website,
        )

    console.print(table)


@sources_app.command("check")
def check_health(
    source_id: str = typer.Argument(None, help="Optional source ID to check. Omit to check all.")
):
    """Run real-time health checks on registered adapters."""
    async def _run_check():
        ctx = SourceExecutionContext()
        try:
            if source_id:
                adapter = registry.get_or_raise(source_id)
                console.print(f"[bold yellow]Checking health for adapter '{source_id}'...[/bold yellow]")
                check = await adapter.health_check(ctx)
                checks = [check]
            else:
                console.print("[bold yellow]Running health checks on all adapters...[/bold yellow]")
                checks = await registry.check_health_all(ctx)

            table = Table(title="Source Adapter Health Audit", show_header=True, header_style="bold magenta")
            table.add_column("Source ID", style="cyan")
            table.add_column("Status", style="bold")
            table.add_column("Response Time", style="yellow")
            table.add_column("Message", style="white")

            for check in checks:
                status_color = "green" if check.status == "ok" else ("yellow" if check.status == "degraded" else "red")
                status_str = f"[{status_color}]{check.status.upper()}[/{status_color}]"
                table.add_row(
                    check.source_id,
                    status_str,
                    f"{check.response_time_ms} ms",
                    check.message,
                )

            console.print(table)
        finally:
            await ctx.aclose()

    asyncio.run(_run_check())


@app.command()
def search(
    source_id: str = typer.Argument(..., help="Target source ID"),
    query: str = typer.Argument("", help="Search query string"),
    page: int = typer.Option(1, "--page", "-p", help="Page number"),
):
    """Search or browse titles for a specific source adapter."""
    async def _run_search():
        ctx = SourceExecutionContext()
        try:
            adapter = registry.get_or_raise(source_id)
            console.print(f"[bold green]Searching '{source_id}' for query='{query}' (page {page})...[/bold green]")
            res = await adapter.search_titles(SourceBrowseRequest(query=query, page=page), ctx)

            table = Table(title=f"Search Results: {source_id} (Page {res.page}/{res.total_pages or 1})", show_header=True)
            table.add_column("Title ID", style="cyan")
            table.add_column("Title Name", style="bold white")
            table.add_column("Media Type", style="blue")
            table.add_column("Canonical URL", style="white")

            for item in res.items:
                table.add_row(
                    item.source_title_id,
                    item.title[:45] + "..." if len(item.title) > 45 else item.title,
                    item.media_type,
                    item.canonical_url,
                )

            console.print(table)
            console.print(f"Total items found: [bold yellow]{len(res.items)}[/bold yellow]")
        finally:
            await ctx.aclose()

    asyncio.run(_run_search())


@app.command()
def details(
    source_id: str = typer.Argument(..., help="Target source ID"),
    title_id: str = typer.Argument(..., help="Target title ID"),
):
    """Inspect detailed metadata for a specific title."""
    async def _run_details():
        ctx = SourceExecutionContext()
        try:
            adapter = registry.get_or_raise(source_id)
            console.print(f"[bold green]Fetching details for '{title_id}' from '{source_id}'...[/bold green]")
            info = await adapter.get_title_details(title_id, ctx)

            panel_text = (
                f"[bold cyan]Title:[/bold cyan] {info.title}\n"
                f"[bold cyan]Canonical URL:[/bold cyan] {info.canonical_url}\n"
                f"[bold cyan]Media Type:[/bold cyan] {info.media_type}\n"
                f"[bold cyan]Status:[/bold cyan] {info.status}\n"
                f"[bold cyan]Tags:[/bold cyan] {', '.join(info.tags[:10])}\n"
                f"[bold cyan]Content Kind:[/bold cyan] {info.content_summary.kind}\n"
                f"[bold cyan]Total Count:[/bold cyan] {info.content_summary.total_count}"
            )
            console.print(Panel(panel_text, title=f"Title Details [{source_id}]"))
        finally:
            await ctx.aclose()

    asyncio.run(_run_details())


@unified_app.command("search")
def unified_search(
    query: str = typer.Argument("", help="Search query across all sources"),
    media_type: str = typer.Option("all", "--media-type", "-m", help="Media type filter ('all', 'anime', 'manga')"),
    page: int = typer.Option(1, "--page", "-p", help="Page number"),
):
    """Search across ALL registered sources concurrently."""
    from loouwd.services.unified import unified_service, UnifiedBrowseRequest

    async def _run_unified_search():
        console.print(f"[bold green]Running unified search across all sources for query='{query}' (media_type={media_type}, page={page})...[/bold green]")
        req = UnifiedBrowseRequest(query=query, media_type=media_type, page=page)
        res = await unified_service.browse_all(req)

        table = Table(
            title=f"Unified Search Results (Page {res.page}/{res.total_pages} | Total: {res.total_items})",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Source", style="cyan", no_wrap=True)
        table.add_column("Title Name", style="bold white")
        table.add_column("Media Type", style="blue")
        table.add_column("Canonical URL", style="white")

        for item in res.items:
            table.add_row(
                item.source_id,
                item.title[:45] + "..." if len(item.title) > 45 else item.title,
                item.media_type,
                item.canonical_url,
            )

        console.print(table)
        console.print(f"Sources Queried: [yellow]{', '.join(res.sources_queried)}[/yellow]")
        if res.failed_sources:
            console.print(f"Failed Sources: [red]{', '.join(res.failed_sources)}[/red]")

    asyncio.run(_run_unified_search())


@cache_app.command("clear")
def clear_cache():
    """Clear active in-memory cache."""
    asyncio.run(global_cache.clear())
    console.print("[bold green]Cache cleared successfully.[/bold green]")


if __name__ == "__main__":
    app()
