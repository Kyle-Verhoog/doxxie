from pkg.internal import ExposedClass10, ExposedClass3, ExposedClass6, ExposedClass7, ExposedClass9
from typing import Any, Union

class A:
    a: Any = ...
    d: pkg.internal.ExposedClass2 = ...
    e: builtins.dict[builtins.str, pkg.internal.ExposedClass11] = ...
    def __init__(self, a: builtins.int, b: builtins.str) -> None: ...
    def public_method(self) -> None: ...
    def public_method_internal_return(self) -> ExposedClass3: ...
    def public_method_internal_argument(self, arg: pkg.internal.ExposedClass5) -> None: ...
    def public_method_internal_return_union(self) -> Union[ExposedClass6, ExposedClass7]: ...
    @property
    def public_propery_internal_return(self) -> ExposedClass10: ...

def hello() -> int: ...
def public_function_internal_return() -> ExposedClass9: ...

var: Any
pub_var1: Any
pub_var2: Any
