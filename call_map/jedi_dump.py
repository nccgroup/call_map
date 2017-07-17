"""
*Warning* this module uses jedi internals and is highly dependent on the jedi
version. Please refer to jedi-requirements.txt in the toplevel of the repo for
the version this commit is compatible with.

"""

import logging
import pprint, textwrap
from sys import path as actual_sys_path

from typing import List, Dict, Tuple, Callable, Any, Optional
from pathlib import Path

from .core import CodeElement, Node, OrganizerNode, UserScopeSettings, ScopeSettings
from . import config
from . import jedi_alt

import toolz as tz

import jedi
from .jedi_ast_tools import get_called_functions, parent_definition
from .jedi_alt.stop_signal import stop_execution_signal_queue, StopExecutionException

logger = logging.getLogger(__name__)


def catch_errors(thunk: Callable, default: Any, post_message: str):
    try:
        return thunk()
    except StopExecutionException as exc:
        logger.info('{}; {}'.format(exc, post_message))
        return default
    except Exception as exc:
        logger.error('{}; {}'.format(exc, post_message), exc_info=config.get_user_config()['EXC_INFO'])
        #import traceback
        #logger.error(traceback.format_exc())
        return default


def filter_nodes(nodes):
    for node in nodes:
        try:
            skip = (node.code_element.name in
                    config.py_ignore.get(node.code_element.module, ()))
        except AttributeError:
            skip = False

        if skip:
            continue
        else:
            yield node


def _cleanup_signal_queue():
    '''Cleans signal queue in case reference resolution finished successfully

    Call after finishing reference resolution searches. This cleans up any
    leftover signals, in case a "stop" signal was issued, but the resolution
    search actually completed successfully.

    '''

    while not stop_execution_signal_queue.empty():
        stop_execution_signal_queue.get()


class UsageFilter(jedi.evaluate.filters.ParserTreeFilter):
    def _is_name_reachable(self, name):
        #print(name, name.parent.type)
        parent = name.parent
        if parent.type in ('decorator', 'atom_expr', 'trailer'):
            return True

        if not name.is_definition():
            return False

        if parent.type == 'trailer':
            return True
        base_node = parent if parent.type in ('classdef', 'funcdef') else name
        return base_node.get_parent_scope() == self._parser_scope


class JediCodeElementNode(Node):
    usage_resolution_modules = frozenset()   # where to search for usages
    sys_path = []

    def __init__(self, code_element: CodeElement, definition: jedi.api.classes.Definition):
        """The parents call the node, children are called by the node.

        If not callable, the Node has no children
        """
        self.code_element = code_element
        self.definition = definition

    @property
    def module_context(self):
        if self.definition:
            return self.definition._name.get_root_context()
        else:
            return None

    def __repr__(self):
        return '<{}({}, call_pos={})>'.format(self.__class__.__name__, self.code_element.name, self.code_element.call_pos)

    @property
    def parents(self):
        # Note: the last created Script object appears to bork the older ones. Must keep making new Script objects!

        # Note: jedi appears to already do enough caching. It does not significantly
        # improve performance to cache the parents.

        #acceptable_name_types = (jedi.parser.tree.Name,
        #                         jedi.evaluate.representation.InstanceElement)

        if self.definition and self.definition.module_path:
            script = jedi.api.Script(source_path=self.definition.module_path,
                                     sys_path=self.definition._evaluator.sys_path,
                                     line=self.definition.line,
                                     column=self.definition.column)

            usages = catch_errors(tz.partial(jedi_alt.usages.usages_with_additional_modules,
                                             script,
                                             self.usage_resolution_modules),
                                  [],
                                  'while finding usages of {}'.format(self.code_element.name))

        elif self.code_element.call_pos[0]:
            call_pos_script = jedi.api.Script(source_path=self.code_element.call_pos[0],
                                              sys_path=self.definition._evaluator.sys_path if self.definition else self.sys_path,
                                              line=self.code_element.call_pos[1][0],
                                              column=self.code_element.call_pos[1][1])

            usages = catch_errors(tz.partial(jedi_alt.usages.usages_with_additional_modules,
                                             call_pos_script,
                                             self.usage_resolution_modules),
                                  [],
                                  'while finding usages of {}'.format(self.code_element.name))

        elif self.definition:
            script = create_import_script(self.definition._evaluator.sys_path if self.definition else self.sys_path,
                                          self.code_element.name)

            usages = [
                usage for usage in
                catch_errors(tz.partial(jedi_alt.usages.usages_with_additional_modules,
                                        script,
                                        self.usage_resolution_modules),
                             [],
                             'while finding usages of {}'.format(self.code_element.name))
                if usage.module_name]

        else:
            return ()

        _unfiltered_parents = []
        positions = set()

        for usage in usages:
            tree_name = usage._name.tree_name
            if tree_name:
                position = (usage.module_path, tree_name.start_pos, tree_name.end_pos)
            else:
                position = (None, (None, None), (None, None))

            if position not in positions or position == (None, (None, None), (None, None)):
                _usage_parent = parent_definition(usage)

                if _usage_parent.module_path:
                    JediCodeElementNode.usage_resolution_modules |= frozenset((_usage_parent._name.get_root_context(),))

                usage_node = JediCodeElementNode.from_definition(
                    'parent', position, _usage_parent)

                # check if this usage is actually the definition of the
                # current node, and is therefore already covered by the
                # "- [sig]" node.
                if (usage_node.code_element.call_pos[0] == self.code_element.path
                    and usage_node.code_element.call_pos[1] == self.code_element.start_pos
                    and usage_node.code_element.type == 'module'):

                    logger.info('Usages: Skipped definition of {} at {}:{}.'
                                .format(self.code_element.name,
                                        usage_node.code_element.name,
                                        usage_node.code_element.call_pos[1][0]))
                    continue
                else:
                    _unfiltered_parents.append(usage_node)
            positions.add(position)

        _cleanup_signal_queue()

        return _unfiltered_parents


    @property
    def children(self):
        if self.definition:

            ## If self is a package, yield submodules/subpackages
            if self.code_element.type == 'module' and self.code_element.path:
                _pp = Path(self.code_element.path)

                sys_path = self.definition._evaluator.sys_path

                is_pkg = (self.code_element.name != _pp.stem
                          and self.code_element.name == _pp.parent.stem
                          and _pp.stem == '__init__')

                if is_pkg:

                    submodules = [path_to_module_name(sys_path, str(_m)) for _m in _pp.parent.glob('*.py')
                                  if _m != _pp]

                    subdirs = [_dd for _dd in _pp.parent.iterdir()
                               if _dd.is_dir() and _dd.name != '__pycache__']

                    subpkgs = [_dd for _dd in subdirs if _dd.joinpath('__init__.py').exists()]

                    if len(subpkgs) < len(subdirs):
                        logger.warning('Package `{}` contains subdirectories that are not packages:\n{}'.format(
                            self.code_element.name,
                            textwrap.indent(
                                pprint.pformat([str(_dd.stem) for _dd in set(subdirs) - set(subpkgs)]),
                                ' ' * 4)))

                    names = submodules + [path_to_module_name(sys_path, str(_dd)) for _dd in subpkgs]

                    for _name in names:
                        _node, _err = get_module_node(sys_path, _name)
                        try:
                            yield _node
                        except KeyError:
                            continue

            if config.get_user_config()['EXPERIMENTAL_MODE']:
                yield from experimental_definitions_of_called_objects(self.definition)
            else:
                tree_name = self.definition._name.tree_name
                if not tree_name:
                    for inferred in self.definition._name.infer():
                        tree_name = inferred.tree_node
                        if tree_name:
                            break

                if tree_name:
                    tree_definition = tree_name.get_definition()

                    path = self.definition.module_path
                    _unfiltered = definitions_of_called_objects(self.definition._evaluator, tree_definition, path)

                    yield from filter_nodes(_unfiltered)

        _cleanup_signal_queue()

    @staticmethod
    def cancel_search():
        if stop_execution_signal_queue.empty():
            stop_execution_signal_queue.put(1)

    @classmethod
    def from_definition(cls, role, call_pos, definition):
        #if not isinstance(definition._name, jedi.parser.tree.Name):
        #    name = definition._name.name
        #else:
        #    name = definition._name

        start_pos = (definition.line, definition.column)
        if definition._name.tree_name:
            end_pos = definition._name.tree_name.end_pos or (None, None)
        else:
            end_pos = (None, None)

        code_element = CodeElement(
            name=definition.name,
            type=definition.type,
            module=definition.module_name,
            role=role,
            path=definition.module_path,
            call_pos=call_pos,
            start_pos=start_pos,
            end_pos=end_pos,
        )

        return cls(code_element, definition)

    def with_new_role(self, role):
        if role == 'signature':
            new_call_pos = (self.code_element.path, self.code_element.start_pos, self.code_element.end_pos)
            new_code_element = self.code_element._replace(role=role, call_pos=new_call_pos)
            return __class__(new_code_element, self.definition)
        else:
            raise NotImplementedError


def definitions_of_called_objects(evaluator: jedi.evaluate.Evaluator,
                                  definition: jedi.parser.tree.BaseNode,
                                  path: str):

    for role, fn, ast_node, call_start_pos, call_end_pos in get_called_functions(definition):
        #try:
        #    defs = list(jedi.api.helpers.evaluate_goto_definition(evaluator, fn))
        #except AttributeError:
        #    defs = list()

        code = ast_node.get_root_node().get_code()
        script = jedi.api.Script(source=code, source_path=path,
                                 sys_path=evaluator.sys_path,
                                 line=call_start_pos[0],
                                 column=call_start_pos[1])

        defs = (catch_errors(script.goto_definitions, [], 'while finding definitions of {}'.format(fn))
                or catch_errors(script.goto_assignments, [], 'while finding assignments of {}'.format(fn)))

        found = set()

        call_pos = (path, call_start_pos, call_end_pos)

        for ii, def_ in enumerate(defs):
            #def_ = defs[-1]  # should be jedi.evaluate.representation.Function

            assert isinstance(def_, jedi.api.classes.Definition)

            module = def_._module
            called_fn_def = def_
            base_name = def_.name
            try:
                start_pos, end_pos = (def_._name.tree_name.start_pos,
                                        def_._name.tree_name.end_pos)
            except AttributeError:
                start_pos, end_pos = ((None, None), (None, None))

            defined_at = (def_.module_path, start_pos, end_pos)

            if (base_name, defined_at) in found:
                continue
            else:
                found.add((base_name, defined_at))

            if ii > 0:
                name = base_name + ' ({})'.format(ii + 1)
            else:
                name = base_name

            code_element = CodeElement(
                name=name,
                type=called_fn_def.type,
                module=module.name.string_name,
                role = role,
                path = defined_at[0],
                call_pos = call_pos,
                start_pos=defined_at[1],
                end_pos=defined_at[2],
            )

            yield JediCodeElementNode(code_element, called_fn_def)

        if len(defs) == 0:
            logging.getLogger(__name__).debug(
                ' Cannot get def for {}'.format(fn))

            name = fn.value if fn.value not in (']', ')') else '[unknown]'

            if role == 'definition':
                start_pos = ast_node.start_pos
                end_pos = ast_node.end_pos
            else:
                start_pos = fn.start_pos
                end_pos = fn.end_pos

            code_element = CodeElement(
                name=name,
                type='[Unknown]',
                module='[Unknown]',
                role = role,
                path = None,
                call_pos = call_pos,
                start_pos=(None,None),
                end_pos=(None,None),
            )

            jn = JediCodeElementNode(code_element, None)

            yield jn


def experimental_definitions_of_called_objects(definition: jedi.api.classes.Definition):
    _unfiltered_nodes = []

    for context in definition._name.infer():
        _filter = UsageFilter(definition._evaluator, context, node_context=None,
                                until_position=None, origin_scope=None)
        values = jedi.api.classes._sort_names_by_start_pos(_filter.values())

        for tree_name_definition in values:
            name = jedi.api.classes.Definition(definition._evaluator, tree_name_definition)
            call_pos = (name.module_path, tree_name_definition.start_pos, tree_name_definition.tree_name.end_pos)

            assignments = name.goto_assignments()

            if assignments:
                assignment = assignments[0]
            else:
                assignment = name

            role = {'atom_expr': 'child',
                'trailer': 'child',
                'funcdef': 'definition',
                'classdef': 'definition',
            }.get(tree_name_definition.tree_name.parent.type, 'definition')

            code_element = CodeElement(
                name=name.name,
                type=name.type,
                module=assignment.module_name,
                role = role,
                path = assignment.module_path,
                call_pos = call_pos,
                start_pos=name._name.start_pos,
                end_pos=name._name.tree_name.end_pos,
            )

            node = JediCodeElementNode(code_element, name)
            _unfiltered_nodes.append(node)

    yield from filter_nodes(_unfiltered_nodes)


def _is_submodule(path: Path, parent: Path):
    for _parent in path.parents:
        if _parent == parent:
            return True
        elif _parent.joinpath('__init__.py').exists():
            continue
        else:
            return False
    else:
        return False

def path_to_module_name(sys_path, path: str):
    path = Path(path).resolve()
    for _sp in reversed(sys_path):
        try:
            sp = Path(_sp).resolve()
        except FileNotFoundError:
            continue

        if _is_submodule(path, sp):
            module_name = ('.'.join(path.relative_to(sp).parts))
            if module_name.endswith('.py'):
                module_name = module_name[:-3]
            return module_name
    else:
        return None


def create_import_script(effective_sys_path: List[Path], module_name: str) -> jedi.api.Script:
    import_script_text = 'import {}'.format(module_name)
    import_script = jedi.api.Script(source=import_script_text, sys_path=list(map(str, effective_sys_path)),
                                    line=1, column=len(import_script_text)-1)  # TODO: double check column
    return import_script


def get_module_node(effective_sys_path: List[Path], module_name: str) -> Tuple[Optional[Node], Optional[Exception]]:
    from .errors import ModuleResolutionError

    import_script = create_import_script(effective_sys_path, module_name)
    definitions = import_script.goto_definitions()

    if definitions:
        mod = tz.first(definitions)

        if tuple(map(int, jedi.__version__.split('.'))) >= (0,10,1):
            # duck punch to avoid mod._name.api_type error, which uses parent_context.
            mod._name.parent_context = mod._name.get_root_context()

        if mod.module_path:
            JediCodeElementNode.usage_resolution_modules |= frozenset((mod._name.get_root_context(),))

        node = JediCodeElementNode.from_definition(
            role='definition',
            call_pos=(mod.module_path, (1,0), (None,None)),
            definition=mod)

        err = None
    else:
        node = None
        err = ModuleResolutionError(
            'Could not resolve module {} (did you mean to use "-f"?)'.format(module_name))

    return node, err


def dump_module_nodes(effective_sys_path: List[Path], module_names: List[str]) \
    -> Tuple[Dict[str, Node], Dict[str, Node]]:

    _nodes = {}
    failures = {}

    for _name in module_names:
        node, err = get_module_node(effective_sys_path, _name)

        if node:
            _nodes[_name] = node
        else:
            failures[_name] = err

    return _nodes, failures


def remove_dupes(ll: list):
    seen = set()
    out = []

    for elt in ll:
        if elt not in seen:
            seen.add(elt)
            out.append(elt)
        else:
            continue

    return out


def make_scope_settings(is_new_project: bool,
                        saved_scope_settings: ScopeSettings,
                        user_scope_settings: UserScopeSettings) -> ScopeSettings:

    additional_sys_path = list(map(str, user_scope_settings.add_to_sys_path))  # type: List[str]

    if is_new_project:
        effective_sys_path = saved_scope_settings.effective_sys_path + additional_sys_path
    elif user_scope_settings.include_runtime_sys_path:
        effective_sys_path = actual_sys_path + additional_sys_path
    else:
        effective_sys_path = additional_sys_path

    if '' in effective_sys_path:
        del effective_sys_path[effective_sys_path.index('')]

    module_names = remove_dupes(saved_scope_settings.module_names + user_scope_settings.module_names)

    scripts = saved_scope_settings.scripts.copy() # type: List[Path]

    for path in user_scope_settings.file_names:
        module_name = path_to_module_name(effective_sys_path, path)
        if module_name is not None:
            module_names.append(module_name)
        elif path.is_file():
            scripts.append(path)
        else:
            logger.warning('Could not resolve module for {}'.format(path))

    return ScopeSettings(module_names=module_names,
                         scripts=scripts,
                         effective_sys_path=list(map(Path, effective_sys_path)))


def dump_script_nodes(effective_sys_path: List[Path], scripts: List[Path]) -> Dict[Path, Node]:
    from .errors import ScriptResolutionError

    _sys_path_str = list(map(str, effective_sys_path))  # type: List[str]

    failures = {}
    _nodes = {}  # type: Dict[Path, Node]
    for path in scripts:
        fname = str(path)
        try:
            script = jedi.api.Script(path=fname, sys_path=_sys_path_str)
        except FileNotFoundError:
            failures[path] = ScriptResolutionError('Cannot resolve path to script "{}"'.format(fname))
            continue
        except UnicodeDecodeError:
            failures[path] = ScriptResolutionError('Cannot decode script "{}"'.format(fname))
            continue

        module = script._get_module()

        children = list(
            filter_nodes(
                definitions_of_called_objects(script._evaluator, module.tree_node, path=fname)))

        node = OrganizerNode(fname, [], children)

        node.code_element = CodeElement(
            name=module.name.string_name,
            type='script',
            module=module.name.string_name,
            role='definition',
            path=str(path.resolve()),
            call_pos=(fname, (None,None), (None,None)),
            start_pos=(1,0),
            end_pos=(None, None),
        )

        node.module_context = module

        _nodes[path] = node

    return _nodes, failures
