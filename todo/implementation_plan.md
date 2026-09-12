# Implementation Plan: 3-Phase Automated Testing Strategy & CI/CD Pipeline

**Target Repository**: `paradigm-city/plugin.video.youtube`  
**Upstream**: `anxdpanic/plugin.video.youtube`  
**Target Matrix**: Kodi 19 (Matrix) through Kodi 22 (Piers) | Python 3.8–3.13+  
**Status**: Fully Implemented and Verified (Phases 1, 2, 3, 4, 5, 6, and 7)  

---

## 1. Executive Summary & Goals

The `plugin.video.youtube` Kodi add-on manages complex interactions between Kodi's C-based application runtime (`xbmc`, `xbmcgui`, `xbmcplugin`, `xbmcaddon`, `xbmcvfs`), YouTube's Data API v3, internal Innertube streaming endpoints, and multi-threaded SQLite caching engines.

Historically, the repository lacked automated testing outside of basic metadata validation (`kodi-addon-checker`), creating high regression risks for:
1. **Concurrency Hazards**: Multi-threaded database access causing statement cache collisions and `KeyError`.
2. **Kodi API Incompatibilities**: Inability to run or verify Python code outside an active Kodi process without crashes.
3. **API & Player Fragility**: YouTube API quota exhaustion, changes in Innertube streaming schemas, and URL redirection edge cases.

This implementation plan defines and documents the architecture of the automated testing framework, test suites, and CI/CD quality gates.

---

## 2. Architecture & Design

### A. Test Execution & Kodi Emulation Architecture
Running tests in standard Python environments requires isolating add-on logic from native Kodi binary libraries.

```mermaid
graph TD
    subgraph Test Runner
        PYTEST[pytest CLI / CI Matrix]
        CONFTEST[tests/conftest.py]
    end

    subgraph Emulation Harness [tests/mocks/]
        M_XBMC[xbmc.py]
        M_ADDON[xbmcaddon.py]
        M_GUI[xbmcgui.py]
        M_PLUGIN[xbmcplugin.py]
        M_VFS[xbmcvfs.py]
    end

    subgraph Add-on Core [resources/lib/youtube_plugin]
        KODION[kodion/ - Framework & SQLite Storage]
        CLIENTS[youtube/client/ - Data & Player Clients]
        HELPERS[youtube/helper/ - UrlResolver & Subtitles]
    end

    PYTEST --> CONFTEST
    CONFTEST -->|Preemptive sys.modules Injection| Emulation Harness
    CONFTEST -->|Import| Add-on Core
    Add-on Core -->|Runtime Calls| Emulation Harness
```

#### Preemptive Module Registration (`tests/conftest.py`)
`youtube_plugin.kodion.compatibility` detects missing `xbmc` modules and falls back to Python 2 imports (`urllib`, `urllib2`, `urlparse`), which fail under Python 3.
- **Solution**: `tests/conftest.py` prepends `resources/lib` to `sys.path` and inserts all mock modules directly into `sys.modules` before any `youtube_plugin` code is imported.

#### Kodi Mock Implementations (`tests/mocks/`)
* **`xbmc.py`**:
  * Logging constants (`LOGDEBUG` through `LOGNONE`) and `log()`.
  * JSON-RPC dispatch emulation (`executeJSONRPC`) supporting `Application.GetProperties`.
  * `PlayList`, `Player`, and `Monitor` stubs.
  * Language format resolution (`getLanguage(format=...)`) and ISO language constants.
* **`xbmcaddon.py`**:
  * `Addon` and `Settings` classes with typed getters (`getSettingBool`, `getSettingInt`, `getSettingNumber`).
  * Explicitly raises `ValueError` on unset numerical/boolean settings so that `kodion` defaults (such as HTTP connect/read timeouts) resolve correctly.
* **`xbmcgui.py`**:
  * `ListItem` with property dictionaries and stream info tracking (`setPath`, `setProperty`, `getVideoInfoTag`).
  * `Dialog` supporting user input, notifications, and context selections.
* **`xbmcplugin.py`**:
  * Directory item accumulation (`addDirectoryItem`, `addDirectoryItems`).
  * Directory finalization (`endOfDirectory`) and sort methods (`SORT_METHOD_*`).
* **`xbmcvfs.py`**:
  * Emulates Kodi virtual filesystem operations (`exists`, `delete`, `mkdir`, `File`).

---

## 3. Implementation Phases

### Phase 1: Test Harness, Storage & Concurrency Suite
* **Goal**: Isolate Kodi dependencies and verify SQLite database stability under high-concurrency thread contention.
* **Deliverables**:
  1. **Test Infrastructure**:
     - `requirements-dev.txt`: `pytest`, `pytest-cov`, `pytest-mock`, `requests`, `requests-mock`, `ruff`.
     - `pyproject.toml`: Pytest configuration, custom markers (`concurrency`, `live`), warning filters, and coverage rules.
  2. **Storage Unit Tests (`tests/unit/test_storage.py`)**:
     - CRUD operations on `DataCache` and `Storage`.
     - Batch updates (`set_many`, `get_many`).
     - TTL expiration and pruning.
     - Function memoization (`FunctionCache.run`).
     - Temporary SQLite handle cleanup ensuring clean teardown on Windows (`WinError 32`).
  3. **Concurrency Stress Tests (`tests/concurrency/test_storage_concurrency.py`)**:
     - Multi-threaded stress testing (10 worker threads executing 500 concurrent read/write operations).
     - Batch update concurrency across threads.
     - Validates that thread synchronization (`RLock` in `Storage`) prevents CPython `statement_cache` collisions and `KeyError`.
  4. **URL Resolver Tests (`tests/unit/test_url_resolver.py`)**:
     - Channel URL resolution (custom handles `@handle`, `/c/`, `/user/`, `/channel/`).
     - YouTube clip URLs with timestamp parameters (`t`, `start`, `end`).
     - Supported browsers redirection wrappers and tracking query stripping.
     - `UrlResolver` wrapper delegation and cache integration.

---

### Phase 2: Client Mocking & API Integration Suites
* **Goal**: Validate YouTube Data API v3 and Innertube player responses without external network dependencies or quota consumption.
* **Deliverables**:
  1. **Fixture Repositories (`tests/fixtures/`)**:
     - `tests/fixtures/v3_api/video_details.json`: Full snippet, content details (ISO 8601 duration `PT3M33S`), and statistics.
     - `tests/fixtures/v3_api/search_results.json`: Mixed search results (videos, channels) and pagination tokens.
     - `tests/fixtures/v3_api/subscriptions_list.json`: User subscriptions and channel IDs.
     - `tests/fixtures/v3_api/quota_exceeded.json`: Google API 403 `quotaExceeded` error payload.
     - `tests/fixtures/innertube/player_response.json`: Playback response containing progressive format 18, adaptive formats (137, 248, 136, 140, 251), and subtitle tracks.
  2. **Data API Client Tests (`tests/integration/test_data_client.py`)**:
     - Metadata parsing: video title, duration, view count, channel association.
     - Search pagination: parameter formatting, item extraction, and page token persistence.
     - Subscription lists: mapping channel subscriptions.
     - Error resilience: verifying graceful error handling and notification on HTTP 403 quota exhaustion.
     - API key validation: ensuring requests are blocked when keys are not configured.
  3. **Player Client Tests (`tests/integration/test_player_client.py`)**:
     - Progressive stream parsing: extracting video/audio streams for itag 18.
     - Stream format definition mapping: resolution, frame rates, and codecs.
     - Subtitle extraction: parsing timed text caption tracks (English, German) into Kodi list items.

---

### Phase 3: CI/CD Pipeline Automation & Quality Gates
* **Goal**: Enforce automated testing and static analysis across all supported Python versions in GitHub Actions.
* **Deliverables**:
  1. **Linter Integration (`ruff`)**:
     - Configured `ruff` rules in `pyproject.toml` (E, W, F, I, B).
     - Cleaned up unused imports and style anomalies across test files.
     - Added `ruff check tests` as a strict pre-test quality gate.
  2. **Modernized Workflow (`.github/workflows/addon-validations.yml`)**:
     - **Triggers**: Executed on push and pull requests for `master`, `main`, `current_testing`, and `tests`.
     - **Open Access**: Removed `if: github.repository == ...` restriction to support forks and external contributors.
     - **Lint Job**: Runs Ruff lint checks on Python 3.12.
     - **Test Matrix Job**: Runs `pytest` with coverage across Python **3.8, 3.9, 3.10, 3.11, 3.12, and 3.13**.
     - **Add-on Checker Job**: Retains Kodi Add-on Checker against the Nexus branch on Python 3.12.

---

### Phase 4: Context Menu Assembly, Route Dispatch & Live Smoke Probes
* **Goal**: Verify UI item context menus, Provider navigation routing, and live YouTube Innertube stream health.
* **Deliverables**:
  1. **Context Menu Assembly Unit Tests (`tests/unit/test_context_menu.py`)**:
     - Default video playback context menus (play, subtitles, audio only, ask for quality).
     - Live stream timeshift toggle (`timeshift=True`).
     - Local vs remote Watch Later and Bookmarks list filtering.
     - Channel subscription and bookmark context actions.
     - Playlist item removal scoping (`playlist_channel_id == 'mine'`).
  2. **Provider Route Dispatch Tests (`tests/unit/test_provider_routing.py`)**:
     - Route matching and parameter extraction for `/`, `/play/`, `/video/rate/`, `/video/more/`, `/subscriptions/list/`, and `/search/query/`.
     - Added `context.settings()` alias method to `AbstractContext` for backwards compatibility with `yt_play.py` and `xbmc_plugin.py`.
     - Verified `KodionException` on unmatched route paths.
  3. **Live Upstream Smoke Tests (`tests/live/test_live_innertube.py`)**:
     - Marked with `@pytest.mark.live` (opt-in; excluded by default in `pyproject.toml`).
     - Real network validation against YouTube Innertube endpoints for public videos (`jNQXAC9IVRw`, `dQw4w9WgXcQ`).
   4. **Scheduled CI Live Health Workflow (`.github/workflows/live-smoke.yml`)**:
      - Weekly scheduled and manual trigger workflow executing `pytest -m live`.

---

### Phase 5: Cipher Deciphering, Rate-Bypass Throttling & OAuth2 Authentication Suites
* **Goal**: Validate signature de-scrambling, rate-limiting bypass algorithms (throttling 'n' parameter calculation), and the OAuth2 device code / token refresh flow.
* **Deliverables**:
  1. **Signature Cipher Engine Unit Tests (`tests/unit/test_cipher.py`)**:
     - `JsonScriptEngine` action primitives: `_list`, `_join`, `_slice`, `_splice`, `_reverse`, `_swap`.
     - Script execution pipeline with parameter replacement and early `_return`.
     - `Cipher` regular expression matching for signature function extractors (`_find_signature_function_name`, `_find_function_body`, `_find_object_body`).
     - `get_signature` cache memoization and end-to-end transformation.
  2. **Rate-Bypass Throttling Arithmetic Tests (`tests/unit/test_ratebypass.py`)**:
     - Array rotation and manipulation primitives: `throttling_reverse`, `throttling_push`, `throttling_mod_func`, `throttling_unshift`, `throttling_swap`, `throttling_splice`, `throttling_nested_splice`, `throttling_prepend`.
     - `js_splice` JavaScript-compatible array splice emulation.
     - `throttling_cipher_function_a` & `throttling_cipher_function_b` character permutation ciphers.
     - `CalculateN` function code extraction, plan parsing generator, and end-to-end `calculate_n` execution with memoization.
  3. **OAuth2 Login Client Integration Tests (`tests/integration/test_login_client.py`)**:
     - Token structure conversions (list to dict, dict to list) and login state tracking (`'fully'`, `'partially'`, `False`).
     - OAuth2 device code request (`request_device_and_user_code`) and payload validation.
     - Device token polling (`request_access_token`) with graceful handling of HTTP 400 `authorization_pending`.
     - Token refresh (`refresh_token`) and `InvalidGrant` exception handling on revoked tokens.
     - Token revocation (`revoke`).

---

### Phase 6: YouTube Data API v3 Client Test Coverage Expansion
* **Goal**: Expand integration test coverage for `YouTubeDataClient` (`data_client.py`) across all major API v3 endpoints using offline fixtures and mocked responses (0 quota, 100% deterministic).
* **Deliverables**:
  1. **API v3 Fixtures (`tests/fixtures/v3_api/`)**:
     - `playlists.json`: Multi-item playlist listing payload with snippets and pagination.
     - `playlist_items.json`: Playlist items with resource IDs and snippet metadata.
     - `channel_details.json`: Channel resource with branding settings, contentDetails, and snippet.
     - `video_categories.json`: Standard YouTube category listings (Film, Music, Gaming).
     - `comments.json`: Comment threads with top-level snippet, likes, and reply structures.
  2. **Expanded Data Client Integration Suite (`tests/integration/test_data_client.py`)**:
     - **Playlists Management**: `get_playlists`, `get_playlist_items`, `get_playlist_item_id_of_video_id`, `create_playlist`, `rename_playlist`, `remove_playlist`, `add_video_to_playlist`, `remove_video_from_playlist`.
     - **Channels & Sections**: `get_channels`, handle identifier lookups (`@handle`), channel sections, and channel video listings.
     - **Subscriptions**: Listing user subscriptions (`get_subscription('mine')`), channel-specific subscriptions, `subscribe`, and `unsubscribe`.
     - **Feeds, Discovery & Categories**: `get_trending_videos`, Innertube `get_related_videos`, `get_video_categories`, `get_video_category`, `get_guide_categories`, `get_live_events`.
     - **Ratings & History**: `get_video_rating`, `rate_video` ('like'/'dislike'), `get_disliked_videos`, `update_watch_history` (playback stats).
     - **Comments & Localization**: `get_parent_comments`, `get_child_comments`, `get_supported_languages`, `get_supported_regions`.

---

### Phase 7: YouTube Player Client (Innertube) Test Coverage Expansion
* **Goal**: Expand integration and unit test coverage for `YouTubePlayerClient` (`player_client.py`) across all major playback pipelines, reaching 76.7% coverage (771 statements).
* **Deliverables**:
  1. **Player Fixtures (`tests/fixtures/innertube/`)**:
     - `player_response.json`: Updated with `initRange` and `indexRange` on adaptive formats for DASH segmenting.
     - `player_response_unplayable.json`: Unplayable/geo-restricted response with nested `errorScreen` reasons.
     - `player_response_live.json`: Live stream response with `hlsManifestUrl` and `isLive = true`.
     - `player_response_cipher.json`: Signature cipher format with encrypted `s`, `sp`, and raw URL.
  2. **Expanded Player Client Integration Suite (`tests/integration/test_player_client.py`)**:
     - **Adaptive MPEG-DASH Streaming**: `test_adaptive_stream_processing_and_mpd_manifest_generation`, `test_adaptive_streams_filtered_by_isa_capabilities`, `test_generate_mpd_manifest_creates_valid_xml`, `test_process_mpd_manifest_stream`, `test_prepare_headers`.
     - **Live HLS Streaming**: `test_live_stream_hls_manifest_parsing` (parsing master m3u8 playlists, tagging `live=True`).
     - **Signature Cipher & Throttling**: `test_signature_cipher_decryption`, `test_signature_cipher_exception_handling`, `test_signature_cipher_missing_keys`, `test_throttling_n_parameter_recalculation`, `test_throttling_disabled_returns_none`, `test_generate_cpn` (16-char nonce validation), `test_process_url_params_without_url`.
     - **Error Handling & Playability**: `test_unplayable_video_raises_youtube_exception`, `test_live_stream_offline_raises_youtube_exception`, `test_player_error_hook_structured_error`, `test_player_error_hook_unstructured_error`, `test_get_error_details_parsing` (runs and simpleText).
     - **Audio-Only & Stream Filtering**: `test_audio_only_stream_filtering`, `test_audio_only_formatting`, `test_stream_format_max_height_filter`, `test_stream_format_unknown_or_discontinued`.
     - **HTML & Web Config Extraction**: `test_get_player_key_found`, `test_get_player_key_not_found`, `test_get_player_client_static`, `test_get_player_config`, `test_get_player_config_no_match`, `test_get_player_js`, `test_get_player_js_context_config_fallback`.

---

## 4. Verification & Operational Guidelines

### A. Running Tests Locally

```powershell
# 1. Run the entire test suite
python -m pytest -v
# 1. Comprehensive Local Runner (Lint + Tests + Stats + Coverage Dashboard)
python run_tests.py
# Or via PowerShell wrapper:
.\run_tests.ps1

# 2. Run only unit tests
python -m pytest tests/unit -v
# 2. Fast Run (Sub-second, skips coverage)
python run_tests.py -f
# Or:
.\run_tests.ps1 -Fast

# 3. Run concurrency stress tests
python -m pytest tests/concurrency -v
# 3. Category-Specific Runs
python run_tests.py --suite unit
python run_tests.py --suite integration
python run_tests.py --suite concurrency

# 4. Run API integration tests
python -m pytest tests/integration -v
# 4. Include Opt-in Live Smoke Tests
python run_tests.py --live

# 5. Run tests with coverage report
python -m pytest --cov=resources/lib/youtube_plugin --cov-report=term

# 6. Run Ruff linting
# 5. Direct Pytest Invocations
python -m pytest -v
python -m ruff check tests
```

### B. CI Quality Gate Matrix

| Job | Environment | Command | Purpose |
| :--- | :--- | :--- | :--- |
| **Lint** | Ubuntu / Python 3.12 | `ruff check tests` | Static analysis, import cleanup, style |
| **Test Matrix** | Ubuntu / Py 3.8–3.13 | `pytest --cov=...` | Regression, concurrency, API parsing |
| **Add-on Check**| Ubuntu / Python 3.12 | `kodi-addon-checker ...` | Kodi official repository packaging standards |

---

## 5. Artifact & File Reference
* **Workflow Definition**: [`.github/workflows/addon-validations.yml`](file:///c:/Users/lutzh/AppData/Roaming/Kodi/addons/plugin.video.youtube/.github/workflows/addon-validations.yml)
* **Configuration**: [`pyproject.toml`](file:///c:/Users/lutzh/AppData/Roaming/Kodi/addons/plugin.video.youtube/pyproject.toml)
* **Dependencies**: [`requirements-dev.txt`](file:///c:/Users/lutzh/AppData/Roaming/Kodi/addons/plugin.video.youtube/requirements-dev.txt)
* **Emulation Suite**: [`tests/mocks/`](file:///c:/Users/lutzh/AppData/Roaming/Kodi/addons/plugin.video.youtube/tests/mocks/)
* **Fixtures**: [`tests/fixtures/`](file:///c:/Users/lutzh/AppData/Roaming/Kodi/addons/plugin.video.youtube/tests/fixtures/)
* **Test Suites**: [`tests/unit/`](file:///c:/Users/lutzh/AppData/Roaming/Kodi/addons/plugin.video.youtube/tests/unit/), [`tests/concurrency/`](file:///c:/Users/lutzh/AppData/Roaming/Kodi/addons/plugin.video.youtube/tests/concurrency/), [`tests/integration/`](file:///c:/Users/lutzh/AppData/Roaming/Kodi/addons/plugin.video.youtube/tests/integration/)
