from pathlib import Path

TEXT_CACHE_SIZE = 100
_text_cache = {}
_text_cache_rankings = {}

def read_text_cached(path: Path) -> str:
    try:
        text = _text_cache[path]
        hole = _text_cache_rankings[path]
        eliminate = True
    except KeyError:
        text = path.read_text()
        _text_cache[path] = text
        hole = TEXT_CACHE_SIZE
        eliminate = False

    _text_cache_rankings[path] = 0

    for key, ranking in list(_text_cache_rankings.items()):
        if key == path:
            continue

        if ranking < hole:
            new_ranking = ranking + 1
            if new_ranking < TEXT_CACHE_SIZE:
                _text_cache_rankings[key] = new_ranking
            else:
                _text_cache.pop(key)
                _text_cache_rankings.pop(key)

    #print('-'*10, list(_text_cache_rankings.values()), len(_text_cache), len(_text_cache_rankings))

    return text