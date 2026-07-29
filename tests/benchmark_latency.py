import asyncio
import time
from rich.console import Console
from rich.table import Table

from loouwd.core.context import SourceExecutionContext
import loouwd.adapters  # Register all adapters
from loouwd.core.registry import registry
from loouwd.core.schemas import SourceBrowseRequest
from loouwd.services.unified import unified_service, UnifiedBrowseRequest
from loouwd.core.cache import global_cache

console = Console()


async def benchmark_adapter(adapter, ctx: SourceExecutionContext):
    sid = adapter.manifest.id
    req = SourceBrowseRequest(page=1)

    # 1. Uncached execution latency
    t0 = time.perf_counter()
    res1 = await adapter.search_titles(req, ctx)
    t1 = time.perf_counter()
    uncached_ms = (t1 - t0) * 1000

    # 2. Cached execution latency
    t2 = time.perf_counter()
    res2 = await adapter.search_titles(req, ctx)
    t3 = time.perf_counter()
    cached_ms = (t3 - t2) * 1000

    items_count = len(res1.items)
    speedup = uncached_ms / cached_ms if cached_ms > 0 else 0.0

    return {
        "id": sid,
        "name": adapter.manifest.name,
        "items": items_count,
        "uncached_ms": round(uncached_ms, 2),
        "cached_ms": round(cached_ms, 2),
        "speedup": round(speedup, 1),
    }


async def main():
    ctx = SourceExecutionContext()
    await global_cache.clear()

    console.print("\n[bold green]Running Latency Benchmark across all Source Adapters...[/bold green]\n")

    results = []
    for adapter in registry.list_sources():
        res = await benchmark_adapter(adapter, ctx)
        results.append(res)

    # Benchmark Unified Multi-Source Search (Concurrent 7 Adapters)
    await global_cache.clear()
    unified_req = UnifiedBrowseRequest(query="", page=1, per_page=20)

    t0 = time.perf_counter()
    uni_res1 = await unified_service.browse_all(unified_req)
    t1 = time.perf_counter()
    uni_uncached_ms = (t1 - t0) * 1000

    t2 = time.perf_counter()
    uni_res2 = await unified_service.browse_all(unified_req)
    t3 = time.perf_counter()
    uni_cached_ms = (t3 - t2) * 1000

    uni_speedup = uni_uncached_ms / uni_cached_ms if uni_cached_ms > 0 else 0.0

    results.append({
        "id": "UNIFIED_ALL (7 sources)",
        "name": "Unified Multi-Source Search",
        "items": uni_res1.total_items,
        "uncached_ms": round(uni_uncached_ms, 2),
        "cached_ms": round(uni_cached_ms, 2),
        "speedup": round(uni_speedup, 1),
    })

    # Render Rich Benchmark Report Table
    table = Table(
        title="loouwd Latency Benchmark Report",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Adapter / Endpoint", style="cyan", no_wrap=True)
    table.add_column("Items Fetched", style="yellow")
    table.add_column("Uncached Latency", style="bold red")
    table.add_column("Cached Latency", style="bold green")
    table.add_column("Speedup Ratio", style="bold white")

    for r in results:
        table.add_row(
            r["id"],
            str(r["items"]),
            f"{r['uncached_ms']} ms",
            f"{r['cached_ms']} ms",
            f"{r['speedup']}x faster",
        )

    console.print(table)
    await ctx.aclose()


if __name__ == "__main__":
    asyncio.run(main())
