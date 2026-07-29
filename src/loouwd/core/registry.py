from abc import ABC, abstractmethod
import time
from typing import Type, Any
from loouwd.core.schemas import (
    SourceManifest,
    SourceBrowseRequest,
    SourceBrowseResult,
    SourceTitleDetails,
    SourceTitleContent,
    SourceReaderPages,
    SourcePlayback,
    SourceHealthCheck,
    HealthState,
)
from loouwd.core.context import SourceExecutionContext
from loouwd.core.logging import logger


class BaseSourceAdapter(ABC):
    @property
    @abstractmethod
    def manifest(self) -> SourceManifest:
        pass

    async def search_titles(
        self, request: SourceBrowseRequest, context: SourceExecutionContext
    ) -> SourceBrowseResult:
        raise NotImplementedError(f"search_titles not implemented for {self.manifest.id}")

    async def get_title_details(
        self, source_title_id: str, context: SourceExecutionContext
    ) -> SourceTitleDetails:
        raise NotImplementedError(f"get_title_details not implemented for {self.manifest.id}")

    async def get_title_content(
        self, source_title_id: str, context: SourceExecutionContext
    ) -> SourceTitleContent:
        raise NotImplementedError(f"get_title_content not implemented for {self.manifest.id}")

    async def get_reader_pages(
        self, source_title_id: str, content_id: str | None, context: SourceExecutionContext
    ) -> SourceReaderPages:
        raise NotImplementedError(f"get_reader_pages not implemented for {self.manifest.id}")

    async def get_playback(
        self, source_title_id: str, content_id: str | None, context: SourceExecutionContext
    ) -> SourcePlayback:
        raise NotImplementedError(f"get_playback not implemented for {self.manifest.id}")

    async def autocomplete_tags(
        self, query: str, tag_type: str = "tag", context: SourceExecutionContext | None = None
    ) -> list[Any]:
        return []

    async def health_check(self, context: SourceExecutionContext) -> SourceHealthCheck:
        start_time = time.time()
        try:
            # Default health check: browse page 1 with empty query
            res = await self.search_titles(SourceBrowseRequest(page=1), context)
            elapsed_ms = (time.time() - start_time) * 1000
            status: HealthState = "ok" if res.items else "degraded"
            message = f"Fetched {len(res.items)} items in {elapsed_ms:.1f}ms"
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            status = "error"
            message = f"Health check failed: {str(e)}"

        return SourceHealthCheck(
            source_id=self.manifest.id,
            status=status,
            message=message,
            response_time_ms=round(elapsed_ms, 2),
        )


class SourceRegistry:
    def __init__(self):
        self._adapters: dict[str, BaseSourceAdapter] = {}

    def register(self, adapter_cls: Type[BaseSourceAdapter]) -> Type[BaseSourceAdapter]:
        instance = adapter_cls()
        source_id = instance.manifest.id
        if source_id in self._adapters:
            logger.warning(f"Overwriting registered adapter for source_id: '{source_id}'")
        self._adapters[source_id] = instance
        logger.info(f"Registered source adapter: '{source_id}' ({instance.manifest.name} v{instance.manifest.version})")
        return adapter_cls

    def get(self, source_id: str) -> BaseSourceAdapter | None:
        return self._adapters.get(source_id)

    def get_or_raise(self, source_id: str) -> BaseSourceAdapter:
        adapter = self.get(source_id)
        if not adapter:
            raise KeyError(f"Source adapter '{source_id}' is not registered.")
        return adapter

    def list_sources(self) -> list[BaseSourceAdapter]:
        return list(self._adapters.values())

    def list_manifests(self) -> list[SourceManifest]:
        return [adapter.manifest for adapter in self._adapters.values()]

    async def check_health_all(
        self, context: SourceExecutionContext
    ) -> list[SourceHealthCheck]:
        results = []
        for adapter in self._adapters.values():
            check = await adapter.health_check(context)
            results.append(check)
        return results


registry = SourceRegistry()
