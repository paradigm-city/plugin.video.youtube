# -*- coding: utf-8 -*-
"""
Unit tests for the Storage connection lifecycle:
- StorageLock re-entrancy and access counting
- Lock release when opening the database fails
- Deferred close timer scheduling and cancellation
- Flushing of deferred (memory store) writes on close
- Per-subclass SQL statements (KeyError root cause)
"""
import shutil
import tempfile
import threading

import pytest

from youtube_plugin.kodion.sql_store import storage as storage_module
from youtube_plugin.kodion.sql_store.data_cache import DataCache
from youtube_plugin.kodion.sql_store.storage import Storage, StorageLock


class IsolatedDataCache(DataCache):
    """DataCache with its own memory store and SQL statements.

    The deferred write memory store is shared by all instances of a class, so
    pending close timers of DataCache instances created by other tests could
    otherwise flush writes made here into their own database files.
    """
    _sql = {}
    _memory_store = {}


@pytest.fixture(autouse=True)
def clean_memory_store():
    IsolatedDataCache._memory_store.clear()
    yield
    IsolatedDataCache._memory_store.clear()


@pytest.fixture
def temp_dir():
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def managed_datacache(temp_dir):
    cache = IsolatedDataCache(filepath=(temp_dir, 'lifecycle.sqlite'))
    yield cache
    cache._close(event='teardown')


@pytest.fixture
def plain_datacache(temp_dir):
    """Unmodified DataCache, so that DataCache._sql is initialised."""
    cache = DataCache(filepath=(temp_dir, 'plain.sqlite'))
    yield cache
    cache._close(event='teardown')


@pytest.fixture
def fast_close_timer(monkeypatch):
    """Replace the 5 second close timer with a near immediate one."""
    timers = []

    def _timer(_interval, function, *args, **kwargs):
        timer = threading.Timer(0.01, function, *args, **kwargs)
        timers.append(timer)
        return timer

    monkeypatch.setattr(storage_module, 'Timer', _timer)
    return timers


def _is_free_for_other_threads(lock):
    """Check whether another thread can acquire the lock right now."""
    result = []

    def _try_acquire():
        acquired = lock.acquire(blocking=False)
        result.append(acquired)
        if acquired:
            lock.release()

    thread = threading.Thread(target=_try_acquire)
    thread.start()
    thread.join(timeout=5)
    return result == [True]


def _wait_for_timers(timers):
    for timer in timers:
        timer.join(timeout=5)
        assert not timer.is_alive()


# ============================================================================
# StorageLock
# ============================================================================

def test_storage_lock_is_reentrant():
    lock = StorageLock()
    with lock:
        assert lock.acquire(blocking=False) is True
        lock.release()
        assert not _is_free_for_other_threads(lock)
    assert _is_free_for_other_threads(lock)


def test_storage_lock_release_without_acquire_is_ignored():
    lock = StorageLock()
    lock.release()
    assert _is_free_for_other_threads(lock)


def test_storage_lock_access_counter_never_goes_negative():
    lock = StorageLock()
    assert lock.accessing() is False
    assert lock.accessing(start=True) is True
    assert lock.accessing(start=True) is True
    assert lock.accessing(done=True) is True
    assert lock.accessing(done=True) is False
    assert lock.accessing(done=True) is False
    assert lock.accessing() is False


# ============================================================================
# Connection lifecycle
# ============================================================================

def test_enter_releases_lock_when_database_cannot_be_opened(managed_datacache, monkeypatch):
    cache = managed_datacache
    monkeypatch.setattr(cache, '_db', None)
    monkeypatch.setattr(cache, '_open', lambda: None)

    with pytest.raises(AttributeError):
        with cache:
            pass

    assert cache._lock.accessing() is False
    assert _is_free_for_other_threads(cache._lock)


def test_exit_schedules_close_timer_and_releases_lock(managed_datacache):
    cache = managed_datacache

    with cache as (db, cursor):
        assert db is not None
        assert cursor is not None
        assert cache._lock.accessing() is True

    timer = cache._close_timer
    assert timer is not None
    assert timer.is_alive()
    assert cache._lock.accessing() is False
    assert _is_free_for_other_threads(cache._lock)


def test_enter_cancels_pending_close_timer(managed_datacache):
    cache = managed_datacache

    with cache:
        pass
    first_timer = cache._close_timer

    with cache:
        assert first_timer.finished.is_set()
        assert cache._close_timer is None

    assert cache._close_timer is not first_timer


def test_close_without_event_is_skipped_while_in_use(managed_datacache):
    cache = managed_datacache
    cache.set_item('key', {'value': 1})

    cache._lock.accessing(start=True)
    try:
        assert cache._close() is False
        assert cache._db is not None
    finally:
        cache._lock.accessing(done=True)


def test_close_with_event_closes_connection_and_reopens_on_demand(managed_datacache):
    cache = managed_datacache
    cache.set_item('key', {'value': 1})
    assert cache._db is not None

    assert cache._close(event='test') is True
    assert cache._db is None

    assert cache.get_item('key') == {'value': 1}


def test_close_flushes_deferred_writes_to_disk(managed_datacache, temp_dir):
    cache = managed_datacache
    cache.set_item('deferred', {'value': 42}, defer=True)

    assert cache._close_actions is True
    assert 'deferred' in IsolatedDataCache._memory_store

    assert cache._close() is True
    assert cache._close_actions is False
    assert not IsolatedDataCache._memory_store

    reader = IsolatedDataCache(filepath=(temp_dir, 'lifecycle.sqlite'))
    try:
        assert reader.get_item('deferred') == {'value': 42}
    finally:
        reader._close(event='teardown')


def test_close_timer_flushes_deferred_writes(managed_datacache, temp_dir, fast_close_timer):
    cache = managed_datacache
    cache.set_item('deferred', {'value': 'timer'}, defer=True)

    with cache:
        pass
    _wait_for_timers(fast_close_timer)

    assert not IsolatedDataCache._memory_store
    assert cache._close_actions is False

    reader = IsolatedDataCache(filepath=(temp_dir, 'lifecycle.sqlite'))
    try:
        assert reader.get_item('deferred') == {'value': 'timer'}
    finally:
        reader._close(event='teardown')


def test_close_timers_do_not_deadlock_concurrent_access(managed_datacache, fast_close_timer):
    cache = managed_datacache
    errors = []

    def _worker(worker_id):
        try:
            for index in range(25):
                key = 'w{0}_{1}'.format(worker_id, index)
                cache.set_item(key, {'n': index}, defer=(index % 5 == 0))
                cache.get_item(key)
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)

    workers = [threading.Thread(target=_worker, args=(n,)) for n in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=30)

    assert not any(worker.is_alive() for worker in workers), 'storage deadlocked'
    assert not errors
    _wait_for_timers(list(fast_close_timer))
    assert _is_free_for_other_threads(cache._lock)


# ============================================================================
# SQL statement initialisation (KeyError root cause)
# ============================================================================

def test_subclass_sql_is_formatted_and_isolated_from_base(plain_datacache):
    assert Storage._sql == {}
    assert DataCache._sql is not Storage._sql
    assert DataCache._sql
    for name, sql in DataCache._sql.items():
        assert '{table}' not in sql, name
    assert 'storage_v2' in DataCache._sql['set']


def test_raw_sql_templates_are_left_unformatted(plain_datacache):
    assert '{table}' in Storage._raw_sql['set']
    assert '{table}' in Storage._raw_sql['create_table']


def test_migrate_instance_uses_own_table_without_touching_class_sql(plain_datacache, temp_dir):
    class_sql = dict(DataCache._sql)

    migrated = Storage(filepath=(temp_dir, 'migrate.sqlite'), migrate='legacy_table')
    try:
        assert 'legacy_table' in migrated._sql['set']
        assert 'storage_v2' not in migrated._sql['set']
        assert Storage._sql == {}
        assert DataCache._sql == class_sql
    finally:
        migrated._close(event='teardown')
