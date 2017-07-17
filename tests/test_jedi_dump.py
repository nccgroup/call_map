import toolz as tz

from load_test_modules import root_node, test_modules_dir
from call_map.config import user_config

use_decorators_node = tz.first(node for node in root_node.children
                               if node.code_element.name == 'use_decorators')

use_comprehension_node = tz.first(node for node in root_node.children
                                  if node.code_element.name == 'use_comprehension')

def test_decorator_child():
    user_config.session_overrides['EXPERIMENTAL_MODE'] = False

    children = list(use_decorators_node.children)

    assert children

    assert any(
        node.code_element.name == 'dec'
        and node.code_element.call_pos == (str(test_modules_dir.joinpath('use_decorators.py')), (7, 1), (7, 4))
        for node in children
    )


def test_comprehension():
    user_config.session_overrides['EXPERIMENTAL_MODE'] = False

    nodes = [node for node in use_comprehension_node.children
             if node.code_element.name == 'ff']

    assert nodes

    ff_node = tz.first(nodes)

    fn_with_comprehension_node = tz.first(
        node for node in use_comprehension_node.children
        if node.code_element.name == 'fn_with_comprehension'
    )

    assert any(node.code_element.name == 'fn_with_comprehension' for node in ff_node.parents)
    assert any(node.code_element.name == 'ff' for node in fn_with_comprehension_node.children)
