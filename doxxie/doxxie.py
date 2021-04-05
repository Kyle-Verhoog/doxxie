import atexit
from collections.abc import Collection
from collections.abc import Mapping
import logging
import os
import pprint
from typing import Dict
from typing import List
from typing import Optional
from typing import Sequence
from typing import Set
from typing import Tuple
from typing import Type

from mypy.nodes import AssignmentStmt
from mypy.nodes import ClassDef
from mypy.nodes import Decorator
from mypy.nodes import FuncDef
from mypy.nodes import NameExpr
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


_ALL = object()


def _pick(base: Mapping, pick: Collection) -> Mapping:
    """Pick the elements of `pick` that are in `base` recursively.
    >>> _pick({"a": {"b": 3, "c": 4}}, {"a": {"b"}})
    {'a': {'b': 3}}
    >>> _pick({"a": 1, "b": 2}, {"a", "b"}) == {"a": 1, "b": 2}
    True
    >>> _pick({"a": 1, "b": 2}, {"a", "c"})
    {'a': 1}
    >>> _pick({"a": {"b": 3, "c": 4}}, {"a": {"b": {"c"}}})
    {'a': {'b': {}}}
    >>> _pick({"a": 3}, {"x": {"y": {"z"}}})
    {}
    >>> d = {"a": {"b": 3, "c": 4}, "b": 2}
    >>> _pick(d, {"a": _ALL, "b": _ALL}) == d
    True
    """
    new: Dict = {}
    next_keys = [(k, base, pick, new) for k in pick]
    while next_keys:
        key, val, pck, n = next_keys.pop()
        if isinstance(val, Mapping) and isinstance(pck, Mapping):
            if key in val:
                if pck[key] == _ALL:
                    n[key] = val[key]
                else:
                    n[key] = {}
                    next_keys.extend(
                        [(k, val[key], pck[key], n[key]) for k in pck[key]]
                    )
        elif isinstance(val, Mapping) and key in val:
            n[key] = val[key]
    return new


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

        self._deriv_outfile: Optional[str] = os.environ.get(
            "DOXXIE_DERIVE_OUTFILE", None
        )

        includes = os.environ.get("DOXXIE_INCLUDES", includes)
        self._includes: List[str] = includes.split(",") if includes else []

        excludes = os.environ.get("DOXXIE_EXCLUDES", excludes)
        self._excludes: List[str] = excludes.split(",") if excludes else []
        self._outfile = os.environ.get("DOXXIE_OUTFILE", out)
        log.debug(
            "doxxie initialized with includes=%r, excludes=%r, outfile=%r, derivfile=%r",
            self._includes,
            self._excludes,
            self._outfile,
            self._deriv_outfile,
        )

        self._api_hints: Set[str] = set()

        # A bit of a hack since mypy plugins don't get a hook for when all the
        # checking is complete.
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

    @staticmethod
    def _is_private_mod(fullname: str) -> bool:
        """
        >>> MypyPlugin._is_private_mod("mod._internal")
        True
        >>> MypyPlugin._is_private_mod("_internal.mod")
        True
        >>> MypyPlugin._is_private_mod("pub.fn.field")
        False
        >>> MypyPlugin._is_private_mod("pub.fn.field._int")
        True
        """
        split = fullname.split(".")
        for part in split:
            if part.startswith("_"):
                return True
        return False

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
            elif isinstance(node.node, Var):
                if self._is_private_attr(node.fullname):
                    continue
                api[node.node.fullname] = node
            else:
                log.debug("%r not yet supported", node.node)
        return api

    def _expand_api(
        self, api: Dict[str, SymbolTableNode]
    ) -> Dict[str, List[SymbolTableNode]]:
        """Expand the given API to include all exposed types."""
        # The resulting public API. The derivation of each member is stored so
        # that it can also be output. The last node in the list is the node
        # associated with the key.
        public_api: Dict[str, List[SymbolTableNode]] = {}

        # List of nodes to process, starting with the initial API.
        to_add: List[Tuple[List[SymbolTableNode], Optional[SymbolTableNode]]] = [
            ([], node) for node in api.values()
        ]
        while to_add:
            chain, node = to_add.pop(0)

            # Shortcut already seen items.
            if not node or not node.fullname or node.fullname in public_api:
                continue

            # Ensure to make a copy of the chain else it could be mutated later on.
            chain = chain.copy()
            chain.append(node)
            public_api[node.fullname] = chain
            # TODO: probably have to use mypy.nodes.SYMBOL_FUNCBASE_TYPES here
            # to be safe.
            if isinstance(node.node, (FuncDef, Decorator)):
                if node.type and isinstance(node.type, CallableType):
                    # Handle the return type.
                    types = map(str, self._get_types(node.type.ret_type))
                    for stype in types:
                        if self._in_includes(stype):
                            to_add.append((chain, self.lookup_fully_qualified(stype)))

                    # Handle argument types.
                    for argtype in node.type.arg_types:
                        types = map(str, self._get_types(argtype))
                        for stype in types:
                            if self._in_includes(stype):
                                to_add.append(
                                    (chain, self.lookup_fully_qualified(stype))
                                )
            # TypeInfo is used for classes.
            elif isinstance(node.node, TypeInfo):
                clsfullname = node.fullname
                for name, attr in node.node.names.items():
                    fullname = f"{clsfullname}.{name}"
                    if self._is_private_attr(fullname):
                        continue
                    to_add.append((chain, self.lookup_fully_qualified(fullname)))
                for n in node.node.mro:
                    if n.fullname and self._in_includes(n.fullname):
                        to_add.append((chain, self.lookup_fully_qualified(n.fullname)))

            elif isinstance(node.node, Var):
                if not node.type:
                    continue
                types = map(str, self._get_types(node.type))
                for stype in list(types):
                    if self._in_includes(stype):
                        to_add.append((chain, self.lookup_fully_qualified(stype)))
            else:
                # TODO: anything to handle here?
                log.debug("%r not yet supported", node.node)
        return public_api

    def _done(self) -> None:
        initial_api = self._initial_public_api()
        log.debug("initial public api %r", initial_api)
        public_api = self._expand_api(initial_api)

        # Generate the public API output.
        public_api_output = {}
        for k, c in public_api.items():
            # Last element is the actual node.
            node = c[-1]
            fullname = node.fullname
            if not fullname:
                continue

            basename = ".".join(fullname.split(".")[:-1])
            name = fullname.split(".")[-1]
            serialized = node.serialize(basename, name)

            if isinstance(node.node, FuncDef):
                out = _pick(
                    serialized,
                    {
                        "node": {
                            # Changing a kwarg to an arg can break the API.
                            "arg_kinds": _ALL,
                            # Changes to arg names break the public API.
                            "arg_names": _ALL,
                            "kind": _ALL,
                            "type": {
                                "arg_types",
                                "ret_type",
                            },
                        }
                    },
                )
                public_api_output[k] = out["node"]
            elif isinstance(node.node, TypeInfo):
                out = _pick(
                    serialized,
                    {
                        "node": {
                            # Base class changes can affect the public API.
                            "bases": _ALL,
                            # MRO changes can affect the public API.
                            "mro": _ALL,
                            "kind": _ALL,
                        },
                    },
                )
                public_api_output[k] = out["node"]
            elif isinstance(node.node, Var):
                out = _pick(
                    serialized,
                    {
                        "node": {
                            "type": _ALL,
                        },
                    },
                )
                public_api_output[k] = out["node"]

        log.debug("public api %r", public_api_output)
        with open(self._outfile, "w") as f:
            pprint.pprint(public_api_output, stream=f, width=80)

        if self._deriv_outfile:
            with open(self._deriv_outfile, "w") as f:
                derived_public_api = {
                    k: [_.fullname for _ in c] for k, c in public_api.items()
                }
                pprint.pprint(derived_public_api, stream=f, width=80)
        return

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
            if not self._in_includes(modname) or self._is_private_mod(modname):
                continue
            for defn in mod.defs:
                if isinstance(defn, (FuncDef, ClassDef, Decorator)):
                    self._api_hints.add(f"{modname}.{defn.name}")
                elif isinstance(defn, AssignmentStmt):
                    for val in defn.lvalues:
                        # TODO: Add support for TupleExpr and others listed below
                        # https://github.com/python/mypy/blob/797544d8f97c478770eb178ba966cc7b1d0e6020/mypy/nodes.py#L203
                        if isinstance(val, NameExpr):
                            name = val.name
                            self._api_hints.add(f"{modname}.{name}")
                else:
                    pass
        log.debug("collected hints %r", self._api_hints)
        return super().set_modules(modules)


def plugin(version: str) -> Type[MypyPlugin]:
    return MypyPlugin
