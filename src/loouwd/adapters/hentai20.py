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
    SourceTitleChapter,
    SourceReaderPages,
    SourcePlayback,
    SourceTitlePage,
    SourceTitleContentSummary,
)
from loouwd.core.context import SourceExecutionContext
from loouwd.core.registry import registry, BaseSourceAdapter
from loouwd.core.cache import cached

SOURCE_ID = "hentai20"
SOURCE_NAME = "Hentai20.io"
BASE_URL = "https://hentai20.io"
FAVICON_URL = "https://hentai20.io/wp-content/uploads/2024/05/cropped-210da20ddb1be20edd43583bcaf1061f628cbc16-300x300.jpg"

GENRE_OPTIONS = [
    SourceFilterOption(value="2274", label="Adult"),
    SourceFilterOption(value="4647", label="Doujinshi"),
    SourceFilterOption(value="2285", label="Ecchi"),
    SourceFilterOption(value="3351", label="Hentai"),
    SourceFilterOption(value="21", label="Manhwa Hentai"),
    SourceFilterOption(value="12", label="Mature"),
    SourceFilterOption(value="7", label="Romance"),
]


@registry.register
class Hentai20Adapter(BaseSourceAdapter):
    @property
    def manifest(self) -> SourceManifest:
        return SourceManifest(
            id=SOURCE_ID,
            name=SOURCE_NAME,
            version="1.3.0",
            description="Browse Hentai20 doujinshi and manga.",
            author="Sirochan Pro",
            website=BASE_URL,
            icon_url=FAVICON_URL,
            supported_media_types=["manga"],
            auth=SourceAuthConfig(type="none"),
            features=SourceFeatureSet(
                browse=True, search=True, title_details=True, favorites=True
            ),
            browse_config=SourceBrowseConfig(
                supports_pagination=True,
                filters=[
                    SourceFilterDefinition(
                        key="genre",
                        label="Genre",
                        type="select",
                        options=GENRE_OPTIONS,
                    )
                ],
            ),
        )

    @cached(ttl=300, key_prefix="hentai20:search")
    async def search_titles(
        self, request: SourceBrowseRequest, context: SourceExecutionContext
    ) -> SourceBrowseResult:
        page = max(1, request.page)
        query = request.query.strip() if request.query else ""
        genre = request.filters.get("genre")

        if query:
            url = f"{BASE_URL}/page/{page}/?s={quote(query)}&post_type=wp-manga" if page > 1 else f"{BASE_URL}/?s={quote(query)}&post_type=wp-manga"
        elif genre:
            url = f"{BASE_URL}/manga-genre/{genre}/page/{page}/" if page > 1 else f"{BASE_URL}/manga-genre/{genre}/"
        else:
            url = f"{BASE_URL}/manga/page/{page}/" if page > 1 else f"{BASE_URL}/manga/"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        try:
            html = await context.fetch_text(url, headers=headers)
            soup = BeautifulSoup(html, "lxml")
            items = []
            seen = set()

            for div in soup.select("div.c-tabs-item__content, div.page-item-detail, div.item-thumb, div.badge-pos-2"):
                link = div.select_one("h3.h4 a") or div.select_one("a[href*='/manga/']")
                img = div.select_one("img")
                if not link:
                    continue

                href = link.get("href", "")
                title = link.text.strip()
                match = re.search(r"/manga/([a-z0-9-]+)", href, re.I)
                if not match or match.group(1) == "page":
                    continue

                slug = match.group(1)
                if slug in seen:
                    continue
                seen.add(slug)

                thumb_url = img.get("src") or img.get("data-src") if img else None

                items.append(
                    SourceBrowseItem(
                        source_id=SOURCE_ID,
                        source_title_id=slug,
                        canonical_url=urljoin(BASE_URL, href),
                        title=title or f"Manga {slug}",
                        media_type="manga",
                        tracking_mode="read",
                        thumbnail_url=thumb_url,
                        total_chapters=1,
                    )
                )

            # Fallback direct link selector
            if not items:
                for a in soup.select('a[href*="/manga/"]'):
                    href = a.get("href", "")
                    title = a.get("title") or a.text.strip()
                    match = re.search(r"/manga/([a-z0-9-]+)", href, re.I)
                    if not match or match.group(1) == "page":
                        continue

                    slug = match.group(1)
                    if slug in seen:
                        continue
                    seen.add(slug)

                    items.append(
                        SourceBrowseItem(
                            source_id=SOURCE_ID,
                            source_title_id=slug,
                            canonical_url=urljoin(BASE_URL, href),
                            title=title or f"Manga {slug}",
                            media_type="manga",
                            tracking_mode="read",
                            thumbnail_url=None,
                            total_chapters=1,
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

    @cached(ttl=600, key_prefix="hentai20:details")
    async def get_title_details(
        self, source_title_id: str, context: SourceExecutionContext
    ) -> SourceTitleDetails:
        canonical_url = f"{BASE_URL}/manga/{source_title_id}/"
        try:
            html = await context.fetch_text(canonical_url)
            soup = BeautifulSoup(html, "lxml")

            title_el = soup.select_one("div.post-title h1") or soup.select_one("h1")
            title = title_el.text.strip() if title_el else f"Manga {source_title_id}"

            img_el = soup.select_one("div.summary_image img")
            thumb_url = img_el.get("src") if img_el else None

            tags = [a.text.strip() for a in soup.select("div.genres-content a")]
            chapters_count = len(soup.select("li.wp-manga-chapter"))

            return SourceTitleDetails(
                source_id=SOURCE_ID,
                source_title_id=source_title_id,
                canonical_url=canonical_url,
                title=title,
                media_type="manga",
                tracking_mode="read",
                thumbnail_url=thumb_url,
                tags=tags,
                total_chapters=chapters_count,
                content_summary=SourceTitleContentSummary(
                    kind="chapters",
                    total_count=chapters_count,
                    available_count=chapters_count,
                    in_app_capabilities=["reader"],
                ),
            )
        except Exception:
            return SourceTitleDetails(
                source_id=SOURCE_ID,
                source_title_id=source_title_id,
                canonical_url=canonical_url,
                title=f"Manga {source_title_id}",
                media_type="manga",
                tracking_mode="read",
                content_summary=SourceTitleContentSummary(kind="none", total_count=0, available_count=0),
            )

    async def get_title_content(
        self, source_title_id: str, context: SourceExecutionContext
    ) -> SourceTitleContent:
        canonical_url = f"{BASE_URL}/manga/{source_title_id}/"
        try:
            html = await context.fetch_text(canonical_url)
            soup = BeautifulSoup(html, "lxml")
            chapters = []

            for li in soup.select("li.wp-manga-chapter"):
                a = li.select_one("a")
                if not a:
                    continue
                href = a.get("href", "")
                chap_title = a.text.strip()
                chap_match = re.search(r"/manga/[^/]+/([a-z0-9-]+)", href, re.I)
                chap_id = chap_match.group(1) if chap_match else chap_title

                chapters.append(
                    SourceTitleChapter(
                        id=chap_id,
                        title=chap_title,
                        canonical_url=urljoin(BASE_URL, href),
                    )
                )

            return SourceTitleContent(kind="chapters", chapters=chapters)
        except Exception:
            return SourceTitleContent(kind="chapters", chapters=[])

    @cached(ttl=600, key_prefix="hentai20:pages")
    async def get_reader_pages(
        self, source_title_id: str, content_id: str | None, context: SourceExecutionContext
    ) -> SourceReaderPages:
        chap_slug = content_id or "chapter-1"
        url = f"{BASE_URL}/manga/{source_title_id}/{chap_slug}/"
        try:
            html = await context.fetch_text(url)
            soup = BeautifulSoup(html, "lxml")
            pages = []

            for idx, img in enumerate(soup.select("div.page-break img, div.reading-content img"), 1):
                img_url = img.get("src") or img.get("data-src")
                if img_url:
                    pages.append(
                        SourceTitlePage(
                            id=f"{chap_slug}-{idx}",
                            number=idx,
                            image_url=img_url.strip(),
                        )
                    )

            return SourceReaderPages(
                content_id=chap_slug,
                title=f"Chapter {chap_slug}",
                pages=pages,
            )
        except Exception:
            return SourceReaderPages(content_id=chap_slug, pages=[])
