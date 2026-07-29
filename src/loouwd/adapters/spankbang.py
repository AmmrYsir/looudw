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

SOURCE_ID = "spankbang"
SOURCE_NAME = "SpankBang"
BASE_URL = "https://spankbang.com"
FAVICON_URL = "https://spankbang.com/favicon.ico"

FEED_OPTIONS = [
    SourceFilterOption(value="most_popular", label="Popular / Top"),
    SourceFilterOption(value="trending_videos", label="Trending"),
    SourceFilterOption(value="new_videos", label="Newest"),
]

TAG_OPTIONS = [
    SourceFilterOption(value="", label="All Tags"),
    SourceFilterOption(value="anime", label="Anime"),
    SourceFilterOption(value="creampie", label="Creampie"),
    SourceFilterOption(value="gangbang", label="Gangbang"),
    SourceFilterOption(value="hentai", label="Hentai"),
    SourceFilterOption(value="blowjob", label="Blowjob"),
    SourceFilterOption(value="interracial", label="Interracial"),
]


@registry.register
class SpankBangAdapter(BaseSourceAdapter):
    @property
    def manifest(self) -> SourceManifest:
        return SourceManifest(
            id=SOURCE_ID,
            name=SOURCE_NAME,
            version="1.3.1",
            description="Browse SpankBang video database with Cloudflare bypass engine.",
            author="Sirochan Pro",
            website=BASE_URL,
            icon_url=FAVICON_URL,
            supported_media_types=["anime"],
            auth=SourceAuthConfig(type="none"),
            features=SourceFeatureSet(
                browse=True, search=True, title_details=True, favorites=True
            ),
            browse_config=SourceBrowseConfig(
                supports_pagination=True,
                filters=[
                    SourceFilterDefinition(
                        key="feed",
                        label="Browse Feed",
                        type="select",
                        default_value="most_popular",
                        options=FEED_OPTIONS,
                    ),
                    SourceFilterDefinition(
                        key="tag",
                        label="Tag",
                        type="select",
                        default_value="",
                        options=TAG_OPTIONS,
                    ),
                ],
            ),
        )

    async def _fetch_html_with_fallback(self, context: SourceExecutionContext, url: str) -> str:
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "cookie": "country=US; age_verified=1",
            "referer": BASE_URL,
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        }
        try:
            return await context.fetch_text(url, headers=headers)
        except Exception:
            if HAS_CURL_CFFI:
                for profile in ["safari15_5", "safari17_0", "chrome120"]:
                    try:
                        async with CurlSession(impersonate=profile, headers=headers) as session:
                            res = await session.get(url, timeout=12)
                            if res.status_code == 200 and len(res.text) > 10000:
                                return res.text
                    except Exception as curl_err:
                        logger.debug(f"TLS impersonation target '{profile}' failed: {curl_err}")

            logger.warning(f"SpankBang at '{url}' request could not bypass Cloudflare Turnstile.")
            return ""

    @cached(ttl=300, key_prefix="spankbang:search")
    async def search_titles(
        self, request: SourceBrowseRequest, context: SourceExecutionContext
    ) -> SourceBrowseResult:
        page = max(1, request.page)
        query = request.query.strip() if request.query else ""
        feed = request.filters.get("feed", "most_popular")
        tag = request.filters.get("tag", "")

        if query:
            url = f"{BASE_URL}/s/{quote(query)}/{page}/"
        elif tag:
            url = f"{BASE_URL}/tag/{quote(str(tag))}/{page}/"
        elif feed == "trending_videos":
            url = f"{BASE_URL}/trending_videos/{page}/"
        elif feed == "new_videos":
            url = f"{BASE_URL}/new_videos/{page}/"
        else:
            url = f"{BASE_URL}/most_popular/{page}/"

        html = await self._fetch_html_with_fallback(context, url)
        if not html:
            return SourceBrowseResult(
                items=[],
                page=page,
                total_pages=1,
                applied_filters=request.filters,
            )

        soup = BeautifulSoup(html, "lxml")
        items = []
        seen_ids = set()

        video_blocks = soup.select('div[data-testid="video-item"], div.video-item, div.js-video-item, div.video_item')
        for div in video_blocks:
            link = div.select_one("a[href*='/video/']") or div.select_one("a.n") or div.select_one("a")
            img = div.select_one("img")
            if not link:
                continue

            href = link.get("href", "")
            title = link.get("title") or link.text.strip()
            match = re.search(r"/([\da-z]+)/(?:video|play|embed)", href, re.I)
            if not match:
                continue

            vid = match.group(1)
            if vid in seen_ids:
                continue
            seen_ids.add(vid)

            thumb_url = img.get("data-src") or img.get("src") if img else None

            items.append(
                SourceBrowseItem(
                    source_id=SOURCE_ID,
                    source_title_id=vid,
                    canonical_url=urljoin(BASE_URL, href),
                    title=title or f"Video {vid}",
                    media_type="anime",
                    tracking_mode="watch",
                    thumbnail_url=thumb_url,
                    total_episodes=1,
                )
            )

        if not items:
            for a in soup.select('a[href*="/video/"]'):
                href = a.get("href", "")
                title = a.get("title") or a.text.strip()
                match = re.search(r"/([\da-z]+)/(?:video|play|embed)", href, re.I)
                if not match:
                    continue

                vid = match.group(1)
                if vid in seen_ids:
                    continue
                seen_ids.add(vid)

                items.append(
                    SourceBrowseItem(
                        source_id=SOURCE_ID,
                        source_title_id=vid,
                        canonical_url=urljoin(BASE_URL, href),
                        title=title or f"Video {vid}",
                        media_type="anime",
                        tracking_mode="read" if "manga" in href else "watch",
                        thumbnail_url=None,
                        total_episodes=1,
                    )
                )

        return SourceBrowseResult(
            items=items,
            page=page,
            total_pages=page + 5,
            applied_filters=request.filters,
        )

    @cached(ttl=600, key_prefix="spankbang:details")
    async def get_title_details(
        self, source_title_id: str, context: SourceExecutionContext
    ) -> SourceTitleDetails:
        canonical_url = f"{BASE_URL}/{source_title_id}/video/"
        html = await self._fetch_html_with_fallback(context, canonical_url)
        if html:
            soup = BeautifulSoup(html, "lxml")
            title_el = soup.select_one("h1") or soup.select_one("title")
            title = title_el.text.strip() if title_el else f"Video {source_title_id}"
            img_el = soup.select_one("meta[property='og:image']")
            thumb_url = img_el.get("content") if img_el else None
            tags = [a.text.strip() for a in soup.select("a[href*='/tag/']")]

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

        return SourceTitleDetails(
            source_id=SOURCE_ID,
            source_title_id=source_title_id,
            canonical_url=canonical_url,
            title=f"Video {source_title_id}",
            media_type="anime",
            tracking_mode="watch",
            content_summary=SourceTitleContentSummary(kind="episodes", total_count=1, available_count=1),
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

    @cached(ttl=600, key_prefix="spankbang:playback")
    async def get_playback(
        self, source_title_id: str, content_id: str | None, context: SourceExecutionContext
    ) -> SourcePlayback:
        embed_url = f"{BASE_URL}/{source_title_id}/embed/"
        canonical_url = f"{BASE_URL}/{source_title_id}/video/"
        html = await self._fetch_html_with_fallback(context, canonical_url)
        if html:
            stream_match = re.search(r'var\s+stream_url\s*=\s*[\'"]([^\'"]+)[\'"]', html)
            stream_url = stream_match.group(1) if stream_match else embed_url
            return SourcePlayback(
                content_id=content_id or source_title_id,
                title=f"SpankBang Stream {source_title_id}",
                stream_url=stream_url,
                mime_type="video/mp4",
                canonical_url=canonical_url,
            )

        return SourcePlayback(
            content_id=content_id or source_title_id,
            title=f"SpankBang Embed {source_title_id}",
            stream_url=embed_url,
            mime_type="video/mp4",
            canonical_url=canonical_url,
        )
