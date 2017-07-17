
from pathlib import Path
from call_map.cache import read_text_cached
import call_map.cache
import random

call_map.cache.TEXT_CACHE_SIZE = 10

class FakePath:
    def __init__(self, name, text):
        self.name = name
        self.text = text

    def __hash__(self):
        return hash(self.name)

    def read_text(self):
        return self.text


def test_read_text_cached():

    paths = [FakePath(str(ii), str(ii)) for ii in range(100)]

    for path in paths[:call_map.cache.TEXT_CACHE_SIZE]:
        assert read_text_cached(path) == path.text

    assert len(call_map.cache._text_cache) == call_map.cache.TEXT_CACHE_SIZE

    for ii in range(1000):
        path = random.choice(paths)
        assert read_text_cached(path) == path.text
        assert len(call_map.cache._text_cache) == call_map.cache.TEXT_CACHE_SIZE
