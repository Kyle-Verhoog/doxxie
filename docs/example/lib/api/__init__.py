# api/__init__.py

from lib._internal import LeakedPrivate
from lib._internal import Private


class Public:
    def __init__(self):
        self.public_attr: int = 5
        self.public_leak: LeakedPrivate = LeakedPrivate()
        self._private: Private = Private()

    def public_method(self) -> None:
        pass

    def _private_method(self) -> str:
        return "hi"
