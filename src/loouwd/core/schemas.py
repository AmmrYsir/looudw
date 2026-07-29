from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict

SourceMediaType = Literal['anime', 'manga']
SourceAuthType = Literal['none', 'credentials', 'token']
SourceTrackingMode = Literal['watch', 'read']
SourceInAppCapability = Literal['reader', 'player']
SourceTitleContentKind = Literal['none', 'pages', 'chapters', 'episodes']
SourceFilterType = Literal['select', 'multiselect', 'toggle', 'text']
SourceStatus = Literal['ongoing', 'completed', 'hiatus', 'unknown']
HealthState = Literal['ok', 'degraded', 'error']


class BaseSchema(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )


class SourceFilterOption(BaseSchema):
    value: str
    label: str


class SourceFilterDefinition(BaseSchema):
    key: str
    label: str
    type: SourceFilterType
    options: list[SourceFilterOption] = Field(default_factory=list)
    default_value: Any = Field(default=None, alias="defaultValue")
    description: str | None = None
    placeholder: str | None = None
    searchable: bool | None = None
    true_label: str | None = Field(default=None, alias="trueLabel")
    false_label: str | None = Field(default=None, alias="falseLabel")


class SourceAuthConfig(BaseSchema):
    type: SourceAuthType = "none"
    fields: list[str] = Field(default_factory=list)


class SourceTagSuggestion(BaseSchema):
    name: str
    type: str = "tag"
    count: int | None = None
    description: str | None = None


class SourceFeatureSet(BaseSchema):
    browse: bool = True
    search: bool = True
    title_details: bool = Field(default=True, alias="titleDetails")
    favorites: bool = True
    tag_autocomplete: bool = Field(default=False, alias="tagAutocomplete")
    library_sync: bool = Field(default=False, alias="librarySync")
    history_sync: bool = Field(default=False, alias="historySync")
    updates_sync: bool = Field(default=False, alias="updatesSync")


class SourceBrowseConfig(BaseSchema):
    supports_pagination: bool = Field(default=True, alias="supportsPagination")
    filters: list[SourceFilterDefinition] = Field(default_factory=list)


class SourceManifest(BaseSchema):
    id: str
    name: str
    version: str
    description: str
    website: str
    icon_url: str | None = Field(default=None, alias="iconUrl")
    supported_media_types: list[SourceMediaType] = Field(alias="supportedMediaTypes")
    auth: SourceAuthConfig = Field(default_factory=SourceAuthConfig)
    features: SourceFeatureSet = Field(default_factory=SourceFeatureSet)
    browse_config: SourceBrowseConfig | None = Field(default=None, alias="browseConfig")


class SourceBrowseItem(BaseSchema):
    source_id: str = Field(alias="sourceId")
    source_title_id: str = Field(alias="sourceTitleId")
    canonical_url: str = Field(alias="canonicalUrl")
    title: str
    media_type: SourceMediaType = Field(alias="mediaType")
    tracking_mode: SourceTrackingMode = Field(alias="trackingMode")
    thumbnail_url: str | None = Field(default=None, alias="thumbnailUrl")
    description: str | None = None
    rating: float | None = None
    hot: bool = False
    popular: bool = False
    total_episodes: int | None = Field(default=None, alias="totalEpisodes")
    total_chapters: int | None = Field(default=None, alias="totalChapters")
    updated_at: str | None = Field(default=None, alias="updatedAt")
    released_at: str | None = Field(default=None, alias="releasedAt")


class SourceBrowseRequest(BaseSchema):
    query: str | None = None
    page: int = 1
    filters: dict[str, Any] = Field(default_factory=dict)


class SourceBrowseResult(BaseSchema):
    items: list[SourceBrowseItem] = Field(default_factory=list)
    page: int = 1
    total_pages: int | None = Field(default=None, alias="totalPages")
    total_items: int | None = Field(default=None, alias="totalItems")
    applied_filters: dict[str, Any] = Field(default_factory=dict, alias="appliedFilters")


class SourceTitleContentSummary(BaseSchema):
    kind: SourceTitleContentKind = "none"
    total_count: int = Field(default=0, alias="totalCount")
    available_count: int = Field(default=0, alias="availableCount")
    in_app_capabilities: list[SourceInAppCapability] = Field(default_factory=list, alias="inAppCapabilities")


class SourceTitleDetails(SourceBrowseItem):
    alt_titles: list[str] = Field(default_factory=list, alias="altTitles")
    status: SourceStatus = "unknown"
    tags: list[str] = Field(default_factory=list)
    content_summary: SourceTitleContentSummary = Field(alias="contentSummary")


class SourceTitlePage(BaseSchema):
    id: str
    number: int
    image_url: str = Field(alias="imageUrl")
    thumbnail_url: str | None = Field(default=None, alias="thumbnailUrl")
    width: int | None = None
    height: int | None = None


class SourceTitleChapter(BaseSchema):
    id: str
    number: float | int | None = None
    title: str
    canonical_url: str | None = Field(default=None, alias="canonicalUrl")
    released_at: str | None = Field(default=None, alias="releasedAt")
    locked: bool = False


class SourceTitleEpisode(BaseSchema):
    id: str
    number: float | int | None = None
    title: str
    canonical_url: str | None = Field(default=None, alias="canonicalUrl")
    released_at: str | None = Field(default=None, alias="releasedAt")
    thumbnail_url: str | None = Field(default=None, alias="thumbnailUrl")
    duration_seconds: int | None = Field(default=None, alias="durationSeconds")
    locked: bool = False


class SourceTitleContent(BaseSchema):
    kind: SourceTitleContentKind
    pages: list[SourceTitlePage] | None = None
    chapters: list[SourceTitleChapter] | None = None
    episodes: list[SourceTitleEpisode] | None = None


class SourceReaderPages(BaseSchema):
    content_id: str | None = Field(default=None, alias="contentId")
    title: str | None = None
    pages: list[SourceTitlePage] = Field(default_factory=list)


class SourcePlayback(BaseSchema):
    content_id: str | None = Field(default=None, alias="contentId")
    title: str | None = None
    stream_url: str = Field(alias="streamUrl")
    mime_type: str = Field(default="video/mp4", alias="mimeType")
    poster_url: str | None = Field(default=None, alias="posterUrl")
    width: int | None = None
    height: int | None = None
    duration_seconds: int | None = Field(default=None, alias="durationSeconds")
    canonical_url: str | None = Field(default=None, alias="canonicalUrl")


class SourceFavoritePayload(BaseSchema):
    source_id: str = Field(alias="sourceId")
    source_title_id: str = Field(alias="sourceTitleId")
    source_url: str = Field(alias="sourceUrl")
    title: str
    media_type: SourceMediaType = Field(alias="mediaType")
    tracking_mode: SourceTrackingMode = Field(alias="trackingMode")
    total_episodes: int | None = Field(default=None, alias="totalEpisodes")
    total_chapters: int | None = Field(default=None, alias="totalChapters")
    description: str | None = None


class SourceHealthCheck(BaseSchema):
    source_id: str = Field(alias="sourceId")
    status: HealthState
    message: str
    response_time_ms: float = Field(alias="responseTimeMs")
