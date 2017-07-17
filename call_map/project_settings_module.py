from pathlib import Path
import json
import logging
from typing import List, GenericMeta, Any, Tuple, Optional, Dict, Iterable
import toolz as tz

from .core import UserScopeSettings, ScopeSettings, CodeElement, CallPosType, Node
from . import serialize
from .custom_typing import CheckableOptional, CheckableDict, CheckableTuple, CheckableList, matches_spec


project_settings = 'project_settings'
sys_path = 'sys_path'
bookmarks = 'bookmarks'

# `files` can only changed manually
# `modules` and `scripts` can be affected by `files` but does affect `files`
files = 'files'
modules = 'modules'
scripts = 'scripts'

categories = [project_settings, sys_path, bookmarks, modules, files, scripts]

logger = logging.getLogger(__name__)

category_type = {
    project_settings: CheckableDict({'project_directory': CheckableOptional(Path)}),
    modules: CheckableList(str),
    files: CheckableList(Path),
    sys_path: CheckableList(Path),
    bookmarks: CheckableList(CheckableList(CodeElement)),
    scripts: CheckableList(Path),
}


def diff(type_spec, oo_1, oo_2):
    if isinstance(type_spec, CheckableList):
        return ([elt_1 for elt_1 in oo_1 if elt_1 not in oo_2], [elt_2 for elt_2 in oo_2 if elt_2 not in oo_1])
    elif isinstance(type_spec, CheckableTuple):
        return [(elt_1, elt_2) for elt_1, elt_2 in zip(oo_1, oo_2) if elt_1 != elt_2]
    elif isinstance(type_spec, CheckableDict):
        return {key: (oo_1.get(key), oo_2.get(key)) for key in set(oo_1.keys()) + set(oo_2.keys())}


class Project:
    def __init__(self, project_directory: Optional[Path]):

        self.project_files = {}

        self.settings = {category: _type.new_empty_instance() for category, _type in category_type.items()}
        #self.settings[project_settings] = {}

        self.project_directory_is_set_up = False    # only matters for nontrivial project_directory
        self.project_directory = project_directory

        # each Node has attributes `code_element` and `definition`.
        self.failures = {}
        self.script_nodes = {}   # type: Dict[Path, Node]; maps script path to node
        self.module_nodes = {}   # type: Dict[str, Node]; maps module name to node

    @property
    def project_directory(self) -> Optional[Path]:
        try:
            return self.settings[project_settings]['project_directory']
        except KeyError:
            return None

    @project_directory.setter
    def project_directory(self, new_project_directory: Optional[Path]):

        if new_project_directory != self.project_directory:
            self.project_directory_is_set_up = False
            self.settings[project_settings]['project_directory'] = new_project_directory

            if new_project_directory:
                self.project_files.update({rest_name: new_project_directory.joinpath(rest_name + '.json')
                                           for rest_name in categories})

    def load_scope_settings(self, scope_settings: ScopeSettings):
        self.settings[modules] = scope_settings.module_names
        self.settings[scripts] = scope_settings.scripts
        self.settings[sys_path] = scope_settings.effective_sys_path

    @property
    def scope_settings(self):
        return ScopeSettings(module_names=self.settings[modules],
                             scripts=self.settings[scripts],
                             effective_sys_path=self.settings[sys_path])

    def update_scope_settings(self, scope_settings: ScopeSettings):
        self.update_settings({modules: scope_settings.module_names,
                              scripts: scope_settings.scripts,
                              sys_path: scope_settings.effective_sys_path})

    def encode(self, category: str, for_persistence: bool):
        '''Encode settings in JSON serializable format

        :param str category: category of settings to encode.
        :param bool for_persistence: whether to filter out settings that don't need to persist

        '''
        if for_persistence and category == project_settings:
            _settings = {k:v for k,v in self.settings[category].items()
                         if k != 'project_directory'}
        else:
            _settings = self.settings[category]

        _type = category_type[category]

        return serialize.encode(_type, _settings)

    def update_persistent_storage(self):
        '''Write out to persistent storage

        Raises `FileNotFoundError` if the project directory cannot be created.

        '''
        if self.project_directory:
            if not self.project_directory_is_set_up:
                self._setup_project_directory()
                self.project_directory_is_set_up = True

            self._write_to_project_directory()

    def _setup_project_directory(self):
        # only used in update_persistent_storage
        try:
            self.project_directory.mkdir(mode=0o744, exist_ok=True)
        except FileNotFoundError:
            raise FileNotFoundError('Could not create project directory: {}'.format(self.project_directory))

        backup_directory = self.project_directory.joinpath('backup')
        try:
            backup_directory.mkdir(mode=0o744, exist_ok=True)
        except FileNotFoundError:
            raise FileNotFoundError('Could not create project backup directory: {}'.format(backup_directory))

        for ff in self.project_files.values():
            ff.touch(mode=0o644)

    def _write_to_project_directory(self):
        # only used in update_persistent_storage
        for key, project_file in self.project_files.items():
            if project_file.exists():
                backup = self.project_directory.joinpath('backup').joinpath(project_file.name)
                project_file.rename(backup)

            project_file = self.project_files[key]
            text = json.dumps(self.encode(key, for_persistence=True), indent=True, sort_keys=True)
            project_file.write_text(text + '\n')

    def load_from_persistent_storage(self):
        # precedence: files > (modules, scripts)

        # Note that `files` will only be changed manually
        # It is not updated by changing `modules` or `scripts`.
        # However, `files` will affect `modules` and `scripts`.

        decoded = {}
        if self.project_directory and self.project_directory.exists():
            for key, project_file in self.project_files.items():
                try:
                    decoded[key] = serialize.decode(category_type[key], json.loads(project_file.read_text()))
                except json.JSONDecodeError as err:
                    logger.error(err)
                except FileNotFoundError as err:
                    #logger.error(err)
                    pass

        return decoded

    def update_settings(self, new_settings: Dict[str, Any]):
        try:
            new_project_directory = new_settings[project_settings]['project_directory']
        except KeyError:
            pass
        else:
            self.project_directory = new_project_directory

        for category, value in new_settings.items():
            type_spec = category_type[category]
            settings = self.settings[category]

            if isinstance(type_spec, CheckableDict):
                settings.update(value)
            elif isinstance(type_spec, CheckableList):
                for elt in value:
                    if elt not in settings:
                        settings.append(elt)
            else:
                raise TypeError('Invalid category type {}'.format(type_spec))


    def set_settings(self, category: str, decoded: Any) -> Tuple[bool, Iterable[Node], Iterable[Node]]:
        from . import jedi_dump

        type_spec = category_type[category]

        if not matches_spec(decoded, type_spec):
            raise TypeError('Settings for {} should have type `{}`'.format(category, type_spec))

        if category == project_settings:
            self.project_directory = decoded['project_directory']
            return (True, [], [])

        old = self.settings[category]

        if isinstance(type_spec, CheckableList):
            to_delete = [elt for elt in old if elt not in decoded]  # type: List[str]
            to_add = [elt for elt in decoded if elt not in old]     # type: List[str]

            if category == modules:
                stale = []
                additional, failures = jedi_dump.dump_module_nodes(self.settings[sys_path], to_add)

                # Execute destructive operations now that we are done with
                # failure-prone operations
                self.settings[category] = decoded

                for name in to_delete:
                    stale_node =  self.module_nodes['python'].pop(name)
                    stale.append(stale_node)

                self.module_nodes['python'].update(additional)
                self.failures['python'][category].update(failures)

                self.update_usage_search_locations('python')

                return (stale or additional, stale, additional.values())

            elif category == scripts:
                stale = []
                additional, failures = jedi_dump.dump_script_nodes(self.settings[sys_path], to_add)

                # Execute destructive operations now that we are done with
                # failure-prone operations
                self.settings[category] = decoded

                for name in to_delete:
                    stale_node =  self.script_nodes['python'].pop(name)
                    stale.append(stale_node)

                self.script_nodes['python'].update(additional)
                self.failures['python'][category].update(failures)

                self.update_usage_search_locations('python')

                return (stale or additional, stale, additional.values())

            elif category == sys_path:
                self.settings[sys_path] = decoded

                platform = 'python'
                self.update_module_resolution_path(platform)
                self.make_platform_specific_nodes(platform)  # depends on self.settings[sys_path]

                return (old != decoded, to_delete, to_add)

            elif category == bookmarks:
                self.settings[bookmarks] = decoded
                return (old != decoded, to_delete, to_add)
            else:
                raise NotImplementedError

        raise NotImplementedError


    def make_platform_specific_nodes(self, platform: str):
        if platform.lower().startswith('python'):
            from . import jedi_dump

            self.failures[platform] = {}

            self.module_nodes[platform], self.failures[platform][modules] = (
                jedi_dump.dump_module_nodes(self.settings[sys_path], self.settings[modules]))

            self.script_nodes[platform], self.failures[platform][scripts] = (
                jedi_dump.dump_script_nodes(self.settings[sys_path], self.settings[scripts]))

        self.update_usage_search_locations(platform)


    def update_usage_search_locations(self, platform: str):
        '''Update the places where usages are found

        Call this whenever you load new modules or scripts.

        '''

        if platform.lower().startswith('python'):
            from . import jedi_dump

            jedi_dump.JediCodeElementNode.usage_resolution_modules = (
                frozenset((nn.module_context for nn in
                           tz.concatv(self.module_nodes[platform].values(),
                                      self.script_nodes[platform].values())
                           if nn.code_element.path)))

    def update_module_resolution_path(self, platform: str):
        if platform.lower().startswith('python'):
            from . import jedi_dump
            jedi_dump.JediCodeElementNode.sys_path = [str(pp) for pp in self.settings[sys_path]]
