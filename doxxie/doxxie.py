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
from mypy.nodes import Decorator
from mypy.nodes import FuncDef
from mypy.nodes import SymbolTableNode
from mypy.nodes import TypeInfo
from mypy.nodes import Var
from mypy.options import Options
from mypy.plugin import Plugin
from mypy.types import CallableType
from mypy.types import Instance
from mypy.types import NoneType  # noqa used doctest
from mypy.types import TupleType
from mypy.types import Type as MypyType
from mypy.types import TypeList
from mypy.types import UnionType


log = logging.getLogger(__name__)


class MypyPlugin(Plugin):
    def __init__(
        self,
        opts: Options,
        includes: str = "",
        excludes: str = "",
        out: str = ".public_api",
        debug: bool = False,
    ):
        super().__init__(opts)
        if os.environ.get("DOXXIE_DEBUG", debug):
            logging.basicConfig(level=logging.DEBUG)

        includes = os.environ.get("DOXXIE_INCLUDES", includes)
        self._includes: List[str] = includes.split(",") if includes else []

        excludes = os.environ.get("DOXXIE_EXCLUDES", excludes)
        self._excludes: List[str] = excludes.split(",") if excludes else []
        self._out_file = os.environ.get("DOXXIE_OUTFILE", out)
        log.debug(
            "doxxie initialized with includes=%r, excludes=%r, outfile=%r",
            self._includes,
            self._excludes,
            self._out_file,
        )

        self._api_hints: Set[str] = set()
        atexit.register(self._done)

    def _in_includes(self, name: str) -> bool:
        """
        >>> MypyPlugin(Options())._in_includes("mod.fn")
        False
        >>> MypyPlugin(Options(), includes="mod")._in_includes("mod.fn")
        True
        >>> MypyPlugin(Options(), includes="mod")._in_includes("mod._internal")
        True
        """
        return any(name.startswith(i) for i in self._includes)

    def set_modules(self, modules):
        """Set the plugin modules.
        This method is called by mypy when new modules are processed. mypy
        typically caches the modules that it processes which means that
        this method will only be called with uncached modules. Hence it's
        recommended that the plugin only be used with the --no-incremental
        option of mypy.
        """
        log.debug("got modules %r", modules.keys())
        # At this point class attribute and method types are not yet evaluated
        # so _api_hints will only contain classes, functions and top-level
        # objects.
        for modname, mod in modules.items():
            if not self._in_includes(modname):
                continue
            for defn in mod.defs:
                if isinstance(defn, (FuncDef, ClassDef, Decorator)):
                    self._api_hints.add(f"{modname}.{defn.name}")
                else:
                    # TODO: handle top-level assignments (AssignmentStmt)
                    # eg: public_var = ExposedClass()
                    pass
        log.debug("collected hints %r", self._api_hints)
        return super().set_modules(modules)

    @staticmethod
    def _is_private_cls(fullname: str) -> bool:
        """
        >>> MypyPlugin._is_private_cls("mod.Class")
        False
        >>> MypyPlugin._is_private_cls("mod._Class")
        True
        >>> MypyPlugin._is_private_cls("_Class")
        True
        >>> MypyPlugin._is_private_cls("Class")
        False
        """
        split = fullname.split(".")
        attr = split[-1]
        if attr.startswith("_"):
            return True
        return False

    @staticmethod
    def _is_private_fn(fullname: str) -> bool:
        """
        >>> MypyPlugin._is_private_fn("_fn")
        True
        >>> MypyPlugin._is_private_fn("fn")
        False
        >>> MypyPlugin._is_private_fn("x.y._fn")
        True
        >>> MypyPlugin._is_private_fn("x._fn")
        True
        >>> MypyPlugin._is_private_fn("x.y.fn")
        False
        >>> MypyPlugin._is_private_fn("x.z")
        False
        >>> MypyPlugin._is_private_fn("mod.__init__")
        True
        """
        split = fullname.split(".")
        attr = split[-1]
        if attr.startswith("_"):
            return True
        return False

    @staticmethod
    def _is_private_attr(attr: str) -> bool:
        """
        >>> MypyPlugin._is_private_attr("mod.cls._z")
        True
        >>> MypyPlugin._is_private_attr("cls._z")
        True
        >>> MypyPlugin._is_private_attr("mod._Cls.z")
        False
        >>> MypyPlugin._is_private_attr("x.z")
        False
        >>> MypyPlugin._is_private_attr("X.__init__")
        False
        """
        split = attr.split(".")
        attr = split[-1]
        # TODO: handle other dunder methods
        if attr.startswith("_") and attr != "__init__":
            return True
        return False

    def _in_excluded(self, fullname: str) -> bool:
        """
        >>> MypyPlugin(Options())._in_excluded("a.b.c")
        False
        >>> MypyPlugin(Options(), excludes="mod.internal")._in_excluded("mod")
        False
        >>> MypyPlugin(Options(), excludes="mod.internal")._in_excluded("mod.internal")
        True
        >>> MypyPlugin(Options(), excludes="mod.internal")._in_excluded("mod.internal.x")
        True
        """
        return any(fullname.startswith(e) for e in self._excludes)

    @staticmethod
    def _get_types(typ: MypyType) -> Sequence[MypyType]:
        """Get all possible types that are used in a type.
        >>> MypyPlugin._get_types(UnionType(items=[NoneType(), NoneType()]))
        [None, None]
        """
        if isinstance(typ, (UnionType, TypeList, TupleType)):
            return typ.items
        # Handle Dict, List, etc
        elif isinstance(typ, Instance):
            # Note that typ is included as well since we don't know if the type
            # is a user defined type.
            # eg. InternalType[OtherInternalType]
            return [typ, *typ.args]
        return [typ]

    def _initial_public_api(self) -> Dict[str, SymbolTableNode]:
        """Generate the initial public API.

        The initial public API is all public objects that are exposed in public
        modules. Public objects are, by PEP-8 standards, defined to be objects
        whose names start with an underscore character.

        The initial API is built off of the hints collected from set_modules.
        """
        # Filter out any excluded modules.
        hints = [h for h in self._api_hints if not self._in_excluded(h)]
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
                log.debug("%r not yet supported", node.node)
        return api

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
            # TODO: probably have to use mypy.nodes.SYMBOL_FUNCBASE_TYPES here
            # to be safe.
            if isinstance(node.node, (FuncDef, Decorator)):
                if node.type and isinstance(node.type, CallableType):
                    # Handle the return type.
                    types = map(str, self._get_types(node.type.ret_type))
                    for stype in types:
                        if self._in_includes(stype):
                            to_add.append(self.lookup_fully_qualified(stype))

                    # Handle argument types.
                    for argtype in node.type.arg_types:
                        types = map(str, self._get_types(argtype))
                        for stype in types:
                            if self._in_includes(stype):
                                to_add.append(self.lookup_fully_qualified(stype))
            # TypeInfo is used for classes.
            elif isinstance(node.node, TypeInfo):
                clsfullname = node.fullname
                # TODO?: have to _get_types on the class here?
                for name, attr in node.node.names.items():
                    fullname = f"{clsfullname}.{name}"
                    if self._is_private_attr(fullname):
                        continue
                    to_add.append(self.lookup_fully_qualified(fullname))
                # TODO: go up MRO for additional public methods
            elif isinstance(node.node, Var):
                if not node.type:
                    continue
                types = map(str, self._get_types(node.type))
                for stype in types:
                    if self._in_includes(stype):
                        to_add.append(self.lookup_fully_qualified(stype))
            else:
                # TODO: anything to handle here?
                log.debug("%r not yet supported", node.node)
        return public_api

    def _done(self):
        initial_api = self._initial_public_api()
        log.debug("initial public api %r", initial_api)
        public_api = self._expand_api(initial_api)

        # Add types to public API.
        typed_public_api = {k: str(v) for k, v in public_api.items()}
        log.debug("typed public api %r", typed_public_api)
        with open(self._out_file, "w") as f:
            pprint.pprint(typed_public_api, stream=f, width=500)
        return


def plugin(version: str) -> Type[MypyPlugin]:
    return MypyPlugin
