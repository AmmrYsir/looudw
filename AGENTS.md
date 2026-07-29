# 🤖 AGENTS.md: Developer & AI Agent Context Guide for Loouwd

Welcome! This document provides AI agents and human developers with an architectural overview, core contracts, best practices, and operational guidelines for working with the **Loouwd** codebase.

---

## 🎯 Project Purpose

**Loouwd** is an event-driven, asynchronous media source aggregator and reactive streaming core built with **Python 3.12**, **FastAPI**, and **curl_cffi**. It unifies manga, doujinshi, webtoons, and video streams across multiple source adapters into a single standardized REST & Server-Sent Events (SSE) API with sub-100ms first-byte streaming.

---

## 🏛️ Core Architectural Blueprint

### 1. BaseSourceAdapter Contract ([`src/loouwd/core/registry.py`](file:///c:/Users/ammar/Desktop/loouwd/src/loouwd/core/registry.py))
Every media source adapter inherits from `BaseSourceAdapter` and registers itself using the `@registry.register` decorator.

Key methods every adapter implements or extends:
- `@property manifest -> SourceManifest`: Metadata declarations, feature flags (`browse`, `search`, `title_details`, `favorites`, `tag_autocomplete`), and dynamic browse filters.
- `search_titles(request: SourceBrowseRequest, context: SourceExecutionContext) -> SourceBrowseResult`: Parses catalog items or search queries.
- `get_title_details(source_title_id: str, context: SourceExecutionContext) -> SourceTitleDetails`: Resolves metadata, cover art, tags, and summary.
- `get_title_content(source_title_id: str, context: SourceExecutionContext) -> SourceTitleContent`: Resolves chapter list (manga) or video episode (anime).
- `get_reader_pages(source_title_id: str, content_id: str | None, context: SourceExecutionContext) -> SourceReaderPages`: Resolves image page URLs for manga/doujin.
- `get_playback(source_title_id: str, content_id: str | None, context: SourceExecutionContext) -> SourcePlayback`: Resolves direct `.mp4` video stream URLs or HLS `.m3u8` master playlists.
- `autocomplete_tags(query: str, tag_type: str, context: SourceExecutionContext) -> list[SourceTagSuggestion]`: Real-time typeahead tag autocompletion.

---

### 2. Reactive Stream Engine ([`src/loouwd/core/stream.py`](file:///c:/Users/ammar/Desktop/loouwd/src/loouwd/core/stream.py))
- Uses Python 3.12 `AsyncGenerator[SourceBrowseItem, None]` to query enabled adapters concurrently.
- Streams items to client consumers in real-time as fast as each adapter parses its payload.
- Exposed via SSE endpoint: `GET /api/v1/unified/stream?query={q}`.

---

### 3. Anti-Bot Protection & Domain Rate Limiting ([`src/loouwd/core/limiter.py`](file:///c:/Users/ammar/Desktop/loouwd/src/loouwd/core/limiter.py))
- **`DomainRateLimiter`**: Enforces per-host semaphores and token-bucket delays before network requests.
- **`curl_cffi` TLS Impersonation**: Uses browser profiles (`safari15_5`, `chrome124`, `chrome120`) to bypass Cloudflare Turnstile and WAF challenges without IP blocks.

---

### 4. High-Speed In-Memory Cache ([`src/loouwd/core/cache.py`](file:///c:/Users/ammar/Desktop/loouwd/src/loouwd/core/cache.py))
- **`AsyncTTLCache`**: Delivers 0.02ms - 0.04ms cached response times for repeated search queries and title details.
- Used via `@cached(ttl=seconds, key_prefix="...")` decorator.

---

## 📁 Directory Structure & File Map

```
loouwd/
├── AGENTS.md                   # This file (AI agent context & guidelines)
├── README.md                   # Project overview & user API docs
├── pyproject.toml              # Project dependencies & CLI entrypoints
├── src/
│   └── loouwd/
│       ├── adapters/           # Source adapter implementations
│       │   ├── __init__.py     # Auto-registers all adapters
│       │   ├── nhentai.py      # nhentai v2 REST API engine (v2.1.0)
│       │   ├── hentai20.py     # WP Madara ts_reader JSON parser (v2.0.0)
│       │   ├── rule34world.py  # Rule34 video stream parser (v2.0.0)
│       │   ├── omegascans.py   # Omegascans REST API chapter parser (v2.0.0)
│       │   ├── spankbang.py    # SpankBang stream_data JSON parser (v2.0.0)
│       │   ├── xvideos.py      # XVideos html5player JS parser (v2.0.0)
│       │   └── xhamster.py     # xHamster HTML5 & window.initials parser (v2.0.0)
│       ├── api/
│       │   └── v1/
│       │       ├── app.py      # FastAPI application instance
│       │       └── routes.py   # REST API & SSE streaming endpoints
│       ├── core/
│       │   ├── cache.py        # In-memory AsyncTTLCache
│       │   ├── context.py      # SourceExecutionContext (fetch_text / fetch_json)
│       │   ├── limiter.py      # DomainRateLimiter (per-host concurrency)
│       │   ├── logging.py      # System logging configuration
│       │   ├── registry.py     # BaseSourceAdapter contract & registry
│       │   ├── schemas.py      # Pydantic schemas (SourceManifest, BrowseItem, etc.)
│       │   ├── services.py     # UnifiedCatalogService
│       │   └── stream.py       # ReactiveStreamEngine (AsyncGenerator pipeline)
│       └── cli.py              # Typer CLI application (loouwd serve/stream/list)
└── tests/                      # Automated unit test suite
```

---

## ⚡ Important Rules & Coding Guidelines for AI Agents

1. **Schema Compliance**:
   - Do NOT pass `author` to `SourceManifest`. The `author` field has been removed from `SourceManifest` schema.
   - Always use Pydantic alias formats (e.g. `icon_url`, `supported_media_types`, `total_episodes`).

2. **Network Request Protocol**:
   - Always route HTTP requests through `context.fetch_text()` or `context.fetch_json()` to trigger `DomainRateLimiter`.
   - For anti-bot domains, use `curl_cffi.requests.AsyncSession` with browser impersonation (`safari15_5`, `chrome124`).

3. **Title & Thumbnail Parsing**:
   - Sanitize video titles: strip duration text (e.g. `11 min`, `180m`, `07:28`) and badge prefixes.
   - Prefer HTTPS URLs for thumbnails and direct MP4/HLS streams.

4. **Error Handling**:
   - Never allow network exceptions to crash the FastAPI server or CLI. Return fallback objects or empty `SourceBrowseResult(items=[], page=page, total_pages=1)` on unexpected HTML changes or timeouts.

5. **Verification Requirement**:
   - After making changes to any adapter or core file, ALWAYS run the automated unit test suite before ending your turn:
     ```bash
     .venv\Scripts\python.exe -m unittest discover -s tests
     ```

---

## 🧪 Verification Commands

```bash
# Run unit test suite
.venv\Scripts\python.exe -m unittest discover -s tests

# Check CLI serve command help
.venv\Scripts\python.exe -m loouwd.cli serve --help

# Test live CLI multi-source stream
.venv\Scripts\python.exe -m loouwd.cli unified stream "naruto"
```
