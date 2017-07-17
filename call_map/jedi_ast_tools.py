import jedi
from typing import Tuple


if tuple(map(int, jedi.__version__.split('.'))) >= (0,10,1):
    jedi_python_tree = jedi.parser.python.tree
else:
    jedi_python_tree = jedi.parser.tree
    jedi.parser.tree.Node.get_first_leaf = jedi.parser.tree.Node.first_leaf
    jedi.parser.tree.Node.get_last_leaf = jedi.parser.tree.Node.last_leaf


def leaves(node: jedi.parser.tree.Node):
    current_leaf = node.get_first_leaf()
    last_leaf = node.get_last_leaf()

    while True:
        yield current_leaf

        if current_leaf is last_leaf:
            break
        else:
            current_leaf = current_leaf.get_next_leaf()


def walk_nodes(node: jedi.parser.tree.BaseNode):
    node = getattr(node, 'base', node)

    for elt in node.children:
        if isinstance(elt, jedi.parser.tree.BaseNode):
            yield elt
            yield from walk_nodes(elt)


def walk_nodes_while_staying_in_scope(node: jedi.parser.tree.BaseNode):
    node = getattr(node, 'base', node)


    for elt in node.children:
        if isinstance(elt, jedi.parser.tree.BaseNode):
            yield elt
            if not isinstance(elt, jedi_python_tree.ClassOrFunc):
                yield from walk_nodes_while_staying_in_scope(elt)


def is_call_trailer(node: jedi.parser.tree.Node):
    """Whether the node is a trailer bounded by parens"""

    if node.type == 'trailer':
        fl = node.get_first_leaf()
        ll = node.get_last_leaf()

        return (type(fl) is jedi_python_tree.Operator
                and fl.value == '('
                and type(ll) is jedi_python_tree.Operator
                and ll.value == ')')

    else:
        return False


def _maybe_getattr_chain(obj, *attrs):
    for attr in attrs:
        obj = getattr(obj, attr, obj)

    return obj


def decorator_name(node: jedi.parser.tree.BaseNode):
    child_1 = node.children[1]
    if isinstance(child_1, jedi_python_tree.Name):
        return child_1
    else:
        name = child_1.children[-1]
        assert isinstance(name, jedi_python_tree.Name)
        return name


def vec_add(pos0: Tuple[int, int], pos1: Tuple[int, int]):
    return (pos0[0] + pos1[0], pos0[1] + pos1[1])


def get_called_functions(node: jedi.parser.tree.BaseNode):
    """Yield AST leaves that represent called functions."""

    _abort = (type(_maybe_getattr_chain(node, 'base', 'var'))
              is jedi.evaluate.compiled.CompiledObject)

    if not _abort:
        for child in walk_nodes_while_staying_in_scope(node):
            if isinstance(child, jedi_python_tree.ClassOrFunc):
                name = child.name

                if isinstance(child, jedi_python_tree.Lambda):
                    loc = (vec_add((-0,0), child.start_pos),
                           vec_add((-0,0), child.end_pos))
                else:
                    loc = ((child.start_pos[0], name.start_pos[1]), name.end_pos)

                yield ('definition', name, child) + loc
            elif is_call_trailer(child):
                name = child.get_previous_leaf()
                yield 'child', name, child, name.start_pos, name.end_pos
            elif isinstance(child, jedi_python_tree.Decorator):
                name = decorator_name(child)
                yield 'child', name, child, name.start_pos, name.end_pos


def parent_scope_of_usage(usage: jedi.api.classes.Definition) -> jedi.api.classes.Definition:
    # Like Definition.parent() but skips nameless parents.
    # Test case: jeid.evaluate.docstrings._evaluate_for_statement_string.
    try:
        return usage.parent()
    except AttributeError:
        _name =  usage._name
        while not hasattr(_name, 'name'):
            _name = _name.get_parent_scope()
        return jedi.api.classes.Definition(usage._evaluator, usage._evaluator.wrap(_name).name)


def _convert_FunctionExecutionContext_to_FunctionContext(_evaluator, context):
    '''Helper copied from `jedi.api.classes.Definition.parent` for `parent_definition`'''

    from jedi.evaluate import representation as er

    if isinstance(context, er.FunctionExecutionContext):
        # TODO the function context should be a part of the function
        # execution context.
        context = er.FunctionContext(
            _evaluator, context.parent_context, context.tree_node)

    return context


def parent_definition(definition: jedi.api.classes.Definition) -> jedi.api.classes.Definition:
    '''Robust version of `jedi.api.classes.Denition.parent`'''
    context = _convert_FunctionExecutionContext_to_FunctionContext(definition._evaluator,
                                                                   definition._name.parent_context)
    if context is None:
        return definition

    while not hasattr(context, 'name'):
        new_context = _convert_FunctionExecutionContext_to_FunctionContext(definition._evaluator,
                                                                           context.parent_context)
        if context is not None:
            context = new_context
        else:
            break

    return jedi.api.classes.Definition(definition._evaluator, context.name)
