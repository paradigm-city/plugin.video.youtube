# SQLite Concurrency & KeyError Fix

## Executive Summary

The `sql_key_error_fix` branch addresses a critical, hard-to-diagnose concurrency bug in `plugin.video.youtube`'s SQLite storage layer (`resources/lib/youtube_plugin/kodion/sql_store/storage.py`). 

Under heavy multi-threaded usage in Kodi (such as concurrent thumbnail fetching, video metadata scraping, and list generation), the addon frequently logged SQLite execution failures:
```text
storage:519(_execute) Failed - Attempt 1 of 3
Query:  'SELECT * FROM storage_v2 WHERE key = ?;'
Values: ('4fd07c6b64fa22cc15e273270784e0ce',)
KeyError: ('SELECT * FROM storage_v2 WHERE key = ?;',)
```

This branch resolves the issue at its root cause by introducing true reentrant thread synchronization (`RLock`), protecting both the SQLite database connection and the in-memory cache, separating raw SQL templates from formatted instances, increasing the SQLite busy timeout, and hardening cursor error recovery.

---

## The Root Cause: Why `KeyError` in `cursor.execute()`?

At first glance, a `KeyError` raised directly from `cursor.execute(query, _values)` seems impossible because `execute` is a database driver method, not a dictionary lookup.

### 1. The `pysqlite` Internal Statement Cache
Python's standard library `sqlite3` module (implemented in C as `_sqlite3` / `pysqlite`) maintains an internal statement cache for each `sqlite3.Connection`. This cache maps query strings (tuples containing the SQL text) to compiled SQLite prepared statements to avoid re-compilation overhead.

### 2. Multi-Threaded Contention Without a Mutex
The addon connects to SQLite with `check_same_thread=False` to allow background worker threads to interact with the database. However, the original `StorageLock` implementation was merely a counter (`_num_accessing`) and did **not** actually acquire a lock when entering `Storage.__enter__`.

When multiple threads concurrently executed queries on the shared connection:
1. Two or more threads attempted to look up or insert into the C-extension's internal statement cache simultaneously.
2. The internal cache dictionary suffered race conditions, leading to internal cache misses or state corruption.
3. Python's C-API raised `KeyError: ('<SQL query string>',)`.

### 3. Immediate Abort in `_execute`
In the original implementation of `_execute()`, only `sqlite3.OperationalError` (ignored for retry) and `sqlite3.InterfaceError` (re-created cursor) were caught. Any unexpected exception—including `KeyError`—triggered `abort = True` on the very first attempt, immediately aborting the database operation and failing the user's request.

---

## Evolution of the Fix Across Commits

The branch consists of two commits representing the progression from symptom mitigation to root-cause resolution:

1. **Commit `4e99911e` (`fix: Corrected the SQL query to properly handle key errors...`)**:
   - **Symptom Mitigation**: Caught `KeyError` alongside `sqlite3.InterfaceError` in `_execute()`.
   - When a `KeyError` occurred, it refreshed the cursor from `self._db` and retried the query up to 3 times rather than aborting immediately.
   - While this mitigated crashes, it did not stop the underlying race conditions causing the cache corruption.

2. **Commit `91b915f0` (`Fix SQLite Concurrency & The KeyError Root Cause`)**:
   - **Root-Cause Architectural Fix**: Implemented comprehensive mutual exclusion across all SQLite database operations, in-memory cache operations, and connection lifecycles.
   - Refactored `StorageLock` to act as a genuine reentrant lock (`threading.RLock`).
   - Hardened cursor re-creation, increased lock timeouts, and ensured template immutability.

---

## Core Concepts and Architectural Changes

### 1. Reentrant Mutex Locking (`StorageLock`)
`StorageLock` was refactored from a loose counter into an active mutex wrapper around Python's `threading.RLock`:
- `__enter__()` now calls `self._lock.acquire()` directly.
- Added explicit `acquire(*args, **kwargs)` and `release()` methods.
- Counter manipulations (`accessing()`) are wrapped in `with self._lock:`.
- `Storage.__enter__()` acquires `self._lock`, and `Storage.__exit__()` guarantees release via a `finally:` block.
- All public and private storage methods (`_get`, `_get_by_ids`, `_set`, `_set_many`, `_update`, `_refresh`, `_remove`, `_remove_many`, `clear`, `is_empty`, `_close`, `_execute`) are wrapped in `with self._lock:`.
- Because `RLock` is reentrant, nested calls within the same thread (e.g., `_set` calling `with self as (db, cursor):` followed by `_execute`) do not deadlock.

### 2. In-Memory Store Thread Safety
Each `Storage` instance maintains an optional `self._memory_store` dictionary for deferred writes and fast lookups. Python dictionaries are not thread-safe under concurrent mutation and iteration. All operations modifying or iterating `_memory_store` (e.g., in `_set_many`, `_get_by_ids`, `_remove_many`) are now fully protected by `self._lock`.

### 3. Template Immutability (`_raw_sql` vs `_sql`)
- **Previously**: The `Storage` class defined `_sql` containing query templates with format placeholders (`{table}`, `{order_col}`). During `__init__`, `self._base._sql.update(...)` formatted these queries in place, mutating the shared class dictionary. Subclasses or migrations could corrupt or overwrite the templates.
- **Now**: 
  - `_raw_sql` holds immutable template strings.
  - `_sql` is instantiated as an instance/class-specific dictionary containing formatted queries.
  - `_raw_sql` is never mutated, eliminating cross-instance query corruption.

### 4. SQLite Busy Timeout Increase
- Increased `PRAGMA busy_timeout = 1000;` (1 second) to `PRAGMA busy_timeout = 10000;` (10 seconds).
- In Kodi, where multiple subsystems may access SQLite databases simultaneously (e.g. during library scans), 1 second was frequently insufficient, causing `sqlite3.OperationalError: database is locked`. The 10-second timeout allows threads to wait for lock release gracefully.

### 5. Defensive Cursor Recovery & Exception Handling
In `_execute()`:
```python
except Exception as exc:
    if isinstance(exc, sqlite3.OperationalError):
        pass
    elif isinstance(exc, (sqlite3.InterfaceError, KeyError)):
        if self._db:
            try:
                cursor = self._db.cursor()
            except Exception:
                pass
    else:
        abort = True
```
- Both `KeyError` and `InterfaceError` trigger cursor re-creation.
- Re-creating the cursor is safely wrapped in `try...except` to prevent cascading failures if the connection is temporarily invalid.
- Retries continue up to 3 attempts with exponential/linear backoff (`time.sleep(0.1)`).

### 6. Timer Lifecycle Synchronization
The database auto-close timer (`self._close_timer`) is now safely manipulated exclusively within `self._lock`. When entering a storage context, any pending close timer is cancelled and set to `None`. In `_close()`, active access checks (`self._lock.accessing()`) and database shutdown routines are guarded to prevent a timer thread from closing a connection while a query thread is executing.

---

## Summary of Affected Subsystems

The `Storage` class in `kodion/sql_store/storage.py` serves as the base class for key data stores in `plugin.video.youtube`:

| Store | Purpose | Concurrency Impact |
|---|---|---|
| `DataCache` | General data cache for API responses | High: Accessed simultaneously by UI and background loaders |
| `FunctionCache` | Caching function call results | High: Accessed across various plugin endpoints |
| `RequestCache` | HTTP request and response caching | High: Multiple parallel HTTP requests hit the cache |
| `PlaybackHistory` | Tracks watched videos and resume points | Moderate: Updated on playback events |
| `SearchHistory` | Stores user search queries | Low to Moderate: Updated on user interaction |
| `BookmarksList` / `WatchLaterList` | User playlist management | Moderate: Read during navigation, written on bookmarking |

By establishing strict thread safety and eliminating race conditions in `Storage`, all dependent caches and stores operate reliably without triggering `KeyError` or crashing concurrent operations.

