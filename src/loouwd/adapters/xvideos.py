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

SOURCE_ID = "xvideos"
SOURCE_NAME = "XVideos"
BASE_URL = "https://www.xvideos.com"
FAVICON_URL = "https://www.xvideos.com/favicon.ico"

SECTION_OPTIONS = [
    SourceFilterOption(value="/c/Amateur-65", label="Amateur"),
    SourceFilterOption(value="/c/Anal-12", label="Anal"),
    SourceFilterOption(value="/c/Asian_Woman-32", label="Asian"),
    SourceFilterOption(value="/c/Blowjob-15", label="Blowjob"),
    SourceFilterOption(value="/c/Creampie-40", label="Creampie"),
    SourceFilterOption(value="/c/Teen-13", label="Teen"),
    SourceFilterOption(value="/c/MILF-38", label="MILF"),
]


@registry.register
class XVideosAdapter(BaseSourceAdapter):
    @property
    def manifest(self) -> SourceManifest:
        return SourceManifest(
            id=SOURCE_ID,
            name=SOURCE_NAME,
            version="1.2.0",
            description="Browse XVideos video database with async high-speed parser.",
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
                        key="section",
                        label="Category",
                        type="select",
                        options=SECTION_OPTIONS,
                    )
                ],
            ),
        )

    @cached(ttl=300, key_prefix="xvideos:search")
    async def search_titles(
        self, request: SourceBrowseRequest, context: SourceExecutionContext
    ) -> SourceBrowseResult:
        page = max(1, request.page)
        query = request.query.strip() if request.query else ""
        section = request.filters.get("section")

        if query:
            url = f"{BASE_URL}/?k={quote(query)}"
            if page > 1:
                url += f"&p={page - 1}"
        elif section:
            url = f"{BASE_URL}{section}"
            if page > 1:
                url += f"/{page - 1}"
        else:
            url = f"{BASE_URL}/new/{page - 1}" if page > 1 else BASE_URL

        try:
            html = await context.fetch_text(url)
            soup = BeautifulSoup(html, "lxml")
            items = []

            for div in soup.select("div.thumb-block"):
                link = div.select_one("p.title a")
                img = div.select_one("div.thumb img")
                if not link:
                    continue

                href = link.get("href", "")
                title = link.get("title") or link.text.strip()
                vid_match = re.search(r"/video\.([a-z0-9]+)", href, re.I)
                if not vid_match:
                    continue

                vid = vid_match.group(1)
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
                total_pages=page + 5,  # estimated pagination
                applied_filters=request.filters,
            )
        except Exception:
            return SourceBrowseResult(items=[], page=page, total_pages=1)

    @cached(ttl=600, key_prefix="xvideos:details")
    async def get_title_details(
        self, source_title_id: str, context: SourceExecutionContext
    ) -> SourceTitleDetails:
        canonical_url = f"{BASE_URL}/video.{source_title_id}/"
        try:
            html = await context.fetch_text(canonical_url)
            soup = BeautifulSoup(html, "lxml")

            title_el = soup.select_one("h2.page-title") or soup.select_one("title")
            title = title_el.text.strip() if title_el else f"Video {source_title_id}"

            img_el = soup.select_one("meta[property='og:image']")
            thumb_url = img_el.get("content") if img_el else None

            tags = [a.text.strip() for a in soup.select("a.btn-default")]

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

    @cached(ttl=600, key_prefix="xvideos:playback")
    async def get_playback(
        self, source_title_id: str, content_id: str | None, context: SourceExecutionContext
    ) -> SourcePlayback:
        embed_url = f"{BASE_URL}/embedframe/{source_title_id}"
        canonical_url = f"{BASE_URL}/video.{source_title_id}/"
        try:
            html = await context.fetch_text(canonical_url)
            # Find setVideoUrlHigh or setVideoUrlLow in JS script
            match_high = re.search(r"html5player\.setVideoUrlHigh\('([^']+)'\)", html)
            match_low = re.search(r"html5player\.setVideoUrlLow\('([^']+)'\)", html)

            stream_url = match_high.group(1) if match_high else (match_low.group(1) if match_low else embed_url)

            return SourcePlayback(
                content_id=content_id or source_title_id,
                title=f"XVideos Stream {source_title_id}",
                stream_url=stream_url,
                mime_type="video/mp4",
                canonical_url=canonical_url,
            )
        except Exception:
            return SourcePlayback(
                content_id=content_id or source_title_id,
                title=f"XVideos Embed {source_title_id}",
                stream_url=embed_url,
                mime_type="video/mp4",
                canonical_url=canonical_url,
            )
