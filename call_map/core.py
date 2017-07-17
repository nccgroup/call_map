import typing
import collections
import abc

from typing import List, Tuple, Optional
from pathlib import Path


LocationType = Tuple[Optional[int], Optional[int]]
CallPosType = Tuple[Optional[str], LocationType, LocationType]

CodeElement = typing.NamedTuple(
    'CodeElement', [('name', str),
                    ('type', str),    # not sure
                    ('module', str),
                    ('role', str),
                    ('path', Optional[str]),
                    ('call_pos', CallPosType),
                    ('start_pos', LocationType),
                    ('end_pos', LocationType)])


class Node(metaclass=abc.ABCMeta):
    """Every node must have attributes `name` and `role`

    The Node is responsible for catching all exceptions arising from the
    analysis backend when searching for connected nodes.

    """

    @property
    @abc.abstractmethod
    def parents(self):
        pass

    @property
    @abc.abstractmethod
    def children(self):
        pass

    @property
    @abc.abstractmethod
    def cancel_search(self):
        '''Cancel pending search for related nodes'''
        pass


class OrganizerNode(Node):
    def __init__(self, name, parents=None, children=None):
        """The parents call the node, children are called by the node.

        If not callable, the Node has no children
        """
        self._parents = parents if parents is not None else []
        self._children = children if children is not None else []
        self.code_element = CodeElement(name=name,
                                        type='organizer',
                                        module='[None]',
                                        role='definition',
                                        path=None,
                                        call_pos=(None, (None,None), (None,None)),
                                        start_pos = (None, None),
                                        end_pos = (None, None))

    @property
    def parents(self):
        return self._parents

    @property
    def children(self):
        return self._children

    def cancel_search(self):
        pass


UserScopeSettings = typing.NamedTuple('UserScopeSettings', [('module_names', List[str]),
                                                            ('file_names', List[Path]),
                                                            ('include_runtime_sys_path', bool),
                                                            ('add_to_sys_path', List[Path])])

ScopeSettings = typing.NamedTuple('ScopeSettings', [('module_names', List[str]),
                                                    ('scripts', List[Path]),
                                                    ('effective_sys_path', List[Path])])
