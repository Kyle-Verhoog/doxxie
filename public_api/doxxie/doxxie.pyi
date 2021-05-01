from mypy.nodes import SymbolTableNode as SymbolTableNode
from mypy.options import Options as Options
from mypy.plugin import Plugin
from mypy.types import NoneType as NoneType
from typing import Any, Type

log: Any

class MypyPlugin(Plugin):
    def __init__(self, opts: Options, includes: str=..., excludes: str=..., out: str=..., debug: bool=...) -> None: ...
    def set_modules(self, modules: Any): ...

def plugin(version: str) -> Type[MypyPlugin]: ...
