import re
from urllib.parse import quote, urljoin
from bs4 import BeautifulSoup

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
    SourceTitleEpisode,
    SourceReaderPages,
    SourcePlayback,
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

SOURCE_ID = "xvideos"
SOURCE_NAME = "XVideos"
BASE_URL = "https://www.xvideos.com"
FAVICON_URL = "/static/icons/xvideos.svg"

CATEGORY_OPTIONS = [
    SourceFilterOption(value="", label="All Categories"),
    SourceFilterOption(value="amateur", label="Amateur"),
    SourceFilterOption(value="anal", label="Anal"),
    SourceFilterOption(value="asian", label="Asian"),
    SourceFilterOption(value="blowjob", label="Blowjob"),
    SourceFilterOption(value="creampie", label="Creampie"),
    SourceFilterOption(value="hentai", label="Hentai"),
    SourceFilterOption(value="milf", label="MILF"),
    SourceFilterOption(value="teen", label="Teen"),
]

COMMON_TAGS = [
    "anime", "hentai", "creampie", "blowjob", "asian", "milf", "amateur",
    "anal", "hardcore", "japanese", "3d", "cosplay", "uncensored"
]


@registry.register
class XVideosAdapter(BaseSourceAdapter):
    """
    Production-grade XVideos adapter with html5player JS stream parser (HLS, MP4 high/low),
    clean title card extraction, and TLS fingerprint protection.
    """

    @property
    def manifest(self) -> SourceManifest:
        return SourceManifest(
            id=SOURCE_ID,
            name=SOURCE_NAME,
            version="2.0.0",
            description="Production-grade XVideos video database with html5player JS stream resolution.",
            website=BASE_URL,
            icon_url=FAVICON_URL,
            supported_media_types=["anime"],
            auth=SourceAuthConfig(type="none"),
            features=SourceFeatureSet(
                browse=True, search=True, title_details=True, favorites=True, tag_autocomplete=True
            ),
            browse_config=SourceBrowseConfig(
                supports_pagination=True,
                filters=[
                    SourceFilterDefinition(
                        key="category",
                        label="Category",
                        type="select",
                        default_value="",
                        options=CATEGORY_OPTIONS,
                    ),
                    SourceFilterDefinition(
                        key="tag",
                        label="Tag Query (e.g. 'anime', 'hentai')",
                        type="text",
                        default_value="",
                    ),
                ],
            ),
        )

    async def _fetch_html(self, context: SourceExecutionContext, url: str) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": f"{BASE_URL}/",
        }
        try:
            return await context.fetch_text(url, headers=headers)
        except Exception:
            if HAS_CURL_CFFI:
                for profile in ["safari15_5", "chrome124", "chrome120"]:
                    try:
                        async with CurlSession(impersonate=profile, headers=headers) as session:
                            res = await session.get(url, timeout=12)
                            if res.status_code == 200 and len(res.text) > 5000:
                                return res.text
                    except Exception as err:
                        logger.debug(f"XVideos TLS impersonation target '{profile}' failed: {err}")

            logger.warning(f"XVideos request to '{url}' failed.")
            return ""

    @cached(ttl=300, key_prefix="xvideos:v2:search")
    async def search_titles(
        self, request: SourceBrowseRequest, context: SourceExecutionContext
    ) -> SourceBrowseResult:
        page = max(1, request.page)
        query = request.query.strip() if request.query else ""
        category = request.filters.get("category", "")
        tag = request.filters.get("tag", "").strip()

        search_query = query or tag or category
        if search_query:
            url = f"{BASE_URL}/?k={quote(search_query)}"
            if page > 1:
                url += f"&p={page - 1}"
        else:
            url = f"{BASE_URL}/new/{page - 1}" if page > 1 else BASE_URL

        html = await self._fetch_html(context, url)
        if not html:
            return SourceBrowseResult(items=[], page=page, total_pages=1)

        soup = BeautifulSoup(html, "lxml")
        items = []
        seen = set()

        for div in soup.select("div.thumb-block"):
            link = div.select_one("p.title a")
            img = div.select_one("div.thumb img")
            if not link:
                continue

            href = link.get("href", "")
            match = re.search(r"/video\.([a-z0-9_]+)", href, re.I)
            if not match:
                continue

            vid = match.group(1)
            if vid in seen:
                continue
            seen.add(vid)

            raw_title = link.get("title") or link.text.strip()
            clean_title = re.sub(r"\s*\d+\s*min$", "", raw_title, flags=re.I).strip()

            thumb_url = img.get("data-src") or img.get("src") if img else None
            if thumb_url and thumb_url.startswith("//"):
                thumb_url = f"https:{thumb_url}"

            items.append(
                SourceBrowseItem(
                    source_id=SOURCE_ID,
                    source_title_id=href,  # Use full href as source_title_id to guarantee exact video page URL
                    canonical_url=urljoin(BASE_URL, href),
                    title=clean_title or f"XVideos Video {vid}",
                    media_type="anime",
                    tracking_mode="watch",
                    thumbnail_url=thumb_url,
                    total_episodes=1,
                )
            )

        return SourceBrowseResult(
            items=items,
            page=page,
            total_pages=page + 5,
            applied_filters=request.filters,
        )

    @cached(ttl=600, key_prefix="xvideos:v2:details")
    async def get_title_details(
        self, source_title_id: str, context: SourceExecutionContext
    ) -> SourceTitleDetails:
        href = source_title_id if source_title_id.startswith("/") else f"/video.{source_title_id}/"
        canonical_url = urljoin(BASE_URL, href)
        html = await self._fetch_html(context, canonical_url)

        if not html:
            return SourceTitleDetails(
                source_id=SOURCE_ID,
                source_title_id=source_title_id,
                canonical_url=canonical_url,
                title=f"XVideos Video {source_title_id}",
                media_type="anime",
                tracking_mode="watch",
                content_summary=SourceTitleContentSummary(kind="episodes", total_count=1, available_count=1),
            )

        soup = BeautifulSoup(html, "lxml")

        title_match = re.search(r"html5player\.setVideoTitle\('([^']+)'\)", html)
        if title_match:
            title = title_match.group(1).strip()
        else:
            title_el = soup.select_one("h2.page-title") or soup.select_one("title")
            title = title_el.text.strip() if title_el else f"XVideos Video {source_title_id}"

        thumb_match = re.search(r"html5player\.setThumbUrl169\('([^']+)'\)", html) or re.search(r"html5player\.setThumbUrl\('([^']+)'\)", html)
        thumb_url = thumb_match.group(1) if thumb_match else None

        tags = [a.text.strip() for a in soup.select("a.btn-default, a[href*='/tags/']")]

        return SourceTitleDetails(
            source_id=SOURCE_ID,
            source_title_id=source_title_id,
            canonical_url=canonical_url,
            title=title,
            media_type="anime",
            tracking_mode="watch",
            thumbnail_url=thumb_url,
            tags=tags,
            content_summary=SourceTitleContentSummary(
                kind="episodes",
                total_count=1,
                available_count=1,
                in_app_capabilities=["player"],
            ),
        )

    async def get_title_content(
        self, source_title_id: str, context: SourceExecutionContext
    ) -> SourceTitleContent:
        details = await self.get_title_details(source_title_id, context)
        episodes = [
            SourceTitleEpisode(
                id=f"{source_title_id}::video",
                number=1,
                title=details.title,
                canonical_url=details.canonical_url,
                thumbnail_url=details.thumbnail_url,
            )
        ]
        return SourceTitleContent(kind="episodes", episodes=episodes)

    async def get_reader_pages(
        self, source_title_id: str, content_id: str | None, context: SourceExecutionContext
    ) -> SourceReaderPages:
        return SourceReaderPages(content_id=source_title_id, pages=[])

    @cached(ttl=600, key_prefix="xvideos:v2:playback")
    async def get_playback(
        self, source_title_id: str, content_id: str | None = None, context: SourceExecutionContext | None = None
    ) -> SourcePlayback:
        href = source_title_id if source_title_id.startswith("/") else f"/video.{source_title_id}/"
        canonical_url = urljoin(BASE_URL, href)
        embed_url = f"{BASE_URL}/embedframe/{source_title_id.replace('/video.', '').replace('/', '')}"

        from loouwd.core.context import default_context
        ctx = context or default_context
        html = await self._fetch_html(ctx, canonical_url)

        stream_url = embed_url
        poster_url = None
        title = f"XVideos Video {source_title_id}"

        if html:
            high_match = re.search(r"html5player\.setVideoUrlHigh\('([^']+)'\)", html)
            hls_match = re.search(r"html5player\.setVideoHLS\('([^']+)'\)", html)
            low_match = re.search(r"html5player\.setVideoUrlLow\('([^']+)'\)", html)

            if high_match:
                stream_url = high_match.group(1)
            elif hls_match:
                stream_url = hls_match.group(1)
            elif low_match:
                stream_url = low_match.group(1)

            thumb_match = re.search(r"html5player\.setThumbUrl169\('([^']+)'\)", html) or re.search(r"html5player\.setThumbUrl\('([^']+)'\)", html)
            if thumb_match:
                poster_url = thumb_match.group(1)

            title_match = re.search(r"html5player\.setVideoTitle\('([^']+)'\)", html)
            if title_match:
                title = title_match.group(1)

        return SourcePlayback(
            content_id=source_title_id,
            title=title,
            stream_url=stream_url,
            mime_type="application/x-mpegURL" if stream_url.endswith(".m3u8") else "video/mp4",
            poster_url=poster_url,
            canonical_url=canonical_url,
        )

    @cached(ttl=600, key_prefix="xvideos:v2:autocomplete")
    async def autocomplete_tags(
        self, query: str, tag_type: str = "tag", context: SourceExecutionContext | None = None
    ) -> list[SourceTagSuggestion]:
        q = query.lower().strip()
        suggestions = []
        for tag in COMMON_TAGS:
            if q in tag:
                suggestions.append(
                    SourceTagSuggestion(
                        name=tag,
                        type="tag",
                        description=f"XVideos tag query for '{tag}'",
                    )
                )
        return suggestions
