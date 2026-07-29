import json
from typing import Any
from urllib.parse import quote

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
    SourceTitleChapter,
    SourceReaderPages,
    SourcePlayback,
    SourceTitlePage,
    SourceTitleContentSummary,
    SourceTagSuggestion,
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

SOURCE_ID = "omegascans"
SOURCE_NAME = "Omegascans"
BASE_URL = "https://omegascans.org"
FAVICON_URL = "/static/icons/omegascans.ico"
API_BASE_URL = "https://api.omegascans.org"

COMMON_GENRES = [
    "Action", "Adult", "Comedy", "Drama", "Ecchi", "Fantasy", "Harem",
    "Manhwa", "Martial Arts", "Mature", "Mystery", "Romance", "School Life",
    "Sci-fi", "Seinen", "Slice of Life", "Smut", "Supernatural"
]


@registry.register
class OmegaScansAdapter(BaseSourceAdapter):
    """
    Production-grade Omegascans REST API adapter with dynamic chapter resolution,
    JSON image reader payload parsing, and TLS fingerprint protection.
    """

    @property
    def manifest(self) -> SourceManifest:
        return SourceManifest(
            id=SOURCE_ID,
            name=SOURCE_NAME,
            version="2.0.0",
            description="Production-grade Omegascans REST API manhwa and webtoon engine.",
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
                        key="genre",
                        label="Genre Query (e.g. 'Action', 'Romance')",
                        type="text",
                        default_value="",
                    )
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
                        logger.debug(f"Omegascans TLS impersonation target '{profile}' failed: {err}")

            logger.warning(f"Omegascans API request to '{url}' failed.")
            return None

    @cached(ttl=300, key_prefix="omegascans:v2:search")
    async def search_titles(
        self, request: SourceBrowseRequest, context: SourceExecutionContext
    ) -> SourceBrowseResult:
        page = max(1, request.page)
        query = request.query.strip() if request.query else ""
        genre = request.filters.get("genre", "").strip()

        search_query = query or genre
        url = f"{API_BASE_URL}/query?page={page}&per_page=20"
        if search_query:
            url += f"&query={quote(search_query)}"

        data = await self._fetch_api_json(context, url)
        if not data or not isinstance(data, dict):
            return SourceBrowseResult(items=[], page=page, total_pages=1)

        raw_items = data.get("data", [])
        meta = data.get("meta", {})
        total_pages = meta.get("last_page", 1)

        items = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue

            slug = item.get("series_slug") or str(item.get("id"))
            title = item.get("title") or f"Series {slug}"
            thumb = item.get("thumbnail")

            items.append(
                SourceBrowseItem(
                    source_id=SOURCE_ID,
                    source_title_id=slug,
                    canonical_url=f"{BASE_URL}/series/{slug}",
                    title=title,
                    media_type="manga",
                    tracking_mode="read",
                    thumbnail_url=thumb,
                    description=item.get("description"),
                    rating=item.get("rating"),
                )
            )

        return SourceBrowseResult(
            items=items,
            page=page,
            total_pages=total_pages,
            applied_filters=request.filters,
        )

    @cached(ttl=600, key_prefix="omegascans:v2:details")
    async def get_title_details(
        self, source_title_id: str, context: SourceExecutionContext
    ) -> SourceTitleDetails:
        url = f"{API_BASE_URL}/series/{source_title_id}"
        item = await self._fetch_api_json(context, url)

        if not item or not isinstance(item, dict):
            return SourceTitleDetails(
                source_id=SOURCE_ID,
                source_title_id=source_title_id,
                canonical_url=f"{BASE_URL}/series/{source_title_id}",
                title=f"Series {source_title_id}",
                media_type="manga",
                tracking_mode="read",
                content_summary=SourceTitleContentSummary(kind="none", total_count=0, available_count=0),
            )

        title = item.get("title") or f"Series {source_title_id}"
        thumb = item.get("thumbnail")
        desc = item.get("description")
        alt = [item.get("alternative_names")] if item.get("alternative_names") else []
        tags = [t.get("name") for t in item.get("tags", []) if isinstance(t, dict) and t.get("name")]

        series_id = item.get("id")
        ch_count = 0
        if series_id:
            ch_url = f"{API_BASE_URL}/chapter/query?series_id={series_id}&per_page=1"
            ch_data = await self._fetch_api_json(context, ch_url)
            if ch_data and isinstance(ch_data, dict):
                ch_count = ch_data.get("meta", {}).get("total", 0)

        return SourceTitleDetails(
            source_id=SOURCE_ID,
            source_title_id=source_title_id,
            canonical_url=f"{BASE_URL}/series/{source_title_id}",
            title=title,
            media_type="manga",
            tracking_mode="read",
            thumbnail_url=thumb,
            description=desc,
            alt_titles=alt,
            tags=tags,
            total_chapters=ch_count,
            content_summary=SourceTitleContentSummary(
                kind="chapters",
                total_count=ch_count,
                available_count=ch_count,
                in_app_capabilities=["reader"],
            ),
        )

    async def get_title_content(
        self, source_title_id: str, context: SourceExecutionContext
    ) -> SourceTitleContent:
        url_series = f"{API_BASE_URL}/series/{source_title_id}"
        item = await self._fetch_api_json(context, url_series)
        series_id = item.get("id") if isinstance(item, dict) else None

        if not series_id:
            return SourceTitleContent(kind="chapters", chapters=[])

        ch_url = f"{API_BASE_URL}/chapter/query?series_id={series_id}&per_page=100"
        ch_data = await self._fetch_api_json(context, ch_url)
        if not ch_data or not isinstance(ch_data, dict):
            return SourceTitleContent(kind="chapters", chapters=[])

        raw_chaps = ch_data.get("data", [])
        chapters = []

        for ch in raw_chaps:
            if not isinstance(ch, dict):
                continue

            chap_slug = ch.get("chapter_slug") or str(ch.get("id"))
            chap_name = ch.get("chapter_name") or f"Chapter {chap_slug}"
            num = ch.get("index") or ch.get("chapter_number")

            chapters.append(
                SourceTitleChapter(
                    id=chap_slug,
                    number=num,
                    title=chap_name,
                    canonical_url=f"{BASE_URL}/series/{source_title_id}/{chap_slug}",
                    released_at=ch.get("created_at"),
                )
            )

        return SourceTitleContent(kind="chapters", chapters=chapters)

    @cached(ttl=600, key_prefix="omegascans:v2:pages")
    async def get_reader_pages(
        self, source_title_id: str, content_id: str | None, context: SourceExecutionContext
    ) -> SourceReaderPages:
        chap_slug = content_id or "chapter-1"
        url = f"{API_BASE_URL}/chapter/{source_title_id}/{chap_slug}"
        res = await self._fetch_api_json(context, url)

        if not res or not isinstance(res, dict):
            return SourceReaderPages(content_id=chap_slug, pages=[])

        chap_obj = res.get("chapter") or res
        chap_name = chap_obj.get("chapter_name") or f"Chapter {chap_slug}"
        raw_data = chap_obj.get("chapter_data")

        img_urls = []
        if isinstance(raw_data, dict):
            img_urls = raw_data.get("images", [])
        elif isinstance(raw_data, str):
            try:
                parsed = json.loads(raw_data)
                if isinstance(parsed, dict):
                    img_urls = parsed.get("images", [])
            except Exception:
                pass

        if not img_urls:
            img_urls = res.get("images") or []

        pages = []
        for idx, img in enumerate(img_urls, 1):
            img_src = img if isinstance(img, str) else img.get("url", "")
            if img_src:
                pages.append(
                    SourceTitlePage(
                        id=f"{chap_slug}-{idx}",
                        number=idx,
                        image_url=img_src,
                    )
                )

        return SourceReaderPages(
            content_id=chap_slug,
            title=chap_name,
            pages=pages,
        )

    @cached(ttl=600, key_prefix="omegascans:v2:autocomplete")
    async def autocomplete_tags(
        self, query: str, tag_type: str = "tag", context: SourceExecutionContext | None = None
    ) -> list[SourceTagSuggestion]:
        q = query.lower().strip()
        suggestions = []
        for genre in COMMON_GENRES:
            if q in genre.lower():
                suggestions.append(
                    SourceTagSuggestion(
                        name=genre,
                        type="genre",
                        description=f"Omegascans genre for {genre}",
                    )
                )
        return suggestions
