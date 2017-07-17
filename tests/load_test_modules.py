import toolz as tz

from call_map.core import UserScopeSettings, ScopeSettings, OrganizerNode
from call_map.jedi_dump import make_scope_settings
from call_map import project_settings_module
from call_map.project_settings_module import Project
from pathlib import Path
from sys import path as runtime_sys_path

test_modules_dir = Path(__file__).parent.joinpath('test_modules')

user_scope_settings = UserScopeSettings(
    module_names=[],
    file_names=test_modules_dir.glob('*.py'),
    include_runtime_sys_path=True,
    add_to_sys_path=([str(test_modules_dir)] + runtime_sys_path),
)

scope_settings = make_scope_settings(is_new_project=True,
                                     saved_scope_settings=ScopeSettings([], [], []),
                                     user_scope_settings=user_scope_settings)  # type: ScopeSettings

project = Project(None)

project.settings.update(
    {project_settings_module.modules: scope_settings.module_names,
     project_settings_module.scripts: scope_settings.scripts,
     project_settings_module.sys_path: scope_settings.effective_sys_path})

project.make_platform_specific_nodes('python')

root_node = OrganizerNode('Root', [],
                          list(tz.concatv(project.module_nodes['python'].values(),
                                          project.script_nodes['python'].values())))
