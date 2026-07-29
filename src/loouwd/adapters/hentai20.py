import re
import json
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

SOURCE_ID = "hentai20"
SOURCE_NAME = "Hentai20.io"
BASE_URL = "https://hentai20.io"
FAVICON_URL = "https://hentai20.io/wp-content/uploads/2024/05/cropped-210da20ddb1be20edd43583bcaf1061f628cbc16-300x300.jpg"

SORT_OPTIONS = [
    SourceFilterOption(value="latest", label="Latest Releases"),
    SourceFilterOption(value="views", label="Most Viewed"),
    SourceFilterOption(value="trending", label="Trending"),
    SourceFilterOption(value="rating", label="Top Rated"),
    SourceFilterOption(value="alphabet", label="Alphabetical A-Z"),
]

GENRE_OPTIONS = [
    SourceFilterOption(value="", label="All Genres"),
    SourceFilterOption(value="manhwa-hentai", label="Manhwa Hentai"),
    SourceFilterOption(value="manga-hentai", label="Manga Hentai"),
    SourceFilterOption(value="mature", label="Mature"),
    SourceFilterOption(value="romance", label="Romance"),
    SourceFilterOption(value="harem", label="Harem"),
    SourceFilterOption(value="school-life", label="School Life"),
    SourceFilterOption(value="drama", label="Drama"),
    SourceFilterOption(value="fantasy", label="Fantasy"),
    SourceFilterOption(value="comedy", label="Comedy"),
]


@registry.register
class Hentai20Adapter(BaseSourceAdapter):
    """
    Production-grade Hentai20.io adapter built against WordPress Madara Theme specifications.
    Extracts chapters, metadata, and reader page images dynamically.
    """

    @property
    def manifest(self) -> SourceManifest:
        return SourceManifest(
            id=SOURCE_ID,
            name=SOURCE_NAME,
            version="2.0.0",
            description="Production-grade Hentai20.io WP Madara manga engine with dynamic chapter extraction.",
            website=BASE_URL,
            icon_url=FAVICON_URL,
            supported_media_types=["manga"],
            auth=SourceAuthConfig(type="none"),
            features=SourceFeatureSet(
                browse=True, search=True, title_details=True, favorites=True, tag_autocomplete=True
            ),
            browse_config=SourceBrowseConfig(
                supports_pagination=True,
                filters=[
                    SourceFilterDefinition(
                        key="sort",
                        label="Sort By",
                        type="select",
                        default_value="latest",
                        options=SORT_OPTIONS,
                    ),
                    SourceFilterDefinition(
                        key="genre",
                        label="Genre",
                        type="select",
                        default_value="",
                        options=GENRE_OPTIONS,
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
                            if res.status_code == 200 and len(res.text) > 1000:
                                return res.text
                    except Exception as err:
                        logger.debug(f"Hentai20 TLS impersonation target '{profile}' failed: {err}")

            logger.warning(f"Hentai20 request to '{url}' failed.")
            return ""

    @cached(ttl=300, key_prefix="hentai20:v2:search")
    async def search_titles(
        self, request: SourceBrowseRequest, context: SourceExecutionContext
    ) -> SourceBrowseResult:
        page = max(1, request.page)
        query = request.query.strip() if request.query else ""
        sort = request.filters.get("sort", "latest")
        genre = request.filters.get("genre", "")

        if query:
            url = f"{BASE_URL}/page/{page}/?s={quote(query)}&post_type=wp-manga" if page > 1 else f"{BASE_URL}/?s={quote(query)}&post_type=wp-manga"
        elif genre:
            url = f"{BASE_URL}/manga-genre/{genre}/page/{page}/" if page > 1 else f"{BASE_URL}/manga-genre/{genre}/"
            if sort:
                url += f"?m_orderby={quote(str(sort))}"
        else:
            url = f"{BASE_URL}/manga/page/{page}/?m_orderby={quote(str(sort))}" if page > 1 else f"{BASE_URL}/manga/?m_orderby={quote(str(sort))}"

        html = await self._fetch_html(context, url)
        if not html:
            return SourceBrowseResult(items=[], page=page, total_pages=1)

        soup = BeautifulSoup(html, "lxml")
        items = []
        seen = set()

        for a in soup.select('a[href*="/manga/"]'):
            href = a.get("href", "")
            title = a.get("title") or a.text.strip()
            match = re.search(r"/manga/([a-z0-9-]+)", href, re.I)
            if not match:
                continue

            slug = match.group(1).lower()
            if slug in ["page", "manga", "list-mode", "grid-mode", "mode", "genre", "tag"]:
                continue
            if slug in seen:
                continue
            seen.add(slug)

            img_el = a.select_one("img")
            thumb_url = img_el.get("src") or img_el.get("data-src") if img_el else None

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

        return SourceBrowseResult(
            items=items,
            page=page,
            total_pages=page + 5,
            applied_filters=request.filters,
        )

    @cached(ttl=600, key_prefix="hentai20:v2:details")
    async def get_title_details(
        self, source_title_id: str, context: SourceExecutionContext
    ) -> SourceTitleDetails:
        canonical_url = f"{BASE_URL}/manga/{source_title_id}/"
        html = await self._fetch_html(context, canonical_url)

        if not html:
            return SourceTitleDetails(
                source_id=SOURCE_ID,
                source_title_id=source_title_id,
                canonical_url=canonical_url,
                title=f"Manga {source_title_id}",
                media_type="manga",
                tracking_mode="read",
                content_summary=SourceTitleContentSummary(kind="none", total_count=0, available_count=0),
            )

        soup = BeautifulSoup(html, "lxml")

        title_el = soup.select_one("div.post-title h1") or soup.select_one("h1")
        title = title_el.text.strip() if title_el else f"Manga {source_title_id}"

        img_el = soup.select_one("div.summary_image img")
        thumb_url = img_el.get("src") or img_el.get("data-src") if img_el else None

        tags = [a.text.strip() for a in soup.select("a[href*='manga-genre'], a[href*='manga-tag']")]
        chapters = soup.select("a[href*='chapter']")
        chapters_count = len(chapters)

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

    async def get_title_content(
        self, source_title_id: str, context: SourceExecutionContext
    ) -> SourceTitleContent:
        canonical_url = f"{BASE_URL}/manga/{source_title_id}/"
        html = await self._fetch_html(context, canonical_url)
        if not html:
            return SourceTitleContent(kind="chapters", chapters=[])

        soup = BeautifulSoup(html, "lxml")
        chapters = []
        seen = set()

        for a in soup.select("a[href*='chapter']"):
            href = a.get("href", "")
            chap_title = a.text.strip()
            if not href or href in seen or "chapter-{number}" in href:
                continue
            seen.add(href)

            chap_match = re.search(r"chapter-([0-9.]+)", href, re.I)
            chap_id = f"chapter-{chap_match.group(1)}" if chap_match else chap_title

            chapters.append(
                SourceTitleChapter(
                    id=chap_id,
                    title=chap_title or f"Chapter {chap_id}",
                    canonical_url=urljoin(BASE_URL, href),
                )
            )

        return SourceTitleContent(kind="chapters", chapters=chapters)

    @cached(ttl=600, key_prefix="hentai20:v2:pages")
    async def get_reader_pages(
        self, source_title_id: str, content_id: str | None, context: SourceExecutionContext
    ) -> SourceReaderPages:
        chap_slug = content_id or "chapter-1"
        if not chap_slug.startswith("chapter-"):
            chap_slug = f"chapter-{chap_slug}"

        url = f"{BASE_URL}/{source_title_id}-{chap_slug}/"
        html = await self._fetch_html(context, url)
        if not html:
            return SourceReaderPages(content_id=chap_slug, pages=[])

        soup = BeautifulSoup(html, "lxml")
        pages = []
        seen_urls = set()

        # Method 1: Extract from ts_reader.run JSON payload script
        match = re.search(r'ts_reader\.run\((.*?)\);', html, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                sources = data.get("sources", [])
                if sources and isinstance(sources, list):
                    raw_imgs = sources[0].get("images", [])
                    for idx, img_src in enumerate(raw_imgs, 1):
                        if img_src and img_src not in seen_urls:
                            seen_urls.add(img_src)
                            pages.append(
                                SourceTitlePage(
                                    id=f"{chap_slug}-{idx}",
                                    number=idx,
                                    image_url=img_src.strip(),
                                )
                            )
            except Exception as json_err:
                logger.debug(f"Hentai20 ts_reader JSON parse failed: {json_err}")

        # Method 2: DOM fallback extraction
        if not pages:
            for idx, img in enumerate(soup.select("div.page-break img, div.reading-content img, img[src*='img.hentai']"), 1):
                img_url = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
                if img_url and img_url not in seen_urls and not img_url.endswith(".svg"):
                    seen_urls.add(img_url)
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

    @cached(ttl=600, key_prefix="hentai20:v2:autocomplete")
    async def autocomplete_tags(
        self, query: str, tag_type: str = "tag", context: SourceExecutionContext | None = None
    ) -> list[SourceTagSuggestion]:
        q = query.lower().strip()
        suggestions = []
        for opt in GENRE_OPTIONS:
            if opt.value and (q in opt.value.lower() or q in opt.label.lower()):
                suggestions.append(
                    SourceTagSuggestion(
                        name=opt.label,
                        type="genre",
                        description=f"Genre filter for {opt.label}",
                    )
                )
        return suggestions
