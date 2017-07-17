import jedi
import call_map.jedi_ast_tools as jat
import toolz as tz
import textwrap


def test_get_called_functions():

    test_script = """

    import call_map.jedi_ast_tools as jat


    def thunk():
        print('hi')


    def ff(node):
        aa = jat.get_called_functions(node)
        thunk()

    """

    text_script = textwrap.dedent(test_script)

    definitions = jedi.api.names(source=test_script)

    def_ff = tz.first(filter(lambda x: x.name == 'ff', definitions))
    called_by_ff = list(jat.get_called_functions(def_ff._name.tree_name.get_definition().children[-1]))

    assert len(called_by_ff) == 2
    assert {name.value for role, name, ast_node, start_pos, end_pos in called_by_ff} == {'thunk', 'get_called_functions'}
