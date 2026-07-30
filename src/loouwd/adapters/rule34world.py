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

SOURCE_ID = "rule34world"
SOURCE_NAME = "Rule34world"
BASE_URL = "https://rule34.world"
FAVICON_URL = "/static/icons/rule34world.ico"

COMMON_TAGS = [
    "3d", "animated", "overwatch", "genshin impact", "league of legends",
    "honkai star rail", "video", "hentai", "anal", "blowjob", "paizuri",
    "creampie", "big breasts", "uncensored", "full color", "blender"
]


@registry.register
class Rule34WorldAdapter(BaseSourceAdapter):
    """
    Production-grade Rule34.world adapter supporting video stream extraction,
    dynamic tag searching, and TLS fingerprint protection.
    """

    @property
    def manifest(self) -> SourceManifest:
        return SourceManifest(
            id=SOURCE_ID,
            name=SOURCE_NAME,
            version="2.0.0",
            description="Production-grade Rule34.world video and art catalog engine.",
            website=BASE_URL,
            icon_url=FAVICON_URL,
            supported_media_types=["anime", "manga"],
            auth=SourceAuthConfig(type="none"),
            features=SourceFeatureSet(
                browse=True, search=True, title_details=True, favorites=True, tag_autocomplete=True
            ),
            browse_config=SourceBrowseConfig(
                supports_pagination=True,
                filters=[
                    SourceFilterDefinition(
                        key="tag",
                        label="Tag Query (e.g. '3d', 'overwatch')",
                        type="text",
                        default_value="",
                    )
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
                            if res.status_code == 200 and len(res.text) > 1000:
                                return res.text
                    except Exception as err:
                        logger.debug(f"Rule34World TLS impersonation target '{profile}' failed: {err}")

            logger.warning(f"Rule34World request to '{url}' failed.")
            return ""

    @cached(ttl=300, key_prefix="rule34world:v2:search")
    async def search_titles(
        self, request: SourceBrowseRequest, context: SourceExecutionContext
    ) -> SourceBrowseResult:
        page = max(1, request.page)
        query = request.query.strip() if request.query else ""
        tag = request.filters.get("tag", "").strip()

        search_query = query or tag
        if search_query:
            url = f"{BASE_URL}/posts?search={quote(search_query)}&page={page}"
        else:
            url = f"{BASE_URL}/posts?page={page}" if page > 1 else f"{BASE_URL}/"

        html = await self._fetch_html(context, url)
        if not html:
            return SourceBrowseResult(items=[], page=page, total_pages=1)

        soup = BeautifulSoup(html, "lxml")
        items = []
        seen = set()

        for a in soup.select("a[href*='/post/']"):
            href = a.get("href", "")
            title = a.get("title") or a.text.strip()
            match = re.search(r"/post/([0-9]+)", href, re.I)
            if not match:
                continue

            pid = match.group(1)
            if pid in seen:
                continue
            seen.add(pid)

            img_el = a.select_one("img")
            thumb_url = img_el.get("src") or img_el.get("data-src") if img_el else None
            if thumb_url and not thumb_url.startswith("http"):
                thumb_url = urljoin(BASE_URL, thumb_url)
            
            raw_title = a.get("title") or a.text.strip()
            clean_title = re.sub(r"^play_arrow\s*\d+:\d+\s*", "", raw_title).strip()

            items.append(
                SourceBrowseItem(
                    source_id=SOURCE_ID,
                    source_title_id=pid,
                    canonical_url=urljoin(BASE_URL, href),
                    title=clean_title or f"Rule34 Post {pid}",
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

    @cached(ttl=600, key_prefix="rule34world:v2:details")
    async def get_title_details(
        self, source_title_id: str, context: SourceExecutionContext
    ) -> SourceTitleDetails:
        canonical_url = f"{BASE_URL}/post/{source_title_id}"
        html = await self._fetch_html(context, canonical_url)

        if not html:
            return SourceTitleDetails(
                source_id=SOURCE_ID,
                source_title_id=source_title_id,
                canonical_url=canonical_url,
                title=f"Rule34 Post {source_title_id}",
                media_type="anime",
                tracking_mode="watch",
                content_summary=SourceTitleContentSummary(kind="episodes", total_count=1, available_count=1),
            )

        soup = BeautifulSoup(html, "lxml")

        title_el = soup.select_one("h1") or soup.select_one("title")
        raw_title = title_el.text.strip() if title_el else f"Rule34 Post {source_title_id}"
        clean_title = raw_title.replace(" - Rule 34 World", "").strip()

        img_el = soup.select_one("meta[property='og:image']")
        thumb_url = img_el.get("content") if img_el else None

        tags = [t.strip() for t in clean_title.split(",") if t.strip()]

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

    @cached(ttl=600, key_prefix="rule34world:v2:playback")
    async def get_playback(
        self, source_title_id: str, content_id: str | None, context: SourceExecutionContext
    ) -> SourcePlayback:
        canonical_url = f"{BASE_URL}/post/{source_title_id}"
        html = await self._fetch_html(context, canonical_url)

        stream_url = canonical_url
        if html:
            soup = BeautifulSoup(html, "lxml")
            video_el = soup.select_one("video source") or soup.select_one("video")
            if video_el:
                src = video_el.get("src") or video_el.get("data-src")
                if src:
                    stream_url = urljoin(BASE_URL, src)

        details = await self.get_title_details(source_title_id, context)

        return SourcePlayback(
            content_id=content_id or source_title_id,
            title=details.title,
            stream_url=stream_url,
            mime_type="video/mp4",
            poster_url=details.thumbnail_url,
            canonical_url=canonical_url,
        )

    @cached(ttl=600, key_prefix="rule34world:v2:autocomplete")
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
                        description=f"Rule34 tag query for '{tag}'",
                    )
                )
        return suggestions
