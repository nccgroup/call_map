from typing import Union, Dict, List, Any, Callable, Tuple
from pathlib import Path
import toolz
from .core import CodeElement
from .custom_typing import CheckableOptional, CheckableDict, CheckableList, CheckableTuple

NoneType = type(None)

py_type = 'py_type'
value = 'value'

encoding_fns = {}
decoding_fns = {}

class DecodeError(Exception):
    pass


def register(py_type: Any, encoder: Callable, decoder: Callable):
    """Register JSON encoding name and JSON encoding/decoding functions"""
    encoding_fns[py_type] = encoder
    decoding_fns[py_type] = decoder


def encode(type_spec, oo: Any):
    """Encode a Python object to JSON serializable form"""

    if isinstance(type_spec, CheckableDict):
        return {k: encode(type_spec.value_types[k], v) for k, v in oo.items()}

    elif isinstance(type_spec, CheckableOptional):
        if oo is not None:
            return encode(type_spec.nontrivial_type, oo)
        else:
            return None

    elif isinstance(type_spec, CheckableList):
        return [encode(type_spec.value_type, elt) for elt in oo]

    elif isinstance(type_spec, CheckableTuple):
        return tuple(encode(elt_type, elt) for elt_type, elt in zip(type_spec.value_types, oo))

    else:
        try:
            return encoding_fns[type_spec](oo)
        except KeyError:
            raise TypeError('Cannot encode {}'.format(repr(oo)))


def decode(type_spec, oo: Union[Dict[str, Any], List, str, int, type(None)]):
    """Decode a Python object encoded by `encode`"""
    try:
        if isinstance(type_spec, CheckableDict):
            return {k: decode(type_spec.value_types[k], v) for k, v in oo.items()}

        elif isinstance(type_spec, CheckableOptional):
            if oo is not None:
                return decode(type_spec.nontrivial_type, oo)
            else:
                return None

        elif isinstance(type_spec, CheckableList):
            return [decode(type_spec.value_type, elt) for elt in oo]

        elif isinstance(type_spec, CheckableTuple):
            return tuple(decode(elt_type, elt) for elt_type, elt in zip(type_spec.value_types, oo))

        elif type_spec in decoding_fns:
            return decoding_fns[type_spec](oo)

        else:
            raise TypeError

    except (TypeError, AttributeError, KeyError) as err:
        raise DecodeError('Cannot decode `{}` as type {}; {}'.format(oo, type_spec, err))



def encode_code_element(ce):
    return ce._asdict()

def decode_code_element(encoded):
    ce1 = CodeElement(**encoded)
    path, line, column = ce1.call_pos
    return ce1._replace(call_pos=(path, tuple(line), tuple(column)),
                        start_pos=tuple(ce1.start_pos),
                        end_pos=tuple(ce1.end_pos))


register(Path, encoder=str, decoder=Path)
register(str, encoder=toolz.identity, decoder=toolz.identity)
register(int, encoder=toolz.identity, decoder=toolz.identity)
register(float, encoder=toolz.identity, decoder=toolz.identity)
register(NoneType, encoder=toolz.identity, decoder=toolz.identity)
register(CodeElement, encoder=encode_code_element, decoder=decode_code_element)
