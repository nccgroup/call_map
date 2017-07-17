import logging
import json as _json
from pathlib import Path as _Path

logging.getLogger(__name__).addHandler(logging.NullHandler())

_package_info = (
    _json.loads(_Path(__file__).parent.joinpath('package_info.json').read_text()))

version = _package_info['version']
