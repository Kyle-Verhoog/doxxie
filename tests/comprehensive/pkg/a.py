from typing import Dict
from typing import Union

from pkg.internal import ExposedClass2
from pkg.internal import ExposedClass3
from pkg.internal import ExposedClass5
from pkg.internal import ExposedClass6
from pkg.internal import ExposedClass7
from pkg.internal import ExposedClass8
from pkg.internal import ExposedClass9
from pkg.internal import ExposedClass10
from pkg.internal import ExposedClass11
from pkg.internal import InternalClass


class A:
    def __init__(self, a: int, b: str) -> None:
        self.a = a
        self._b = b
        self._c: InternalClass = InternalClass(a, b)
        self.d: ExposedClass2 = ExposedClass2()
        self.e: Dict[str, ExposedClass11] = dict()

    def public_method(self):
        pass

    def _private_method(self):
        pass

    def public_method_internal_return(self) -> ExposedClass3:
        return ExposedClass3()

    def public_method_internal_argument(self, arg: ExposedClass5) -> None:
        return

    def public_method_internal_return_union(
        self,
    ) -> Union[ExposedClass6, ExposedClass7]:
        return ExposedClass6()

    @property
    def public_propery_internal_return(self) -> ExposedClass10:
        return ExposedClass10()


class _A:
    pass


def hello() -> int:
    return 3


def public_function_internal_return() -> ExposedClass9:
    return ExposedClass9()


def _hello():
    return


var = ExposedClass8()
