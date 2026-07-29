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

SOURCE_ID = "xhamster"
SOURCE_NAME = "xHamster"
BASE_URL = "https://xhamster.com"
FAVICON_URL = "https://xhamster.com/favicon.ico"

CATEGORY_OPTIONS = [
    SourceFilterOption(value="/categories/amateur", label="Amateur"),
    SourceFilterOption(value="/categories/mature", label="Mature"),
    SourceFilterOption(value="/categories/anal", label="Anal"),
    SourceFilterOption(value="/categories/blowjob", label="Blowjob"),
    SourceFilterOption(value="/categories/creampie", label="Creampie"),
    SourceFilterOption(value="/categories/hentai", label="Hentai"),
]


@registry.register
class XHamsterAdapter(BaseSourceAdapter):
    @property
    def manifest(self) -> SourceManifest:
        return SourceManifest(
            id=SOURCE_ID,
            name=SOURCE_NAME,
            version="1.2.0",
            description="Browse xHamster video catalog.",
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
                        key="category",
                        label="Category",
                        type="select",
                        options=CATEGORY_OPTIONS,
                    )
                ],
            ),
        )

    @cached(ttl=300, key_prefix="xhamster:search")
    async def search_titles(
        self, request: SourceBrowseRequest, context: SourceExecutionContext
    ) -> SourceBrowseResult:
        page = max(1, request.page)
        query = request.query.strip() if request.query else ""
        category = request.filters.get("category")

        if query:
            url = f"{BASE_URL}/search/{quote(query)}?page={page}"
        elif category:
            url = f"{BASE_URL}{category}/{page}" if page > 1 else f"{BASE_URL}{category}"
        else:
            url = f"{BASE_URL}/{page}" if page > 1 else BASE_URL

        try:
            html = await context.fetch_text(url)
            soup = BeautifulSoup(html, "lxml")
            items = []

            for div in soup.select("div.thumb-list__item, a.video-thumb-info__name"):
                link = div if div.name == "a" else div.select_one("a.video-thumb-info__name") or div.select_one("a[href*='/videos/']")
                img = div.select_one("img") if div.name != "a" else None
                if not link:
                    continue

                href = link.get("href", "")
                title = link.text.strip()
                match = re.search(r"/videos/([a-z0-9-]+)", href, re.I)
                if not match:
                    continue

                vid = match.group(1)
                thumb_url = img.get("src") or img.get("data-src") if img else None

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

    @cached(ttl=600, key_prefix="xhamster:details")
    async def get_title_details(
        self, source_title_id: str, context: SourceExecutionContext
    ) -> SourceTitleDetails:
        canonical_url = f"{BASE_URL}/videos/{source_title_id}"
        try:
            html = await context.fetch_text(canonical_url)
            soup = BeautifulSoup(html, "lxml")

            title_el = soup.select_one("h1") or soup.select_one("title")
            title = title_el.text.strip() if title_el else f"Video {source_title_id}"

            img_el = soup.select_one("meta[property='og:image']")
            thumb_url = img_el.get("content") if img_el else None

            tags = [a.text.strip() for a in soup.select("a[href*='/categories/']")]

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

    @cached(ttl=600, key_prefix="xhamster:playback")
    async def get_playback(
        self, source_title_id: str, content_id: str | None, context: SourceExecutionContext
    ) -> SourcePlayback:
        canonical_url = f"{BASE_URL}/videos/{source_title_id}"
        embed_url = f"{BASE_URL}/embed/{source_title_id}"
        try:
            html = await context.fetch_text(canonical_url)
            # Match window.initials or MP4 stream links
            match = re.search(r'"fallbackUrl"\s*:\s*"([^"]+)"', html) or re.search(r'"quality_720p"\s*:\s*"([^"]+)"', html)
            stream_url = match.group(1).replace("\\/", "/") if match else embed_url

            return SourcePlayback(
                content_id=content_id or source_title_id,
                title=f"xHamster Stream {source_title_id}",
                stream_url=stream_url,
                mime_type="video/mp4",
                canonical_url=canonical_url,
            )
        except Exception:
            return SourcePlayback(
                content_id=content_id or source_title_id,
                title=f"xHamster Embed {source_title_id}",
                stream_url=embed_url,
                mime_type="video/mp4",
                canonical_url=canonical_url,
            )
