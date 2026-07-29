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

SOURCE_ID = "rule34world"
SOURCE_NAME = "Rule34world"
BASE_URL = "https://rule34.world"
FAVICON_URL = "https://rule34.world/favicon.ico"

TAG_OPTIONS = [
    SourceFilterOption(value="video", label="Video"),
    SourceFilterOption(value="animated", label="Animated"),
    SourceFilterOption(value="3d", label="3D"),
    SourceFilterOption(value="netorare", label="Netorare"),
    SourceFilterOption(value="overwatch", label="Overwatch"),
    SourceFilterOption(value="genshin_impact", label="Genshin Impact"),
]


@registry.register
class Rule34WorldAdapter(BaseSourceAdapter):
    @property
    def manifest(self) -> SourceManifest:
        return SourceManifest(
            id=SOURCE_ID,
            name=SOURCE_NAME,
            version="1.2.0",
            description="Browse Rule34.world animated and video content.",
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
                        key="tag",
                        label="Tag",
                        type="select",
                        options=TAG_OPTIONS,
                    )
                ],
            ),
        )

    @cached(ttl=300, key_prefix="rule34world:search")
    async def search_titles(
        self, request: SourceBrowseRequest, context: SourceExecutionContext
    ) -> SourceBrowseResult:
        page = max(1, request.page)
        query = request.query.strip() if request.query else ""
        tag = request.filters.get("tag")

        if query:
            url = f"{BASE_URL}/posts?search={quote(query)}&page={page}"
        elif tag:
            url = f"{BASE_URL}/posts?tags={quote(str(tag))}&page={page}"
        else:
            url = f"{BASE_URL}/posts?page={page}"

        try:
            html = await context.fetch_text(url)
            soup = BeautifulSoup(html, "lxml")
            items = []

            for div in soup.select("a.post-card, div.post-item, a[href*='/post/']"):
                href = div.get("href", "")
                title = div.get("title") or div.text.strip() or "Rule34 Post"
                match = re.search(r"/post/([a-z0-9-]+)", href, re.I)
                if not match:
                    continue

                pid = match.group(1)
                img = div.select_one("img")
                thumb_url = img.get("src") or img.get("data-src") if img else None

                items.append(
                    SourceBrowseItem(
                        source_id=SOURCE_ID,
                        source_title_id=pid,
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

    @cached(ttl=600, key_prefix="rule34world:details")
    async def get_title_details(
        self, source_title_id: str, context: SourceExecutionContext
    ) -> SourceTitleDetails:
        canonical_url = f"{BASE_URL}/post/{source_title_id}"
        try:
            html = await context.fetch_text(canonical_url)
            soup = BeautifulSoup(html, "lxml")

            title_el = soup.select_one("h1") or soup.select_one("title")
            title = title_el.text.strip() if title_el else f"Post {source_title_id}"

            img_el = soup.select_one("meta[property='og:image']")
            thumb_url = img_el.get("content") if img_el else None

            tags = [a.text.strip() for a in soup.select("a[href*='tag']")]

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
                title=f"Post {source_title_id}",
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

    @cached(ttl=600, key_prefix="rule34world:playback")
    async def get_playback(
        self, source_title_id: str, content_id: str | None, context: SourceExecutionContext
    ) -> SourcePlayback:
        canonical_url = f"{BASE_URL}/post/{source_title_id}"
        try:
            html = await context.fetch_text(canonical_url)
            soup = BeautifulSoup(html, "lxml")
            video_el = soup.select_one("video source")
            stream_url = video_el.get("src") if video_el else canonical_url

            return SourcePlayback(
                content_id=content_id or source_title_id,
                title=f"Rule34 Stream {source_title_id}",
                stream_url=stream_url,
                mime_type="video/mp4",
                canonical_url=canonical_url,
            )
        except Exception:
            return SourcePlayback(
                content_id=content_id or source_title_id,
                title=f"Rule34 Video {source_title_id}",
                stream_url=canonical_url,
                mime_type="video/mp4",
                canonical_url=canonical_url,
            )
