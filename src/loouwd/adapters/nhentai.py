from typing import Any
import math
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
    SourceReaderPages,
    SourcePlayback,
    SourceTitlePage,
    SourceTitleContentSummary,
)
from loouwd.core.context import SourceExecutionContext
from loouwd.core.registry import registry, BaseSourceAdapter
from loouwd.core.cache import cached

SOURCE_ID = "nhentai"
SOURCE_NAME = "nhentai"
BASE_URL = "https://nhentai.net"
FAVICON_URL = "https://nhentai.net/favicon.png"
API_BASE_URL = "https://nhentai.net/api/v2"

TAG_OPTIONS = [
    "tentacles", "stuck in wall", "netorare", "netorase", "double penetration",
    "mmf threesome", "deepthroat", "bukkake", "big penis", "dark skin",
    "goblin", "blowjob", "crotch tattoo", "old man", "mind break", "handjob",
    "fingering", "condom", "blindfold", "blackmail", "group", "rape", "slave",
    "bestiality", "anal", "defloration", "impregnation", "dilf", "cheating",
    "muscle", "big breasts", "schoolgirl uniform", "sole female", "full color",
    "ahegao", "paizuri", "nakadashi", "uncensored"
]

PARODY_OPTIONS = [
    "Blue Archive", "Genshin Impact", "Pokemon", "Love Live", "Sword Art Online",
    "To Love-Ru", "My Hero Academia", "Princess Connect", "Code Geass",
    "Dead or Alive", "Kimetsu no Yaiba", "Honkai Star Rail", "Jujutsu Kaisen"
]


@registry.register
class NHentaiAdapter(BaseSourceAdapter):
    @property
    def manifest(self) -> SourceManifest:
        return SourceManifest(
            id=SOURCE_ID,
            name=SOURCE_NAME,
            version="1.3.1",
            description="Browse nhentai galleries through API with async registry performance.",
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
                        key="tag",
                        label="Tag",
                        type="multiselect",
                        default_value=[],
                        options=[SourceFilterOption(value=t, label=t) for t in TAG_OPTIONS],
                    ),
                    SourceFilterDefinition(
                        key="parody",
                        label="Parody",
                        type="multiselect",
                        default_value=[],
                        options=[SourceFilterOption(value=p, label=p) for p in PARODY_OPTIONS],
                    ),
                ],
            ),
        )

    @cached(ttl=300, key_prefix="nhentai:search")
    async def search_titles(
        self, request: SourceBrowseRequest, context: SourceExecutionContext
    ) -> SourceBrowseResult:
        page = max(1, request.page)
        query = request.query.strip() if request.query else ""

        # Build filter query params
        query_parts = []
        if query:
            query_parts.append(query)

        tags = request.filters.get("tag", [])
        if isinstance(tags, str):
            tags = [tags]
        for t in tags:
            query_parts.append(f'tag:"{t}"')

        parodies = request.filters.get("parody", [])
        if isinstance(parodies, str):
            parodies = [parodies]
        for p in parodies:
            query_parts.append(f'parody:"{p}"')

        full_query = " ".join(query_parts)
        if full_query:
            url = f"{API_BASE_URL}/search?query={full_query}&page={page}"
        else:
            url = f"{API_BASE_URL}/galleries?page={page}"

        try:
            data = await context.fetch_json(url)
            results = data.get("result", [])
            total_pages = data.get("num_pages", 1)

            items = []
            for g in results:
                if g.get("blacklisted"):
                    continue
                gid = str(g.get("id"))
                title_obj = g.get("title", {})
                title = title_obj.get("pretty") or title_obj.get("english") or title_obj.get("japanese") or f"Gallery {gid}"
                media_id = g.get("media_id", "")
                thumb = f"https://t.nhentai.net/galleries/{media_id}/thumb.jpg" if media_id else None

                items.append(
                    SourceBrowseItem(
                        source_id=SOURCE_ID,
                        source_title_id=gid,
                        canonical_url=f"{BASE_URL}/g/{gid}/",
                        title=title,
                        media_type="manga",
                        tracking_mode="read",
                        thumbnail_url=thumb,
                        total_chapters=1,
                        total_episodes=None,
                    )
                )

            return SourceBrowseResult(
                items=items,
                page=page,
                total_pages=total_pages,
                applied_filters=request.filters,
            )
        except Exception as err:
            # Mock fallback / offline handling
            return SourceBrowseResult(items=[], page=page, total_pages=1)

    @cached(ttl=600, key_prefix="nhentai:details")
    async def get_title_details(
        self, source_title_id: str, context: SourceExecutionContext
    ) -> SourceTitleDetails:
        url = f"{API_BASE_URL}/gallery/{source_title_id}"
        try:
            g = await context.fetch_json(url)
            gid = str(g.get("id", source_title_id))
            title_obj = g.get("title", {})
            title = title_obj.get("pretty") or title_obj.get("english") or f"Gallery {gid}"
            alt_titles = [t for t in [title_obj.get("english"), title_obj.get("japanese")] if t]
            media_id = g.get("media_id", "")
            thumb = f"https://t.nhentai.net/galleries/{media_id}/thumb.jpg" if media_id else None

            tags = [t.get("name") for t in g.get("tags", []) if isinstance(t, dict) and t.get("name")]
            num_pages = g.get("num_pages", 0)

            return SourceTitleDetails(
                source_id=SOURCE_ID,
                source_title_id=gid,
                canonical_url=f"{BASE_URL}/g/{gid}/",
                title=title,
                media_type="manga",
                tracking_mode="read",
                thumbnail_url=thumb,
                alt_titles=alt_titles,
                status="completed",
                tags=tags,
                content_summary=SourceTitleContentSummary(
                    kind="pages",
                    total_count=num_pages,
                    available_count=num_pages,
                    in_app_capabilities=["reader"],
                ),
            )
        except Exception:
            return SourceTitleDetails(
                source_id=SOURCE_ID,
                source_title_id=source_title_id,
                canonical_url=f"{BASE_URL}/g/{source_title_id}/",
                title=f"Gallery {source_title_id}",
                media_type="manga",
                tracking_mode="read",
                content_summary=SourceTitleContentSummary(kind="none", total_count=0, available_count=0),
            )

    async def get_title_content(
        self, source_title_id: str, context: SourceExecutionContext
    ) -> SourceTitleContent:
        pages_res = await self.get_reader_pages(source_title_id, None, context)
        return SourceTitleContent(kind="pages", pages=pages_res.pages)

    @cached(ttl=600, key_prefix="nhentai:pages")
    async def get_reader_pages(
        self, source_title_id: str, content_id: str | None, context: SourceExecutionContext
    ) -> SourceReaderPages:
        url = f"{API_BASE_URL}/gallery/{source_title_id}"
        try:
            g = await context.fetch_json(url)
            media_id = g.get("media_id", "")
            num_pages = g.get("num_pages", 0)
            pages = []
            for i in range(1, num_pages + 1):
                img_url = f"https://i.nhentai.net/galleries/{media_id}/{i}.jpg"
                thumb_url = f"https://t.nhentai.net/galleries/{media_id}/{i}t.jpg"
                pages.append(
                    SourceTitlePage(
                        id=f"{source_title_id}-{i}",
                        number=i,
                        image_url=img_url,
                        thumbnail_url=thumb_url,
                    )
                )

            return SourceReaderPages(
                content_id=source_title_id,
                title=g.get("title", {}).get("pretty") or f"Gallery {source_title_id}",
                pages=pages,
            )
        except Exception:
            return SourceReaderPages(content_id=source_title_id, pages=[])
