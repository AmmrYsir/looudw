from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import ORJSONResponse
from loouwd.core.schemas import (
    SourceManifest,
    SourceBrowseRequest,
    SourceBrowseResult,
    SourceTitleDetails,
    SourceTitleContent,
    SourceReaderPages,
    SourcePlayback,
    SourceHealthCheck,
)
from loouwd.core.registry import registry
from loouwd.core.context import default_context
from loouwd.core.cache import global_cache

router = APIRouter(prefix="/api/v1", default_response_class=ORJSONResponse)


@router.get("/sources", response_model=list[SourceManifest])
async def list_sources():
    """List all registered source adapter manifests."""
    return registry.list_manifests()


@router.get("/sources/health", response_model=list[SourceHealthCheck])
async def health_check_all():
    """Run health audits against all registered adapters."""
    return await registry.check_health_all(default_context)


@router.get("/sources/{source_id}", response_model=SourceManifest)
async def get_source_manifest(source_id: str):
    """Retrieve detailed manifest for a specific source adapter."""
    adapter = registry.get(source_id)
    if not adapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source adapter '{source_id}' not found.",
        )
    return adapter.manifest


@router.get("/sources/{source_id}/health", response_model=SourceHealthCheck)
async def health_check_source(source_id: str):
    """Run health audit for a single source adapter."""
    adapter = registry.get(source_id)
    if not adapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source adapter '{source_id}' not found.",
        )
    return await adapter.health_check(default_context)


@router.post("/sources/{source_id}/browse", response_model=SourceBrowseResult)
async def browse_source(source_id: str, request: SourceBrowseRequest):
    """Browse or search title catalog of a specific source adapter."""
    adapter = registry.get(source_id)
    if not adapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source adapter '{source_id}' not found.",
        )
    return await adapter.search_titles(request, default_context)


@router.get("/sources/{source_id}/titles/{source_title_id}", response_model=SourceTitleDetails)
async def get_title_details(source_id: str, source_title_id: str):
    """Get metadata details for a specific title."""
    adapter = registry.get(source_id)
    if not adapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source adapter '{source_id}' not found.",
        )
    return await adapter.get_title_details(source_title_id, default_context)


@router.get("/sources/{source_id}/titles/{source_title_id}/content", response_model=SourceTitleContent)
async def get_title_content(source_id: str, source_title_id: str):
    """Get title content (episodes, chapters, or page list)."""
    adapter = registry.get(source_id)
    if not adapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source adapter '{source_id}' not found.",
        )
    return await adapter.get_title_content(source_title_id, default_context)


@router.get("/sources/{source_id}/titles/{source_title_id}/pages", response_model=SourceReaderPages)
async def get_reader_pages(
    source_id: str, source_title_id: str, content_id: str | None = Query(default=None)
):
    """Get image reader pages for manga/doujin titles."""
    adapter = registry.get(source_id)
    if not adapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source adapter '{source_id}' not found.",
        )
    return await adapter.get_reader_pages(source_title_id, content_id, default_context)


@router.get("/sources/{source_id}/titles/{source_title_id}/playback", response_model=SourcePlayback)
async def get_playback(
    source_id: str, source_title_id: str, content_id: str | None = Query(default=None)
):
    """Get video playback stream metadata for video titles."""
    adapter = registry.get(source_id)
    if not adapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source adapter '{source_id}' not found.",
        )
    return await adapter.get_playback(source_title_id, content_id, default_context)


from loouwd.core.schemas import SourceTagSuggestion


@router.get("/sources/{source_id}/tags/autocomplete", response_model=list[SourceTagSuggestion])
async def autocomplete_tags(
    source_id: str,
    query: str = Query(..., min_length=1),
    tag_type: str = Query(default="tag", alias="type"),
):
    """Real-time tag autocompletion endpoint for UI search bars."""
    adapter = registry.get(source_id)
    if not adapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source adapter '{source_id}' not found.",
        )
    return await adapter.autocomplete_tags(query, tag_type=tag_type, context=default_context)


from loouwd.services.unified import (
    unified_service,
    UnifiedBrowseRequest,
    UnifiedBrowseResult,
)


@router.post("/unified/browse", response_model=UnifiedBrowseResult)
async def unified_browse(request: UnifiedBrowseRequest):
    """Unified search/browse across all registered source adapters in parallel."""
    return await unified_service.browse_all(request)


@router.get("/unified/feed/{media_type}", response_model=UnifiedBrowseResult)
async def unified_feed(
    media_type: str = "all",
    query: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=24, ge=1, le=100),
):
    """Unified media feed aggregating items by media_type ('all', 'anime', 'manga')."""
    valid_media_type = media_type if media_type in ["anime", "manga"] else "all"
    req = UnifiedBrowseRequest(
        query=query,
        media_type=valid_media_type,
        page=page,
        per_page=per_page,
    )
    return await unified_service.browse_all(req)


from fastapi.responses import StreamingResponse
import json
from loouwd.core.stream import stream_engine


@router.get("/unified/stream")
async def unified_stream(
    query: str | None = Query(default=None),
    media_type: str = Query(default="all"),
    page: int = Query(default=1, ge=1),
):
    """Server-Sent Events (SSE) real-time streaming endpoint for multi-source search."""
    valid_media_type = media_type if media_type in ["anime", "manga"] else "all"

    async def _event_generator():
        async for item in stream_engine.stream_browse(query=query, media_type=valid_media_type, page=page):
            payload = item.model_dump(by_alias=True)
            yield f"data: {json.dumps(payload)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(_event_generator(), media_type="text/event-stream")


@router.post("/cache/clear")
async def clear_cache():
    """Clear active in-memory cache."""
    await global_cache.clear()
    return {"message": "Cache cleared successfully."}
