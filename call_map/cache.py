from pathlib import Path
import toolz as tz

TEXT_CACHE_SIZE = 100
_text_cache = {}  # type: Dict[Path, Tuple[int, str]]
'''_text_cache is a map into a doubly-linked list'''

_count = 0
_last = None
_first = None


def read_text_cached(path: Path) -> str:
    global _count, _first, _last

    if path == _first:
        return _text_cache[_first][-1]

    try:
        _prev, _next, text = _text_cache[path]
        hole = True
    except KeyError:
        text = path.read_text()
        hole = False

    if _count == 0:
        _text_cache[path] = (None, None, text)
        _last = _first = path
    else:
        # _first != path
        _text_cache[path] = (None, _first, text)
        _, _f_next, _f_text = _text_cache[_first]
        _text_cache[_first] = (path, _f_next, _f_text)
        _first = path

    if hole:
        _p_prev, _, _p_text = _text_cache[_prev]
        _text_cache[_prev] = _p_prev, _next, _p_text

        if _next:
            _, _n_next, _n_text = _text_cache[_next]
            _text_cache[_next] = _prev, _n_next, _n_text
        else:
            _last = _prev
    else:
        if _count == TEXT_CACHE_SIZE:
            _last = _text_cache.pop(_last)[0]
            _l_prev, _, _l_text = _text_cache[_last]
            _text_cache[_last] = (_l_prev, None, _l_text)
        else:
            _count += 1

    return text


def _get_index(path):
    # for debugging
    nn = 0
    _cur = _first
    while True:
        if _cur == path:
            return nn
        elif _cur == None:
            return

        _cur = _text_cache[_cur][1]

        nn += 1
