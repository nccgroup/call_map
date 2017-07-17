import toolz as tz
import typing
import abc


class TypeSpec(metaclass=abc.ABCMeta):
    '''Used to classify objects, but is not an actual Python type

    Instead of `isinstance`, use `matches_spec` with `TypeSpec`s. Does not implement any
    other interface.

    For example, this is useful for specifying a list of strings. `TypeSpec`s
    differ from type hints, in that they can easily be checked.

    '''

    @abc.abstractmethod
    def __matches_spec__(self, obj):
        pass


def matches_spec(obj: typing.Any, type_spec: typing.Union[type, TypeSpec, typing.Iterable]):
    if isinstance(type_spec, type):
        return isinstance(obj, type_spec)
    elif isinstance(type_spec, TypeSpec):
        return type_spec.__matches_spec__(obj)
    elif tz.isiterable(type_spec):
        return any(matches_spec(obj, elt) for elt in type_spec)


class CheckableOptional(TypeSpec):
    def __init__(self, arg):
        self.nontrivial_type = arg

    def __repr__(self):
        return '<CheckableOptional {}>'.format(repr(self.nontrivial_type))

    def __matches_spec__(self, obj):
        return matches_spec(obj, (type(None), self.nontrivial_type))


class CheckableDict(TypeSpec):
    def __init__(self, types: dict):
        self.value_types = types

    def __repr__(self):
        return '<CheckableDict {}>'.format(repr(self.value_types))

    def __matches_spec__(self, obj):
        return (
            isinstance(obj, dict)
            and set(self.value_types.keys()) == set(obj.keys())
            and all(matches_spec(obj[key], val_type)
                    for key, val_type in self.value_types.items()))

    def new_empty_instance(self):
        return {key: None for key in self.value_types}


class CheckableList(TypeSpec):
    def __init__(self, value_type):
        self.value_type = value_type

    def __repr__(self):
        return '<CheckableList [{}]>'.format(repr(self.value_type))

    def __matches_spec__(self, obj):
        return (isinstance(obj, list)
                and all(matches_spec(elt, self.value_type) for elt in obj))

    def new_empty_instance(self):
        return list()


class CheckableTuple(TypeSpec):
    def __init__(self, *value_types):
        self.value_types = value_types

    def __repr__(self):
        return '<CheckableTuple ({})>'.format(repr(self.value_types))

    def __matches_spec__(self, obj):
        return (isinstance(obj, tuple)
                and all(matches_spec(elt, self.value_type) for elt in zip(obj, self.value_types)))
