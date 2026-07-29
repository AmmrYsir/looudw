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

SOURCE_ID = "xhamster"
SOURCE_NAME = "xHamster"
BASE_URL = "https://xhamster.com"
FAVICON_URL = "/static/icons/xhamsters.png"

FEED_OPTIONS = [
    SourceFilterOption(value="best", label="Best"),
    SourceFilterOption(value="most_viewed", label="Most Viewed"),
    SourceFilterOption(value="most_commented", label="Most Commented"),
    SourceFilterOption(value="newest", label="Newest"),
]

CATEGORY_OPTIONS = [
    SourceFilterOption(value="", label="All Categories"),
    SourceFilterOption(value="amateur", label="Amateur"),
    SourceFilterOption(value="anal", label="Anal"),
    SourceFilterOption(value="asian", label="Asian"),
    SourceFilterOption(value="blowjob", label="Blowjob"),
    SourceFilterOption(value="creampie", label="Creampie"),
    SourceFilterOption(value="hentai", label="Hentai"),
    SourceFilterOption(value="mature", label="Mature"),
    SourceFilterOption(value="milf", label="MILF"),
]

COMMON_TAGS = [
    "anime", "hentai", "creampie", "blowjob", "asian", "milf", "amateur",
    "anal", "hardcore", "japanese", "3d", "cosplay", "uncensored"
]


@registry.register
class XHamsterAdapter(BaseSourceAdapter):
    """
    Production-grade xHamster video database adapter with direct .mp4 stream parser,
    category/feed routing, and TLS fingerprint protection.
    """

    @property
    def manifest(self) -> SourceManifest:
        return SourceManifest(
            id=SOURCE_ID,
            name=SOURCE_NAME,
            version="2.0.0",
            description="Production-grade xHamster video database with direct MP4/HLS stream resolution.",
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
                        key="feed",
                        label="Sort By",
                        type="select",
                        default_value="best",
                        options=FEED_OPTIONS,
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
                        logger.debug(f"xHamster TLS impersonation target '{profile}' failed: {err}")

            logger.warning(f"xHamster request to '{url}' failed.")
            return ""

    @cached(ttl=300, key_prefix="xhamster:v2:search")
    async def search_titles(
        self, request: SourceBrowseRequest, context: SourceExecutionContext
    ) -> SourceBrowseResult:
        page = max(1, request.page)
        query = request.query.strip() if request.query else ""
        feed = request.filters.get("feed", "best")
        category = request.filters.get("category", "")
        tag = request.filters.get("tag", "").strip()

        search_query = query or tag
        if search_query:
            url = f"{BASE_URL}/search/{quote(search_query)}?page={page}"
        elif category:
            cat_slug = category.replace("/categories/", "").strip("/")
            url = f"{BASE_URL}/categories/{cat_slug}/{page}" if page > 1 else f"{BASE_URL}/categories/{cat_slug}"
        elif feed == "most_viewed":
            url = f"{BASE_URL}/most-viewed/{page}" if page > 1 else f"{BASE_URL}/most-viewed/"
        elif feed == "most_commented":
            url = f"{BASE_URL}/most-commented/{page}" if page > 1 else f"{BASE_URL}/most-commented/"
        elif feed == "newest":
            url = f"{BASE_URL}/newest/{page}" if page > 1 else f"{BASE_URL}/newest/"
        else:
            url = f"{BASE_URL}/best/{page}" if page > 1 else f"{BASE_URL}/best/"

        html = await self._fetch_html(context, url)
        if not html:
            return SourceBrowseResult(items=[], page=page, total_pages=1)

        soup = BeautifulSoup(html, "lxml")
        items = []
        seen = set()

        for a in soup.select("a[href*='/videos/']"):
            href = a.get("href", "")
            raw_title = a.get("title") or a.text.strip()

            if "/creators/" in href or "/channels/" in href or not raw_title:
                continue

            match = re.search(r"/videos/([a-z0-9-]+)", href, re.I)
            if not match:
                continue

            vid = match.group(1)
            if vid in seen or vid in ["best", "most-viewed", "newest", "most-commented"]:
                continue
            seen.add(vid)

            clean_title = re.sub(r"^\s*(?:\d+:\d+|\d+:\d+:\d+)\s*", "", raw_title).strip()

            img_el = a.select_one("img")
            thumb_url = img_el.get("src") or img_el.get("data-src") if img_el else None

            items.append(
                SourceBrowseItem(
                    source_id=SOURCE_ID,
                    source_title_id=vid,
                    canonical_url=urljoin(BASE_URL, href),
                    title=clean_title or f"Video {vid}",
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

    @cached(ttl=600, key_prefix="xhamster:v2:details")
    async def get_title_details(
        self, source_title_id: str, context: SourceExecutionContext
    ) -> SourceTitleDetails:
        canonical_url = f"{BASE_URL}/videos/{source_title_id}"
        html = await self._fetch_html(context, canonical_url)

        if not html:
            return SourceTitleDetails(
                source_id=SOURCE_ID,
                source_title_id=source_title_id,
                canonical_url=canonical_url,
                title=f"xHamster Video {source_title_id}",
                media_type="anime",
                tracking_mode="watch",
                content_summary=SourceTitleContentSummary(kind="episodes", total_count=1, available_count=1),
            )

        soup = BeautifulSoup(html, "lxml")
        title_el = soup.select_one("h1") or soup.select_one("title")
        raw_title = title_el.text.strip() if title_el else f"xHamster Video {source_title_id}"
        clean_title = raw_title.replace(" - xHamster", "").strip()

        img_el = soup.select_one("meta[property='og:image']")
        thumb_url = img_el.get("content") if img_el else None

        tags = [a.text.strip() for a in soup.select("a[href*='/categories/'], a[href*='/tags/']")]

        return SourceTitleDetails(
            source_id=SOURCE_ID,
            source_title_id=source_title_id,
            canonical_url=canonical_url,
            title=clean_title,
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

    @cached(ttl=600, key_prefix="xhamster:v2:playback")
    async def get_playback(
        self, source_title_id: str, content_id: str | None, context: SourceExecutionContext
    ) -> SourcePlayback:
        canonical_url = f"{BASE_URL}/videos/{source_title_id}"
        embed_url = f"{BASE_URL}/embed/{source_title_id}"
        html = await self._fetch_html(context, canonical_url)

        stream_url = embed_url
        if html:
            soup = BeautifulSoup(html, "lxml")
            video_el = soup.select_one("video source, video")
            if video_el and (video_el.get("src") or video_el.get("data-src")):
                stream_url = video_el.get("src") or video_el.get("data-src")
            else:
                match = re.search(r'"(?:fallbackUrl|mp4|hls)"\s*:\s*"([^"]+)"', html)
                if match:
                    stream_url = match.group(1).replace(r"\/", "/")

        details = await self.get_title_details(source_title_id, context)

        return SourcePlayback(
            content_id=content_id or source_title_id,
            title=details.title,
            stream_url=stream_url,
            mime_type="application/x-mpegURL" if stream_url.endswith(".m3u8") else "video/mp4",
            poster_url=details.thumbnail_url,
            canonical_url=canonical_url,
        )

    @cached(ttl=600, key_prefix="xhamster:v2:autocomplete")
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
                        description=f"xHamster tag query for '{tag}'",
                    )
                )
        return suggestions
