from typing import Any
from urllib.parse import quote
from loouwd.core.schemas import (
    SourceManifest,
    SourceAuthConfig,
    SourceFeatureSet,
    SourceBrowseConfig,
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
)
from loouwd.core.context import SourceExecutionContext
from loouwd.core.registry import registry, BaseSourceAdapter
from loouwd.core.cache import cached

SOURCE_ID = "omegascans"
SOURCE_NAME = "Omegascans"
BASE_URL = "https://omegascans.org"
FAVICON_URL = "https://omegascans.org/icon.png"
API_BASE_URL = "https://api.omegascans.org/query"


@registry.register
class OmegaScansAdapter(BaseSourceAdapter):
    @property
    def manifest(self) -> SourceManifest:
        return SourceManifest(
            id=SOURCE_ID,
            name=SOURCE_NAME,
            version="1.1.0",
            description="Browse Omegascans manhwa and manga releases through API.",
            author="Sirochan Pro",
            website=BASE_URL,
            icon_url=FAVICON_URL,
            supported_media_types=["manga"],
            auth=SourceAuthConfig(type="none"),
            features=SourceFeatureSet(
                browse=True, search=True, title_details=True, favorites=True
            ),
            browse_config=SourceBrowseConfig(supports_pagination=True, filters=[]),
        )

    @cached(ttl=300, key_prefix="omegascans:search")
    async def search_titles(
        self, request: SourceBrowseRequest, context: SourceExecutionContext
    ) -> SourceBrowseResult:
        page = max(1, request.page)
        query = request.query.strip() if request.query else ""

        url = f"{API_BASE_URL}?page={page}&per_page=20"
        if query:
            url += f"&query={quote(query)}"

        try:
            res = await context.fetch_json(url)
            data = res.get("data", [])
            meta = res.get("meta", {})
            total_pages = meta.get("last_page", 1)

            items = []
            for item in data:
                slug = item.get("series_slug") or str(item.get("id"))
                title = item.get("title", f"Series {slug}")
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
        except Exception:
            return SourceBrowseResult(items=[], page=page, total_pages=1)

    @cached(ttl=600, key_prefix="omegascans:details")
    async def get_title_details(
        self, source_title_id: str, context: SourceExecutionContext
    ) -> SourceTitleDetails:
        url = f"https://api.omegascans.org/series/{source_title_id}"
        try:
            item = await context.fetch_json(url)
            title = item.get("title", f"Series {source_title_id}")
            thumb = item.get("thumbnail")
            desc = item.get("description")
            alt = [item.get("alternative_names")] if item.get("alternative_names") else []
            chapters = item.get("chapters", [])

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
                total_chapters=len(chapters),
                content_summary=SourceTitleContentSummary(
                    kind="chapters",
                    total_count=len(chapters),
                    available_count=len(chapters),
                    in_app_capabilities=["reader"],
                ),
            )
        except Exception:
            return SourceTitleDetails(
                source_id=SOURCE_ID,
                source_title_id=source_title_id,
                canonical_url=f"{BASE_URL}/series/{source_title_id}",
                title=f"Series {source_title_id}",
                media_type="manga",
                tracking_mode="read",
                content_summary=SourceTitleContentSummary(kind="none", total_count=0, available_count=0),
            )

    async def get_title_content(
        self, source_title_id: str, context: SourceExecutionContext
    ) -> SourceTitleContent:
        url = f"https://api.omegascans.org/series/{source_title_id}"
        try:
            item = await context.fetch_json(url)
            raw_chaps = item.get("chapters", [])
            chapters = []
            for ch in raw_chaps:
                chap_slug = ch.get("chapter_slug") or str(ch.get("id"))
                chap_name = ch.get("chapter_name") or f"Chapter {chap_slug}"
                num = ch.get("chapter_number")

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
        except Exception:
            return SourceTitleContent(kind="chapters", chapters=[])

    @cached(ttl=600, key_prefix="omegascans:pages")
    async def get_reader_pages(
        self, source_title_id: str, content_id: str | None, context: SourceExecutionContext
    ) -> SourceReaderPages:
        chap_slug = content_id or "chapter-1"
        url = f"https://api.omegascans.org/chapter/{source_title_id}/{chap_slug}"
        try:
            res = await context.fetch_json(url)
            raw_images = res.get("images", [])
            pages = []
            for idx, img in enumerate(raw_images, 1):
                pages.append(
                    SourceTitlePage(
                        id=f"{chap_slug}-{idx}",
                        number=idx,
                        image_url=img if isinstance(img, str) else img.get("url", ""),
                    )
                )

            return SourceReaderPages(
                content_id=chap_slug,
                title=res.get("chapter_name") or f"Chapter {chap_slug}",
                pages=pages,
            )
        except Exception:
            return SourceReaderPages(content_id=chap_slug, pages=[])
