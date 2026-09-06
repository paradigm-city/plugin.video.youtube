# -*- coding: utf-8 -*-
"""
Unit tests for SQLite Storage and DataCache.
"""
import shutil
import tempfile
import pytest

from youtube_plugin.kodion.sql_store.data_cache import DataCache
from youtube_plugin.kodion.sql_store.function_cache import FunctionCache


@pytest.fixture(autouse=True)
def clean_memory_store():
    DataCache._memory_store.clear()
    FunctionCache._memory_store = {}
    yield
    DataCache._memory_store.clear()
    FunctionCache._memory_store = {}


@pytest.fixture
def managed_datacache():
    temp_dir = tempfile.mkdtemp()
    cache_path = (temp_dir, 'test_storage.sqlite')
    cache = DataCache(filepath=cache_path)
    yield cache
    cache._close(event='teardown')
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def managed_funccache():
    temp_dir = tempfile.mkdtemp()
    cache_path = (temp_dir, 'test_func_storage.sqlite')
    cache = FunctionCache(filepath=cache_path)
    yield cache
    cache._close(event='teardown')
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_datacache_crud_operations(managed_datacache):
    cache = managed_datacache

    assert cache.is_empty() is True
    assert cache.get_item('nonexistent') is None

    # Set item
    payload = {'title': 'Never Gonna Give You Up', 'views': 1500000000}
    cache.set_item('video_1', payload)

    assert cache.is_empty() is False
    retrieved = cache.get_item('video_1')
    assert retrieved == payload

    # Update item
    payload['views'] += 1
    cache.set_item('video_1', payload)
    assert cache.get_item('video_1')['views'] == 1500000001

    # Delete item
    cache.del_item('video_1')
    assert cache.get_item('video_1') is None
    assert cache.is_empty() is True


def test_datacache_batch_operations(managed_datacache):
    cache = managed_datacache

    batch = {
        'item_a': {'val': 100},
        'item_b': {'val': 200},
        'item_c': {'val': 300},
    }
    cache.set_items(batch)

    retrieved = cache.get_items(['item_a', 'item_c', 'item_missing'])
    assert 'item_a' in retrieved
    assert retrieved['item_a'] == {'val': 100}
    assert 'item_c' in retrieved
    assert retrieved['item_c'] == {'val': 300}
    assert 'item_missing' not in retrieved

    # Clear all
    cache.clear()
    assert cache.is_empty() is True


def test_datacache_ttl_expiration(managed_datacache, monkeypatch):
    cache = managed_datacache

    cache.set_item('ephemeral_key', {'data': 'hello'})

    # Retrieval within 60s TTL
    assert cache.get_item('ephemeral_key', seconds=60) == {'data': 'hello'}

    # Simulate passage of time by mocking since_epoch in storage module
    from youtube_plugin.kodion.sql_store import storage as storage_mod
    original_since_epoch = storage_mod.since_epoch

    future_time = original_since_epoch() + 100
    monkeypatch.setattr(storage_mod, 'since_epoch', lambda: future_time)

    # Retrieval after 60s TTL expired
    assert cache.get_item('ephemeral_key', seconds=60) is None


def test_function_cache_memoization(managed_funccache):
    func_cache = managed_funccache
    call_counts = {'add': 0}

    def compute(a, b):
        call_counts['add'] += 1
        return a + b

    # First run computes result
    res1 = func_cache.run(compute, 300, a=5, b=10)
    assert res1 == 15
    assert call_counts['add'] == 1

    # Second run returns cached result without invoking function
    res2 = func_cache.run(compute, 300, a=5, b=10)
    assert res2 == 15
    assert call_counts['add'] == 1

    # Refresh forces recomputation
    res3 = func_cache.run(compute, 300, _refresh=True, a=5, b=10)
    assert res3 == 15
    assert call_counts['add'] == 2

    # Different arguments invokes function
    res4 = func_cache.run(compute, 300, a=20, b=30)
    assert res4 == 50
    assert call_counts['add'] == 3

