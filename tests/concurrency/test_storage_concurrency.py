# -*- coding: utf-8 -*-
"""
Concurrency and multi-threading stress tests for SQLite Storage.
Verifies thread-safety, statement cache isolation, and lock contention resilience.
"""
import shutil
import tempfile
import threading
import time
import pytest

from youtube_plugin.kodion.sql_store.data_cache import DataCache


@pytest.fixture(autouse=True)
def clean_memory_store():
    DataCache._memory_store.clear()
    yield
    DataCache._memory_store.clear()


@pytest.fixture
def thread_safe_datacache():
    temp_dir = tempfile.mkdtemp()
    cache_path = (temp_dir, 'concurrency_test.sqlite')
    cache = DataCache(filepath=cache_path)
    yield cache
    cache._close(event='teardown')
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.concurrency
def test_concurrent_read_write_multithreaded(thread_safe_datacache):
    """
    Stress test concurrent reads and writes across multiple worker threads.
    Verifies that CPython statement cache or SQLite concurrency does not raise
    KeyError, InterfaceError, or unhandled OperationalError.
    """
    cache = thread_safe_datacache
    num_writers = 4
    num_readers = 4
    iterations = 25
    errors = []

    # Pre-populate some keys for readers
    for i in range(20):
        cache.set_item(f'seed_key_{i}', {'val': i, 'timestamp': time.time()})

    start_event = threading.Event()

    def writer_worker(writer_id):
        start_event.wait()
        try:
            for j in range(iterations):
                key = f'w_{writer_id}_item_{j}'
                data = {'writer': writer_id, 'seq': j, 'payload': 'x' * 128}
                cache.set_item(key, data)
                time.sleep(0.001)
        except Exception as exc:
            errors.append(('writer', writer_id, exc))

    def reader_worker(reader_id):
        start_event.wait()
        try:
            for j in range(iterations):
                target_key = f'seed_key_{j % 20}'
                result = cache.get_item(target_key)
                if result is not None:
                    assert isinstance(result, dict)
                time.sleep(0.001)
        except Exception as exc:
            errors.append(('reader', reader_id, exc))

    threads = []
    for w in range(num_writers):
        t = threading.Thread(target=writer_worker, args=(w,))
        threads.append(t)
        t.start()

    for r in range(num_readers):
        t = threading.Thread(target=reader_worker, args=(r,))
        threads.append(t)
        t.start()

    # Release all threads simultaneously
    start_event.set()

    for t in threads:
        t.join(timeout=10.0)
        assert not t.is_alive(), "Worker thread timed out"

    assert not errors, f"Concurrency errors occurred: {errors}"

    # Verify that items written during stress test are intact
    for w in range(num_writers):
        for j in range(iterations):
            key = f'w_{w}_item_{j}'
            item = cache.get_item(key)
            assert item is not None
            assert item['writer'] == w
            assert item['seq'] == j


@pytest.mark.concurrency
def test_concurrent_batch_updates(thread_safe_datacache):
    """
    Stress test concurrent batch writes (set_items) across multiple threads.
    """
    cache = thread_safe_datacache
    num_threads = 4
    batch_size = 10
    errors = []
    start_event = threading.Event()

    def batch_worker(thread_id):
        start_event.wait()
        try:
            batch = {
                f'batch_{thread_id}_{k}': {'thread': thread_id, 'k': k}
                for k in range(batch_size)
            }
            cache.set_items(batch)
        except Exception as exc:
            errors.append((thread_id, exc))

    threads = [threading.Thread(target=batch_worker, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()

    start_event.set()

    for t in threads:
        t.join(timeout=10.0)
        assert not t.is_alive()

    assert not errors, f"Batch concurrency errors occurred: {errors}"

    # Verify all batches were committed
    for i in range(num_threads):
        keys = [f'batch_{i}_{k}' for k in range(batch_size)]
        retrieved = cache.get_items(keys)
        assert len(retrieved) == batch_size

