from typing import Optional
from pathlib import Path
from concurrent.futures import wait

from call_map.gui import make_app
from call_map.core import UserScopeSettings, ScopeSettings, OrganizerNode, CodeElement
from call_map.config import user_config

test_modules_dir = Path(__file__).parent.joinpath("test_modules")


def create_testing_app(project_directory: Optional[str]):
    module_names = ['simple_test_package']
    #module_names = ['toolz']
    user_scope_settings = UserScopeSettings(
        module_names=module_names,
        file_names=[],
        include_runtime_sys_path=True,
        add_to_sys_path=[test_modules_dir])
    ui_toplevel = make_app(user_scope_settings, project_directory=project_directory, enable_ipython_support=True)

    return ui_toplevel


def iterListWidget(ll):
    for ii in range(ll.count()):
        yield ll.item(ii)


def test_definition_resolution():
    # create application, open on
    ui_toplevel = create_testing_app(project_directory=None)

    map_widget = ui_toplevel.map_widget

    user_config.session_overrides['MULTITHREADING'] = False
    user_config.session_overrides['EXPERIMENTAL_MODE'] = False

    for ii, target_name in enumerate(['simple_test_package', 'aa', 'foo', 'bar']):
        for item in iterListWidget(map_widget.callLists[ii]):
            if item.node.code_element.name == target_name:
                map_widget.callLists[ii].setCurrentItem(item)
                break
        else:
            raise ValueError('Could not find {}'.format(target_name))

    # test that the 'bar' node has the correct properties. TODO: test more properties
    assert map_widget.callLists[3].currentItem().node.code_element.module == 'bb'

    #ll = map_widget.callLists[0]
    #print(ll.node)
    #print(ll.node.children)

    #print(list(iterListWidget(ui_toplevel.map_widget.callLists[0]))[0])
    #print(list(ui_toplevel.map_widget.node_path()))


def test_usages_resolution():
    # create application, open on
    ui_toplevel = create_testing_app(project_directory=None)

    map_widget = ui_toplevel.map_widget

    user_config.session_overrides['MULTITHREADING'] = False
    user_config.session_overrides['EXPERIMENTAL_MODE'] = False

    for ii, target_name in enumerate(['simple_test_package', 'bb', 'bar', 'foo']):
        for item in iterListWidget(map_widget.callLists[ii]):
            if item.node.code_element.name == target_name:
                map_widget.callLists[ii].setCurrentItem(item)

    # test that we found the usage of bar in the function `aa.foo`
    assert map_widget.callLists[3].currentItem().node.code_element.role == 'parent'
    assert map_widget.callLists[3].currentItem().node.code_element.type == 'function'
    assert map_widget.callLists[3].currentItem().node.code_element.module == 'aa'


def test_definition_resolution_with_script():
    # TODO: add a script node, test definition resolution.
    pass


def test_usages_resolution_with_script():
    # TODO: add a script node, test usages resolution.
    pass
