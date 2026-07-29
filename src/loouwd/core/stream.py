import asyncio
from typing import AsyncGenerator, Literal
from loouwd.core.schemas import (
    SourceBrowseItem,
    SourceBrowseRequest,
    SourceMediaType,
)
from loouwd.core.registry import registry
from loouwd.core.context import SourceExecutionContext, default_context
from loouwd.core.logging import logger


class ReactiveStreamEngine:
    """
    Reactive Stream Pipeline for Multi-Source Search & Catalog Generation.
    Yields individual SourceBrowseItem objects to callers in real-time
    as fast as each target source adapter responds over the wire.
    """

    def __init__(self, context: SourceExecutionContext | None = None):
        self.context = context or default_context

    async def stream_browse(
        self,
        query: str | None = None,
        media_type: SourceMediaType | Literal["all"] = "all",
        source_ids: list[str] | None = None,
        page: int = 1,
    ) -> AsyncGenerator[SourceBrowseItem, None]:
        all_adapters = registry.list_sources()

        target_adapters = []
        for adapter in all_adapters:
            manifest = adapter.manifest
            if source_ids and manifest.id not in source_ids:
                continue
            if media_type != "all" and media_type not in manifest.supported_media_types:
                continue
            target_adapters.append(adapter)

        if not target_adapters:
            return

        item_queue: asyncio.Queue[SourceBrowseItem | None] = asyncio.Queue()
        browse_req = SourceBrowseRequest(query=query, page=page)
        active_tasks_count = len(target_adapters)

        async def _producer(adapter):
            nonlocal active_tasks_count
            try:
                res = await adapter.search_titles(browse_req, self.context)
                for item in res.items:
                    await item_queue.put(item)
            except Exception as e:
                logger.warning(f"Reactive producer error for adapter '{adapter.manifest.id}': {e}")
            finally:
                active_tasks_count -= 1
                if active_tasks_count == 0:
                    # Put sentinel to signal completion
                    await item_queue.put(None)

        # Launch all adapter producers concurrently
        for adapter in target_adapters:
            asyncio.create_task(_producer(adapter))

        # Consumer loop: yield items as they arrive in queue
        while True:
            item = await item_queue.get()
            if item is None:
                break
            yield item


stream_engine = ReactiveStreamEngine()
