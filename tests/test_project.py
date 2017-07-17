
from pathlib import Path
from typing import Optional
import toolz as tz
import pytest
import json

import call_map.project_settings_module
from call_map.gui import make_app
from call_map.core import UserScopeSettings
from call_map.config import user_config


test_modules_dir = Path(__file__).parent.joinpath("test_modules")


@pytest.fixture(scope='module')
def testing_project_directory(tmpdir_factory):
    return Path(str(tmpdir_factory.mktemp('project_directory')))


@pytest.fixture(scope='module')
def second_project_directory(tmpdir_factory):
    return Path(str(tmpdir_factory.mktemp('project_directory')))


@pytest.fixture(scope='module')
def testing_ui(testing_project_directory):
    '''Returns ui_toplevel module for the app'''

    module_names = ['simple_test_package']
    #module_names = ['toolz']
    user_scope_settings = UserScopeSettings(
        module_names=module_names,
        file_names=[],
        include_runtime_sys_path=True,
        add_to_sys_path=[test_modules_dir])
    ui_toplevel = make_app(user_scope_settings,
                           project_directory=testing_project_directory,
                           enable_ipython_support=True,
                           show_gui=False)

    return ui_toplevel


def iterListWidget(ll):
    for ii in range(ll.count()):
        yield ll.item(ii)


def append_to_list_settings_widget(list_settings_widget, item_name):
    textEdit = list_settings_widget.textEdit
    jj = json.loads(textEdit.toPlainText())
    jj.append(item_name)
    textEdit.setPlainText(json.dumps(jj))
    list_settings_widget.commit()


def test_add_module(testing_ui):
    append_to_list_settings_widget(testing_ui.settings_widget.module_settings_widget,
                                   'json')
    assert 'json' in testing_ui.project.settings[call_map.project_settings_module.modules]


def test_add_bookmark(testing_ui):
    testing_ui.map_widget.callLists

    map_widget = testing_ui.map_widget

    user_config.session_overrides['MULTITHREADING'] = False
    user_config.session_overrides['EXPERIMENTAL_MODE'] = False

    # Step 1: Choose a path and bookmark it.
    for ii, target_name in enumerate(['simple_test_package', 'bb', 'bar', 'foo']):
        for item in iterListWidget(map_widget.callLists[ii]):
            if item.node.code_element.name == target_name:
                map_widget.callLists[ii].setCurrentItem(item)

    bookmarked_node_path = list(map_widget.node_path())
    bookmarks_widget = testing_ui.settings_widget.bookmarks_widget
    bookmarks_widget.addBookmark()

    # Step 2: Go down a different path.
    for ii, target_name in enumerate(['simple_test_package', 'aa']):
        for item in iterListWidget(map_widget.callLists[ii]):
            if item.node.code_element.name == target_name:
                map_widget.callLists[ii].setCurrentItem(item)

    assert not all(aa.code_element == bb.code_element
                   for aa, bb in
                   zip(map_widget.node_path(), bookmarked_node_path))

    # Step 3: Revisit bookmark
    assert bookmarks_widget.listWidget.count() == 1
    bookmarks_widget.listWidget.setCurrentRow(0)
    bookmarks_widget.visitBookmark()

    assert all(aa.code_element == bb.code_element
               for aa, bb in
               zip(map_widget.node_path(), bookmarked_node_path))



def test_change_project_directory(testing_ui, testing_project_directory,
                                  second_project_directory):

    def change_project_directory(project_directory):
        textEdit = testing_ui.settings_widget.project_settings_widget.textEdit
        jj = json.loads(textEdit.toPlainText())
        jj['project_directory'] = str(project_directory)
        textEdit.setPlainText(json.dumps(jj))
        testing_ui.settings_widget.project_settings_widget.commit()

    original_project = call_map.project_settings_module.Project(testing_project_directory)

    original_project.update_settings(original_project.load_from_persistent_storage())

    assert original_project.settings[call_map.project_settings_module.modules]

    change_project_directory(second_project_directory)
    second_project = call_map.project_settings_module.Project(second_project_directory)
    second_project.update_settings(second_project.load_from_persistent_storage())

    assert (testing_ui.settings_widget.project_settings_widget.project.project_directory
            == second_project_directory)

    assert tz.assoc_in(
        original_project.settings,
        [call_map.project_settings_module.project_settings, 'project_directory'],
        second_project.project_directory
    ) == second_project.settings

    change_project_directory(testing_project_directory)


def test_change_sys_path():
    pass


def test_change_scripts(testing_ui):
    append_to_list_settings_widget(testing_ui.settings_widget.script_settings_widget,
                                   __file__)
    assert Path(__file__) in testing_ui.project.settings[call_map.project_settings_module.scripts]