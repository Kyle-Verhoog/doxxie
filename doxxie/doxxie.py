import atexit
import logging
import os
import pprint
from typing import Dict
from typing import List
from typing import Optional
from typing import Sequence
from typing import Set
from typing import Type

from mypy.nodes import ClassDef
from mypy.nodes import FuncDef
from mypy.nodes import SymbolTableNode
from mypy.nodes import TypeInfo
from mypy.nodes import Var
from mypy.plugin import Plugin
from mypy.types import CallableType
from mypy.types import Type as MypyType
from mypy.types import UnionType


log = logging.getLogger(__name__)


class MypyPlugin(Plugin):
    def __init__(self, opts):
        super().__init__(opts)
        if os.environ.get("DOXXIE_DEBUG", False):
            logging.basicConfig(level=logging.DEBUG)

        self._api_hints: Set[str] = set()

        includes = os.environ.get("DOXXIE_INCLUDES", "")
        self._includes: List[str] = includes.split(",") if includes else []

        excludes = os.environ.get("DOXXIE_EXCLUDES", "")
        self._excludes: List[str] = excludes.split(",") if excludes else []
        self._out_file = os.environ.get("DOXXIE_OUTFILE", ".public_api")
        log.debug(
            "doxxie initialized with includes=%r, excludes=%r, outfile=%r",
            self._includes,
            self._excludes,
            self._out_file,
        )
        atexit.register(self._done)

    def _in_includes(self, name: str) -> bool:
        return any(name.startswith(i) for i in self._includes)

    def set_modules(self, modules):
        log.debug("got modules %r", modules.keys())
        # At this point class attributes and methods are not yet evaluated.
        for modname, mod in modules.items():
            if not self._in_includes(modname):
                continue
            for defn in mod.defs:
                if any(isinstance(defn, typ) for typ in [FuncDef, ClassDef]):
                    self._api_hints.add(f"{modname}.{defn.name}")
                else:
                    # TODO: handle top-level assignments (AssignmentStmt)
                    # eg: public_var = ExposedClass()
                    pass
        log.debug("collected hints %r", self._api_hints)
        return super().set_modules(modules)

    @staticmethod
    def _is_private_cls(fullname: str) -> bool:
        split = fullname.split(".")
        attr = split[-1]
        if attr.startswith("_"):
            return True
        return False

    @staticmethod
    def _is_private_fn(fullname: str) -> bool:
        split = fullname.split(".")
        attr = split[-1]
        if attr.startswith("_"):
            return True
        return False

    @staticmethod
    def _is_private_attr(attr: str) -> bool:
        """
        >>> MypyPlugin._is_private_attr("x.y._z")
        True
        >>> MypyPlugin._is_private_attr("x._z")
        True
        >>> MypyPlugin._is_private_attr("x.y.z")
        False
        >>> MypyPlugin._is_private_attr("x.z")
        False
        """
        split = attr.split(".")
        attr = split[-1]
        # TODO: handle other dunder methods
        if attr.startswith("_") and attr != "__init__":
            return True
        return False

    def _initial_public_api(self) -> Dict[str, SymbolTableNode]:
        # Filter out any excluded modules.
        hints = [
            h
            for h in self._api_hints
            if not any(h.startswith(i) for i in self._excludes)
        ]
        api = {}
        for name in hints:
            node = self.lookup_fully_qualified(name)
            if not node or not node.fullname:
                continue
            if isinstance(node.node, TypeInfo):
                if self._is_private_cls(node.fullname):
                    continue

                api[name] = node
                # Add all the public class attributes.
                for name, item in node.node.names.items():
                    if self._is_private_attr(name):
                        continue
                    if item.fullname:
                        api[item.fullname] = item
            elif isinstance(node.node, FuncDef):
                if self._is_private_fn(node.fullname):
                    continue
                api[node.node.fullname] = node
            else:
                raise NotImplementedError
        return api

    @staticmethod
    def _get_types(typ: MypyType) -> Sequence[MypyType]:
        # TODO: handle list, dict, etc - way to handle arbitrary?
        if isinstance(typ, UnionType):
            return typ.items
        return [typ]

    def _expand_api(
        self, api: Dict[str, SymbolTableNode]
    ) -> Dict[str, SymbolTableNode]:
        public_api: Dict[str, SymbolTableNode] = {}
        to_add: List[Optional[SymbolTableNode]] = list(api.values())
        while to_add:
            node = to_add.pop(0)

            # Shortcut already seen items.
            if not node or not node.fullname or node.fullname in public_api:
                continue

            public_api[node.fullname] = node
            if isinstance(node.node, FuncDef):
                if node.type and isinstance(node.type, CallableType):
                    # Handle the return type.
                    types = map(str, self._get_types(node.type.ret_type))
                    for stype in types:
                        if self._in_includes(stype):
                            to_add.append(self.lookup_fully_qualified(stype))

                    # Handle argument types.
                    for argtype in node.type.arg_types:
                        types = map(str, self._get_types(node.type.ret_type))
                        for stype in types:
                            if self._in_includes(stype):
                                to_add.append(self.lookup_fully_qualified(stype))
            elif isinstance(node.node, TypeInfo):
                clsfullname = node.fullname
                for name, attr in node.node.names.items():
                    fullname = f"{clsfullname}.{name}"
                    if self._is_private_attr(fullname):
                        continue
                    to_add.append(self.lookup_fully_qualified(fullname))
                # TODO: go up MRO for additional public methods
            elif isinstance(node.node, Var):
                stype = str(node.type)
                if self._in_includes(stype):
                    to_add.append(self.lookup_fully_qualified(stype))
            else:
                # TODO: anything to handle here?
                pass
        return public_api

    def _done(self):
        initial_api = self._initial_public_api()
        log.debug("initial public api %r", initial_api)
        public_api = self._expand_api(initial_api)

        # Add types to public API.
        typed_public_api = {k: str(v) if v.node else v for k, v in public_api.items()}
        with open(self._out_file, "w") as f:
            pprint.pprint(typed_public_api, stream=f, width=250)
        return


def plugin(version: str) -> Type[MypyPlugin]:
    return MypyPlugin
