from typing import List, Tuple
import logging

import jedi
import jedi.api

from jedi._compatibility import unicode
from jedi.api import classes

from jedi.evaluate import imports
from jedi.evaluate.filters import TreeNameDefinition
from jedi.evaluate.representation import ModuleContext

from ..config import get_user_config

if tuple(map(int, jedi.__version__.split('.'))) >= (0,10,1):
    from jedi.parser.python.tree import Import as tree_Import
else:
    from jedi.parser.tree import Import as tree_Import


PROFILING = get_user_config()['PROFILING']


def usages_with_additional_modules(script: jedi.api.Script,
                                   additional_module_contexts: Tuple[ModuleContext] = ()):
    """
    Based on `jedi.api.Script.usages`, except `additional_modules` are also searched

    Forked from `jedi.api.Script.usages` on 2017-02-02.

    Return :class:`classes.Definition` objects, which contain all
    names that point to the definition of the name under the cursor. This
    is very useful for refactoring (renaming), or to show all usages of a
    variable.

    .. todo:: Implement additional_module_paths

    :rtype: list of :class:`classes.Definition`
    """
    from jedi import settings
    from jedi.api import usages
    from jedi.api import helpers
    from . import api_usages as alt_api_usages

    self = script

    temp, settings.dynamic_flow_information = \
        settings.dynamic_flow_information, False
    try:
        module_node = self._get_module_node()
        user_stmt = module_node.get_statement_for_position(self._pos)
        definition_names = self._goto()

        #assert not definition_names
        if not definition_names and isinstance(user_stmt, tree_Import):
            # For not defined imports (goto doesn't find something, we take
            # the name as a definition. This is enough, because every name
            # points to it.
            name = user_stmt.name_for_position(self._pos)
            if name is None:
                # Must be syntax
                return []
            definition_names = [TreeNameDefinition(self._get_module(), name)]

        if not definition_names:
            # Without a definition for a name we cannot find references.
            return []

        definition_names = usages.resolve_potential_imports(self._evaluator,
                                                            definition_names)

        modules = set([d.get_root_context() for d in definition_names])
        modules.add(self._get_module())
        for additional_module_context in additional_module_contexts:
            modules.add(additional_module_context)
        definitions = alt_api_usages.usages(self._evaluator, definition_names, modules)
    finally:
        settings.dynamic_flow_information = temp

    return helpers.sorted_definitions(set(definitions))


if PROFILING:
    try:
        from profilehooks import profile
    except ImportError:
        logging.getLogger(__name__).error('Failed to start with profiler; please install `profilehooks`.')

    usages_with_additional_modules = profile(usages_with_additional_modules, dirs=True, immediate=True)
