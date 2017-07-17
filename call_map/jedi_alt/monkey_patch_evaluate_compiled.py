"""
Sometimes the unimplemented method `jedi.evaluate.CompiledObject.dict_values` is called.
TODO: make tests and push upstream
"""

import logging
from jedi.evaluate import CompiledObject

def do_monkey_patch():
    def _dict_values(self):
        logging.getLogger(__name__).warning(
            "Monkey patched function `jedi.evaluate.CompiledObject.dict_values` called.")
        return set([create(self.evaluator, val) for val in self.obj.values()])

    CompiledObject.dict_values = _dict_values
