import asyncio
import math
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

from loouwd.core.schemas import (
    SourceBrowseItem,
    SourceBrowseRequest,
    SourceTitleDetails,
    SourceTitleContent,
    SourceMediaType,
)
from loouwd.core.registry import registry
from loouwd.core.context import SourceExecutionContext, default_context
from loouwd.core.logging import logger
from loouwd.core.cache import cached


class UnifiedBrowseRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    query: str | None = None
    media_type: SourceMediaType | Literal["all"] = Field(default="all", alias="mediaType")
    source_ids: list[str] | None = Field(default=None, alias="sourceIds")
    page: int = 1
    per_page: int = Field(default=24, alias="perPage")
    sort_by: Literal["relevance", "title", "source"] = Field(default="relevance", alias="sortBy")


class UnifiedBrowseResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[SourceBrowseItem] = Field(default_factory=list)
    page: int = 1
    per_page: int = Field(default=24, alias="perPage")
    total_items: int = Field(default=0, alias="totalItems")
    total_pages: int = Field(default=1, alias="totalPages")
    sources_queried: list[str] = Field(default_factory=list, alias="sourcesQueried")
    failed_sources: list[str] = Field(default_factory=list, alias="failedSources")


class UnifiedCatalogService:
    """
    Main Unification Module that integrates and aggregates all different source adapters
    into a standardized, uniform data interface and API.
    """

    def __init__(self, context: SourceExecutionContext | None = None):
        self.context = context or default_context

    @cached(ttl=120, key_prefix="unified:browse")
    async def browse_all(self, req: UnifiedBrowseRequest) -> UnifiedBrowseResult:
        all_adapters = registry.list_sources()

        # Filter active adapters by requested source_ids or media_type
        target_adapters = []
        for adapter in all_adapters:
            manifest = adapter.manifest
            if req.source_ids and manifest.id not in req.source_ids:
                continue
            if req.media_type != "all" and req.media_type not in manifest.supported_media_types:
                continue
            target_adapters.append(adapter)

        if not target_adapters:
            return UnifiedBrowseResult(
                items=[],
                page=req.page,
                per_page=req.per_page,
                total_items=0,
                total_pages=1,
                sources_queried=[],
            )

        # Execute concurrent search requests across all target adapters
        browse_req = SourceBrowseRequest(query=req.query, page=req.page)

        async def _fetch_from_adapter(adapter):
            try:
                res = await adapter.search_titles(browse_req, self.context)
                return adapter.manifest.id, res.items, None
            except Exception as e:
                logger.warning(f"Unified query failed for adapter '{adapter.manifest.id}': {e}")
                return adapter.manifest.id, [], str(e)

        results = await asyncio.gather(*[_fetch_from_adapter(a) for a in target_adapters])

        all_items: list[SourceBrowseItem] = []
        sources_queried: list[str] = []
        failed_sources: list[str] = []

        for sid, items, err in results:
            sources_queried.append(sid)
            if err:
                failed_sources.append(sid)
            else:
                all_items.extend(items)

        # Sort combined results
        if req.sort_by == "title":
            all_items.sort(key=lambda x: x.title.lower())
        elif req.sort_by == "source":
            all_items.sort(key=lambda x: x.source_id)

        # Apply global pagination over aggregated items
        total_items = len(all_items)
        total_pages = max(1, math.ceil(total_items / req.per_page))
        start_idx = (req.page - 1) * req.per_page
        end_idx = start_idx + req.per_page
        paginated_items = all_items[start_idx:end_idx]

        return UnifiedBrowseResult(
            items=paginated_items,
            page=req.page,
            per_page=req.per_page,
            total_items=total_items,
            total_pages=total_pages,
            sources_queried=sources_queried,
            failed_sources=failed_sources,
        )

    async def get_unified_details(self, source_id: str, source_title_id: str) -> SourceTitleDetails:
        """Fetch title details from any adapter uniformly."""
        adapter = registry.get_or_raise(source_id)
        return await adapter.get_title_details(source_title_id, self.context)

    async def get_unified_content(self, source_id: str, source_title_id: str) -> SourceTitleContent:
        """Fetch title content (episodes, chapters, pages) from any adapter uniformly."""
        adapter = registry.get_or_raise(source_id)
        return await adapter.get_title_content(source_title_id, self.context)


unified_service = UnifiedCatalogService()
