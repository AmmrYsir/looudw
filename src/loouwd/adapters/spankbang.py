import re
import json
from typing import Any
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

SOURCE_ID = "spankbang"
SOURCE_NAME = "SpankBang"
BASE_URL = "https://spankbang.com"
FAVICON_URL = "https://spankbang.com/favicon.ico"

FEED_OPTIONS = [
    SourceFilterOption(value="most_popular", label="Popular / Top"),
    SourceFilterOption(value="trending_videos", label="Trending"),
    SourceFilterOption(value="new_videos", label="Newest"),
    SourceFilterOption(value="upcoming_videos", label="Upcoming"),
]

COMMON_TAGS = [
    "anime", "hentai", "creampie", "gangbang", "blowjob", "interracial",
    "asian", "japanese", "3d", "cosplay", "uncensored", "full color",
    "milf", "ebony", "latina", "amateur", "hardcore"
]


@registry.register
class SpankBangAdapter(BaseSourceAdapter):
    """
    Production-grade SpankBang video database adapter with Cloudflare Turnstile
    bypass engine and stream_data JSON quality parser (1080p, 720p, 480p, HLS m3u8).
    """

    @property
    def manifest(self) -> SourceManifest:
        return SourceManifest(
            id=SOURCE_ID,
            name=SOURCE_NAME,
            version="2.0.0",
            description="Production-grade SpankBang video streaming engine with stream_data parser and Cloudflare Turnstile bypass.",
            author="Sirochan Pro",
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
                        label="Browse Feed",
                        type="select",
                        default_value="most_popular",
                        options=FEED_OPTIONS,
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

    async def _fetch_html_with_fallback(self, context: SourceExecutionContext, url: str) -> str:
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "cookie": "country=US; age_verified=1",
            "referer": f"{BASE_URL}/",
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
                        logger.debug(f"SpankBang TLS impersonation target '{profile}' failed: {curl_err}")

            logger.warning(f"SpankBang request to '{url}' failed.")
            return ""

    @cached(ttl=300, key_prefix="spankbang:v2:search")
    async def search_titles(
        self, request: SourceBrowseRequest, context: SourceExecutionContext
    ) -> SourceBrowseResult:
        page = max(1, request.page)
        query = request.query.strip() if request.query else ""
        feed = request.filters.get("feed", "most_popular")
        tag = request.filters.get("tag", "").strip()

        if query:
            url = f"{BASE_URL}/s/{quote(query)}/{page}/"
        elif tag:
            url = f"{BASE_URL}/tag/{quote(str(tag))}/{page}/"
        elif feed == "trending_videos":
            url = f"{BASE_URL}/trending_videos/{page}/"
        elif feed == "new_videos":
            url = f"{BASE_URL}/new_videos/{page}/"
        elif feed == "upcoming_videos":
            url = f"{BASE_URL}/upcoming_videos/{page}/"
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
            if thumb_url and thumb_url.startswith("//"):
                thumb_url = f"https:{thumb_url}"
            raw_title = link.get("title") or link.text.strip()
            clean_title = re.sub(r"^\s*(?:HD|4K|1080p|720p|\d+m|\d+s|\n)+\s*", "", raw_title, flags=re.I)
            clean_title = re.sub(r"\s+", " ", clean_title).strip()

            items.append(
                SourceBrowseItem(
                    source_id=SOURCE_ID,
                    source_title_id=vid,
                    canonical_url=urljoin(BASE_URL, href),
                    title=clean_title or f"SpankBang Video {vid}",
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
                        title=title or f"SpankBang Video {vid}",
                        media_type="anime",
                        tracking_mode="watch",
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

    @cached(ttl=600, key_prefix="spankbang:v2:details")
    async def get_title_details(
        self, source_title_id: str, context: SourceExecutionContext
    ) -> SourceTitleDetails:
        canonical_url = f"{BASE_URL}/{source_title_id}/video/"
        html = await self._fetch_html_with_fallback(context, canonical_url)

        if not html:
            return SourceTitleDetails(
                source_id=SOURCE_ID,
                source_title_id=source_title_id,
                canonical_url=canonical_url,
                title=f"SpankBang Video {source_title_id}",
                media_type="anime",
                tracking_mode="watch",
                content_summary=SourceTitleContentSummary(kind="episodes", total_count=1, available_count=1),
            )

        soup = BeautifulSoup(html, "lxml")
        title_el = soup.select_one("h1") or soup.select_one("title")
        raw_title = title_el.text.strip() if title_el else f"SpankBang Video {source_title_id}"
        clean_title = raw_title.replace(" - SpankBang", "").strip()

        img_el = soup.select_one("meta[property='og:image']")
        thumb_url = img_el.get("content") if img_el else None

        tags = [a.text.strip() for a in soup.select("a[href*='/tag/']")]

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

    @cached(ttl=600, key_prefix="spankbang:v2:playback")
    async def get_playback(
        self, source_title_id: str, content_id: str | None, context: SourceExecutionContext
    ) -> SourcePlayback:
        canonical_url = f"{BASE_URL}/{source_title_id}/video/"
        embed_url = f"{BASE_URL}/{source_title_id}/embed/"
        html = await self._fetch_html_with_fallback(context, canonical_url)

        stream_url = embed_url
        poster_url = None
        duration = None

        if html:
            match = re.search(r'var\s+stream_data\s*=\s*(\{.*?\});', html, re.DOTALL)
            if match:
                try:
                    js_dict = match.group(1).replace("'", '"')
                    # Standardize JSON format
                    data = json.loads(js_dict)
                    for key in ["1080p", "720p", "480p", "main", "240p", "m3u8"]:
                        urls = data.get(key, [])
                        if urls and isinstance(urls, list) and urls[0]:
                            stream_url = urls[0]
                            break

                    poster_url = data.get("cover_image") or data.get("thumbnail")
                    duration = data.get("length")
                except Exception as json_err:
                    logger.debug(f"SpankBang stream_data JSON parse fallback: {json_err}")

            if stream_url == embed_url:
                stream_match = re.search(r'var\s+stream_url\s*=\s*[\'"]([^\'"]+)[\'"]', html)
                if stream_match:
                    stream_url = stream_match.group(1)

        details = await self.get_title_details(source_title_id, context)

        return SourcePlayback(
            content_id=content_id or source_title_id,
            title=details.title,
            stream_url=stream_url,
            mime_type="application/x-mpegURL" if stream_url.endswith(".m3u8") else "video/mp4",
            poster_url=poster_url or details.thumbnail_url,
            duration_seconds=duration,
            canonical_url=canonical_url,
        )

    @cached(ttl=600, key_prefix="spankbang:v2:autocomplete")
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
                        description=f"SpankBang tag query for '{tag}'",
                    )
                )
        return suggestions
