import os
from pathlib import Path
from .qt_compatibility import QtCore
from typing import Tuple, Optional
import toolz as tz

# ignore

py_ignore = {'builtins': frozenset(['ArithmeticError',
                                    'AssertionError',
                                    'AttributeError',
                                    'BaseException',
                                    'BlockingIOError',
                                    'BrokenPipeError',
                                    'BufferError',
                                    'BytesWarning',
                                    'ChildProcessError',
                                    'ConnectionAbortedError',
                                    'ConnectionError',
                                    'ConnectionRefusedError',
                                    'ConnectionResetError',
                                    'DeprecationWarning',
                                    'EOFError',
                                    'Ellipsis',
                                    'EnvironmentError',
                                    'Exception',
                                    'False',
                                    'FileExistsError',
                                    'FileNotFoundError',
                                    'FloatingPointError',
                                    'FutureWarning',
                                    'GeneratorExit',
                                    'IOError',
                                    'ImportError',
                                    'ImportWarning',
                                    'IndentationError',
                                    'IndexError',
                                    'InterruptedError',
                                    'IsADirectoryError',
                                    'KeyError',
                                    'KeyboardInterrupt',
                                    'LookupError',
                                    'MemoryError',
                                    'NameError',
                                    'None',
                                    'NotADirectoryError',
                                    'NotImplemented',
                                    'NotImplementedError',
                                    'OSError',
                                    'OverflowError',
                                    'PendingDeprecationWarning',
                                    'PermissionError',
                                    'ProcessLookupError',
                                    'RecursionError',
                                    'ReferenceError',
                                    'ResourceWarning',
                                    'RuntimeError',
                                    'RuntimeWarning',
                                    'StopAsyncIteration',
                                    'StopIteration',
                                    'SyntaxError',
                                    'SyntaxWarning',
                                    'SystemError',
                                    'SystemExit',
                                    'TabError',
                                    'TimeoutError',
                                    'True',
                                    'TypeError',
                                    'UnboundLocalError',
                                    'UnicodeDecodeError',
                                    'UnicodeEncodeError',
                                    'UnicodeError',
                                    'UnicodeTranslateError',
                                    'UnicodeWarning',
                                    'UserWarning',
                                    'ValueError',
                                    'Warning',
                                    'ZeroDivisionError',
                                    '__IPYTHON__',
                                    '__build_class__',
                                    '__debug__',
                                    '__doc__',
                                    '__import__',
                                    '__loader__',
                                    '__name__',
                                    '__package__',
                                    '__spec__',
                                    'abs',
                                    'all',
                                    'any',
                                    'ascii',
                                    'bin',
                                    'bool',
                                    #'bytearray',
                                    #'bytes',
                                    'callable',
                                    'chr',
                                    'classmethod',
                                    #'compile',
                                    'complex',
                                    'copyright',
                                    'credits',
                                    #'delattr',
                                    'dict',
                                    'dir',
                                    #'divmod',
                                    #'dreload',
                                    'enumerate',
                                    #'eval',
                                    #'exec',
                                    'filter',
                                    'float',
                                    #'format',
                                    'frozenset',
                                    #'get_ipython',
                                    #'getattr',
                                    #'globals',
                                    #'hasattr',
                                    'hash',
                                    'help',
                                    'hex',
                                    'id',
                                    'input',
                                    'int',
                                    'isinstance',
                                    'issubclass',
                                    'iter',
                                    'len',
                                    'license',
                                    'list',
                                    #'locals',
                                    'map',
                                    'max',
                                    #'memoryview',
                                    'min',
                                    'next',
                                    'object',
                                    'oct',
                                    #'open',
                                    'ord',
                                    'pow',
                                    'print',
                                    'property',
                                    'range',
                                    'repr',
                                    'reversed',
                                    'round',
                                    'set',
                                    'setattr',
                                    'slice',
                                    'sorted',
                                    'staticmethod',
                                    'str',
                                    'sum',
                                    'super',
                                    'tuple',
                                    'type',
                                    #'vars',
                                    'zip'
                                ])}



def default_open_in_editor(path, line):
    import sys
    import logging
    import subprocess as sbp

    if sys.platform == 'darwin':
        sbp.call(['open', '--', path])
    else:
        logging.getLogger(__name__).warning(
            ' Need to define open_in_editor in call_map_rc.py')


class UserConfig:
    """
    Manages user config

    The config file at `$CALL_MAP_RC_DIRECTORY/call_map_rc.py` is watched. If
    the config file is changed, it will be re-read the next time `get_config` is
    called.

    There are three priority levels for settings: defaults, settings from the
    config file, and the override settings. The overrides are for testing. The
    user also may be allowed to change the overrides mid-session in the future.

    The main reason UserConfig is a class, and not just a collection of
    variables and functions, is for testability.

    """

    default_user_config = {'open_in_editor': default_open_in_editor,
                           'MULTITHREADING': True,
                           'UNICODE_ROLE_MARKERS': True,
                           'EXC_INFO': False,
                           'EXPERIMENTAL_MODE': False,
                           'LOG_LEVEL': None, # needs restart to take effect
                           'PROFILING': False} # needs restart to take effect

    def __init__(self, rc_dir: Optional[str]):
        self.rc_dir = rc_dir

        self._cache = None    # caches the settings

        self.watcher = QtCore.QFileSystemWatcher()
        self.watcher.fileChanged.connect(self.clear_cache)
        self.start_watcher()

        # top priority configuration settings. Used for debugging.
        self.session_overrides = {}

    def clear_cache(self, file_names: Tuple[str]):
        self._cache = None

    def start_watcher(self):
        if self.rc_dir and os.path.isdir(self.rc_dir):
            self.watcher.addPath(os.path.join(self.rc_dir, 'call_map_rc.py'))

    def read_user_config(self):
        """Read the configuration from file"""
        from sys import path as sys_path

        if self.rc_dir and os.path.isdir(self.rc_dir):
            text = Path(self.rc_dir).joinpath('call_map_rc.py').read_text()

            _namespace = {}

            exec(text, _namespace)

            result = {}

            for key in self.default_user_config:
                try:
                    result[key] = _namespace[key]
                except KeyError:
                    continue

            return result
        else:
            return {}

    def get_config(self):
        if self._cache is None:
            read_result = self.read_user_config()
            return tz.merge(self.default_user_config,
                            read_result,
                            self.session_overrides)
        else:
            return self._cache


user_config = UserConfig(rc_dir=os.getenv('CALL_MAP_RC_DIRECTORY'))
get_user_config = user_config.get_config
