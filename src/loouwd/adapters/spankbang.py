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
            version="1.2.0",
            description="Browse SpankBang video database with Top/Popular and Trending feeds.",
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

        try:
            html = await context.fetch_text(url)
            soup = BeautifulSoup(html, "lxml")
            items = []

            for div in soup.select("div.video-item"):
                link = div.select_one("a.n") or div.select_one("a")
                img = div.select_one("img")
                if not link:
                    continue

                href = link.get("href", "")
                title = link.get("title") or link.text.strip()
                match = re.search(r"^/([a-z0-9]+)/video/", href, re.I)
                if not match:
                    continue

                vid = match.group(1)
                thumb_url = img.get("data-src") or img.get("src") if img else None

                items.append(
                    SourceBrowseItem(
                        source_id=SOURCE_ID,
                        source_title_id=vid,
                        canonical_url=urljoin(BASE_URL, href),
                        title=title,
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
        except Exception:
            return SourceBrowseResult(items=[], page=page, total_pages=1)

    @cached(ttl=600, key_prefix="spankbang:details")
    async def get_title_details(
        self, source_title_id: str, context: SourceExecutionContext
    ) -> SourceTitleDetails:
        canonical_url = f"{BASE_URL}/{source_title_id}/video/"
        try:
            html = await context.fetch_text(canonical_url)
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
        except Exception:
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
        try:
            html = await context.fetch_text(canonical_url)
            stream_match = re.search(r'var\s+stream_url\s*=\s*[\'"]([^\'"]+)[\'"]', html)
            stream_url = stream_match.group(1) if stream_match else embed_url

            return SourcePlayback(
                content_id=content_id or source_title_id,
                title=f"SpankBang Stream {source_title_id}",
                stream_url=stream_url,
                mime_type="video/mp4",
                canonical_url=canonical_url,
            )
        except Exception:
            return SourcePlayback(
                content_id=content_id or source_title_id,
                title=f"SpankBang Embed {source_title_id}",
                stream_url=embed_url,
                mime_type="video/mp4",
                canonical_url=canonical_url,
            )
