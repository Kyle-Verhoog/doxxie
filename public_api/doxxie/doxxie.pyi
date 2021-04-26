import Any
from mypy.nodes import SymbolTableNode as SymbolTableNode
from mypy.options import Options as Options
from mypy.plugin import Plugin
from mypy.types import NoneType as NoneType
from typing import Type

log: Any

class MypyPlugin(Plugin):
    def __init__(self, opts: Any, includes: builtins.str=..., excludes: builtins.str=..., out: builtins.str=..., debug: builtins.bool=...) -> None: ...
    def set_modules(self, modules: Any): ...

def plugin(version: builtins.str) -> Type[MypyPlugin]: ...
