"""
Modified version of `jedi.api.usages` from `jedi` v0.10.0.

- Removed :func:`resolve_potential_imports`.
- Added `compare_contexts` and used it in `usages`. (This was merged upstream.)
- Caught and logged errors in loop over usage items. This makes it so that if
  one item raises an error, the user can still see other usages. (This will not
  be merged upstream. Catching non-top-level errors is frowned upon in Jedi.)

"""

from jedi.api import classes
from jedi.parser import tree
from jedi.evaluate import imports
from jedi.evaluate.filters import TreeNameDefinition
from jedi.evaluate.representation import ModuleContext
import logging

logger = logging.getLogger(__name__)


def compare_contexts(c1, c2):
    return c1 == c2 or (c1[1] == c2[1] and c1[0].tree_node == c2[0].tree_node)


def usages(evaluator, definition_names, mods):
    """
    :param definitions: list of Name
    """
    def resolve_names(definition_names):
        for name in definition_names:
            if name.api_type == 'module':
                found = False
                for context in name.infer():
                    found = True
                    yield context.name
                if not found:
                    yield name
            else:
                yield name

    def compare_array(definition_names):
        """ `definitions` are being compared by module/start_pos, because
        sometimes the id's of the objects change (e.g. executions).
        """
        return [
            (name.get_root_context(), name.start_pos)
            for name in resolve_names(definition_names)
        ]

    search_name = list(definition_names)[0].string_name
    compare_definitions = compare_array(definition_names)
    mods = mods | set([d.get_root_context() for d in definition_names])
    definition_names = set(resolve_names(definition_names))
    for m in imports.get_modules_containing_name(evaluator, mods, search_name):
        if isinstance(m, ModuleContext):
            for name_node in m.tree_node.used_names.get(search_name, []):
                context = evaluator.create_context(m, name_node)
                try:
                    result = evaluator.goto(context, name_node)
                except (NotImplementedError, RecursionError) as err:
                    logger.error(err)
                    continue
                if any(compare_contexts(c1, c2)
                       for c1 in compare_array(result)
                       for c2 in compare_definitions):
                    name = TreeNameDefinition(context, name_node)
                    definition_names.add(name)
                    # Previous definitions might be imports, so include them
                    # (because goto might return that import name).
                    compare_definitions += compare_array([name])
        else:
            # compiled objects
            definition_names.add(m.name)

    return [classes.Definition(evaluator, n) for n in definition_names]
