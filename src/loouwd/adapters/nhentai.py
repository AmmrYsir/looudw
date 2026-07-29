import math
from typing import Any
from urllib.parse import quote, urljoin

from loouwd.core.schemas import (
    SourceManifest,
    SourceAuthConfig,
    SourceFeatureSet,
    SourceBrowseConfig,
    SourceFilterDefinition,
    SourceFilterOption,
    SourceBrowseRequest,
    SourceBrowseResult,
    SourceBrowseItem,
    SourceTitleDetails,
    SourceTitleContent,
    SourceReaderPages,
    SourcePlayback,
    SourceTitlePage,
    SourceTitleContentSummary,
)
from loouwd.core.context import SourceExecutionContext
from loouwd.core.registry import registry, BaseSourceAdapter
from loouwd.core.cache import cached
from loouwd.core.logging import logger

try:
    from curl_cffi.requests import AsyncSession as CurlSession
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

SOURCE_ID = "nhentai"
SOURCE_NAME = "nhentai"
BASE_URL = "https://nhentai.net"
FAVICON_URL = "/static/icons/nhentai.png"
API_V2_BASE = "https://nhentai.net/api/v2"
IMAGE_CDN_BASE = "https://i.nhentai.net"
THUMB_CDN_BASE = "https://t.nhentai.net"

# API-Native Filters based on official nhentai v2 specification
SORT_OPTIONS = [
    SourceFilterOption(value="recent", label="Recent / Newest"),
    SourceFilterOption(value="popular", label="Popular (All Time)"),
    SourceFilterOption(value="popular-today", label="Popular Today"),
    SourceFilterOption(value="popular-week", label="Popular This Week"),
    SourceFilterOption(value="popular-month", label="Popular This Month"),
]

LANGUAGE_OPTIONS = [
    SourceFilterOption(value="", label="All Languages"),
    SourceFilterOption(value="english", label="English"),
    SourceFilterOption(value="japanese", label="Japanese"),
    SourceFilterOption(value="chinese", label="Chinese"),
]

CATEGORY_OPTIONS = [
    SourceFilterOption(value="", label="All Categories"),
    SourceFilterOption(value="doujinshi", label="Doujinshi"),
    SourceFilterOption(value="manga", label="Manga"),
    SourceFilterOption(value="artist-cg", label="Artist CG"),
    SourceFilterOption(value="game-cg", label="Game CG"),
    SourceFilterOption(value="non-h", label="Non-H"),
]


@registry.register
class NHentaiAdapter(BaseSourceAdapter):
    """
    Production-grade nhentai source adapter built against official v2 REST API specs.
    Features dynamic API-native filters, freeform tag search, exact image extension mapping,
    and Cloudflare TLS fingerprint impersonation.
    """

    @property
    def manifest(self) -> SourceManifest:
        return SourceManifest(
            id=SOURCE_ID,
            name=SOURCE_NAME,
            version="2.1.0",
            description="Official nhentai v2 REST API engine with dynamic API-native sorting and filters.",
            website=BASE_URL,
            icon_url=FAVICON_URL,
            supported_media_types=["manga"],
            auth=SourceAuthConfig(type="none"),
            features=SourceFeatureSet(
                browse=True, search=True, title_details=True, favorites=True, tag_autocomplete=True
            ),
            browse_config=SourceBrowseConfig(
                supports_pagination=True,
                filters=[
                    SourceFilterDefinition(
                        key="sort",
                        label="Sort By",
                        type="select",
                        default_value="recent",
                        options=SORT_OPTIONS,
                    ),
                    SourceFilterDefinition(
                        key="language",
                        label="Language",
                        type="select",
                        default_value="",
                        options=LANGUAGE_OPTIONS,
                    ),
                    SourceFilterDefinition(
                        key="category",
                        label="Category",
                        type="select",
                        default_value="",
                        options=CATEGORY_OPTIONS,
                    ),
                    SourceFilterDefinition(
                        key="tag",
                        label="Tag Query (e.g. 'full color', 'sole female')",
                        type="text",
                        default_value="",
                    ),
                    SourceFilterDefinition(
                        key="parody",
                        label="Parody Query (e.g. 'genshin impact')",
                        type="text",
                        default_value="",
                    ),
                ],
            ),
        )

    async def _fetch_api_json(self, context: SourceExecutionContext, url: str) -> dict | list | None:
        headers = {
            "accept": "application/json, text/plain, */*",
            "referer": f"{BASE_URL}/",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        }
        try:
            return await context.fetch_json(url, headers=headers)
        except Exception:
            if HAS_CURL_CFFI:
                for profile in ["safari15_5", "chrome124", "chrome120"]:
                    try:
                        async with CurlSession(impersonate=profile, headers=headers) as session:
                            res = await session.get(url, timeout=12)
                            if res.status_code == 200:
                                return res.json()
                    except Exception as err:
                        logger.debug(f"nhentai TLS impersonation target '{profile}' failed: {err}")

            logger.warning(f"nhentai API request to '{url}' failed.")
            return None

    @cached(ttl=300, key_prefix="nhentai:v2:search")
    async def search_titles(
        self, request: SourceBrowseRequest, context: SourceExecutionContext
    ) -> SourceBrowseResult:
        page = max(1, request.page)
        query = request.query.strip() if request.query else ""
        sort = request.filters.get("sort", "recent")
        language = request.filters.get("language", "")
        category = request.filters.get("category", "")
        tag = request.filters.get("tag", "")
        parody = request.filters.get("parody", "")

        # Build nhentai v2 query string
        query_parts = []
        if query:
            query_parts.append(query)
        if language:
            query_parts.append(f'language:"{language}"')
        if category:
            query_parts.append(f'category:"{category}"')
        if tag:
            query_parts.append(f'tag:"{tag}"')
        if parody:
            query_parts.append(f'parody:"{parody}"')

        full_query = " ".join(query_parts)

        # Construct API v2 URL
        if full_query:
            url = f"{API_V2_BASE}/galleries?query={quote(full_query)}&page={page}"
            if sort and sort != "recent":
                url += f"&sort={quote(str(sort))}"
        else:
            url = f"{API_V2_BASE}/galleries?page={page}"
            if sort:
                url += f"&sort={quote(str(sort))}"

        data = await self._fetch_api_json(context, url)
        if not data or not isinstance(data, dict):
            return SourceBrowseResult(items=[], page=page, total_pages=1)

        results = data.get("result", [])
        total_pages = data.get("num_pages", 1)

        items = []
        for g in results:
            if not isinstance(g, dict) or g.get("blacklisted"):
                continue

            gid = str(g.get("id"))
            title_obj = g.get("title") or {}
            title = (
                title_obj.get("pretty")
                or title_obj.get("english")
                or title_obj.get("japanese")
                or f"Gallery {gid}"
            )

            thumb_obj = g.get("thumbnail") or g.get("cover")
            thumb_url = None
            if isinstance(thumb_obj, dict) and thumb_obj.get("path"):
                thumb_url = f"{THUMB_CDN_BASE}/{thumb_obj.get('path')}"
            elif g.get("media_id"):
                thumb_url = f"{THUMB_CDN_BASE}/galleries/{g.get('media_id')}/thumb.jpg"

            items.append(
                SourceBrowseItem(
                    source_id=SOURCE_ID,
                    source_title_id=gid,
                    canonical_url=f"{BASE_URL}/g/{gid}/",
                    title=title,
                    media_type="manga",
                    tracking_mode="read",
                    thumbnail_url=thumb_url,
                    total_chapters=1,
                )
            )

        return SourceBrowseResult(
            items=items,
            page=page,
            total_pages=total_pages,
            applied_filters=request.filters,
        )

    @cached(ttl=600, key_prefix="nhentai:v2:details")
    async def get_title_details(
        self, source_title_id: str, context: SourceExecutionContext
    ) -> SourceTitleDetails:
        url = f"{API_V2_BASE}/galleries/{source_title_id}"
        g = await self._fetch_api_json(context, url)

        if not g or not isinstance(g, dict):
            return SourceTitleDetails(
                source_id=SOURCE_ID,
                source_title_id=source_title_id,
                canonical_url=f"{BASE_URL}/g/{source_title_id}/",
                title=f"Gallery {source_title_id}",
                media_type="manga",
                tracking_mode="read",
                content_summary=SourceTitleContentSummary(kind="none", total_count=0, available_count=0),
            )

        gid = str(g.get("id", source_title_id))
        title_obj = g.get("title") or {}
        title = title_obj.get("pretty") or title_obj.get("english") or f"Gallery {gid}"
        alt_titles = [t for t in [title_obj.get("english"), title_obj.get("japanese")] if t]

        thumb_obj = g.get("cover") or g.get("thumbnail")
        thumb_url = None
        if isinstance(thumb_obj, dict) and thumb_obj.get("path"):
            thumb_url = f"{THUMB_CDN_BASE}/{thumb_obj.get('path')}"

        tags = [t.get("name") for t in g.get("tags", []) if isinstance(t, dict) and t.get("name")]
        num_pages = g.get("num_pages") or len(g.get("pages", []))

        return SourceTitleDetails(
            source_id=SOURCE_ID,
            source_title_id=gid,
            canonical_url=f"{BASE_URL}/g/{gid}/",
            title=title,
            media_type="manga",
            tracking_mode="read",
            thumbnail_url=thumb_url,
            alt_titles=alt_titles,
            status="completed",
            tags=tags,
            content_summary=SourceTitleContentSummary(
                kind="pages",
                total_count=num_pages,
                available_count=num_pages,
                in_app_capabilities=["reader"],
            ),
        )

    async def get_title_content(
        self, source_title_id: str, context: SourceExecutionContext
    ) -> SourceTitleContent:
        pages_res = await self.get_reader_pages(source_title_id, None, context)
        return SourceTitleContent(kind="pages", pages=pages_res.pages)

    @cached(ttl=600, key_prefix="nhentai:v2:pages")
    async def get_reader_pages(
        self, source_title_id: str, content_id: str | None, context: SourceExecutionContext
    ) -> SourceReaderPages:
        url = f"{API_V2_BASE}/galleries/{source_title_id}"
        g = await self._fetch_api_json(context, url)

        if not g or not isinstance(g, dict):
            return SourceReaderPages(content_id=source_title_id, pages=[])

        raw_pages = g.get("pages", [])
        pages = []
        for idx, p in enumerate(raw_pages, 1):
            if isinstance(p, dict):
                page_num = p.get("number", idx)
                path = p.get("path", "")
                thumb_path = p.get("thumbnail", path)

                img_url = f"{IMAGE_CDN_BASE}/{path}" if path else f"{IMAGE_CDN_BASE}/galleries/{g.get('media_id')}/{idx}.jpg"
                thumb_url = f"{THUMB_CDN_BASE}/{thumb_path}" if thumb_path else img_url

                pages.append(
                    SourceTitlePage(
                        id=f"{source_title_id}-{page_num}",
                        number=page_num,
                        image_url=img_url,
                        thumbnail_url=thumb_url,
                        width=p.get("width"),
                        height=p.get("height"),
                    )
                )

        title_obj = g.get("title") or {}
        title = title_obj.get("pretty") or f"Gallery {source_title_id}"

        return SourceReaderPages(
            content_id=source_title_id,
            title=title,
            pages=pages,
        )

    @cached(ttl=600, key_prefix="nhentai:v2:autocomplete")
    async def autocomplete_tags(
        self, query: str, tag_type: str = "tag", context: SourceExecutionContext | None = None
    ) -> list[Any]:
        from loouwd.core.schemas import SourceTagSuggestion
        from loouwd.core.context import default_context

        ctx = context or default_context
        clean_type = tag_type.lower().strip() if tag_type else "tag"
        if clean_type not in ["artist", "category", "character", "group", "language", "parody", "tag"]:
            clean_type = "tag"

        url = f"{API_V2_BASE}/tags/{clean_type}?query={quote(query.strip())}"
        data = await self._fetch_api_json(ctx, url)

        if not data or not isinstance(data, dict):
            return []

        results = data.get("result", [])
        suggestions = []
        for item in results:
            if isinstance(item, dict) and item.get("name"):
                suggestions.append(
                    SourceTagSuggestion(
                        name=item.get("name"),
                        type=item.get("type", clean_type),
                        count=item.get("count"),
                        description=item.get("description"),
                    )
                )

        return suggestions
