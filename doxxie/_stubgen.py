#!/usr/bin/env python3
"""Generate PEP-484 type stubs for the public API of a mypy-typed Python package.

This module wraps mypy's ``stubgen`` to produce stubs that contain *only* the
public API surface of a library.  Internal types that leak into the public API
(via return types, argument types, or attribute annotations) are automatically
included in the output so that the stubs remain self-consistent.

Usage::

    doxxie --public-api-only -p mypkg -o public_api
    doxxie --public-api-only -p mypkg -e mypkg.vendor -o public_api
"""

import argparse
import os
import sys
from typing import Dict, List, Optional, Sequence, Set

from mypy.lookup import lookup_fully_qualified
from mypy.nodes import (
    ClassDef,
    Decorator,
    FuncDef,
    MypyFile,
    OverloadedFuncDef,
    TypeInfo,
    Var,
)
from mypy.stubgen import (
    ASTStubGenerator,
    Options as StubgenOptions,
    collect_build_targets,
    generate_asts_for_modules,
    mypy_options,
)
from mypy.types import (
    CallableType,
    Instance,
    TupleType,
    Type,
    UnionType,
)


# ---------------------------------------------------------------------------
# Private-name detection
# ---------------------------------------------------------------------------

def _is_private_name(name: str) -> bool:
    """A name is private if it starts with ``_`` and is not a public dunder.

    Metadata dunders (__all__, __version__, etc.) and display dunders
    (__repr__, __str__) are considered private for API-surface purposes.
    """
    if not name.startswith("_"):
        return False
    if not name.endswith("__"):
        return True  # single-underscore prefix → private
    # It is a dunder.  Some dunders are excluded from the public surface.
    return name in _IGNORED_DUNDERS


_IGNORED_DUNDERS = frozenset({
    "__all__",
    "__author__",
    "__version__",
    "__about__",
    "__copyright__",
    "__email__",
    "__license__",
    "__summary__",
    "__title__",
    "__uri__",
    "__str__",
    "__repr__",
    "__getattr__",
    "__slots__",
})


# ---------------------------------------------------------------------------
# Type helpers
# ---------------------------------------------------------------------------

def _get_types(typ: Type) -> Sequence[Type]:
    """Decompose a compound type into its constituent types."""
    if isinstance(typ, (UnionType, TupleType)):
        return typ.items
    if isinstance(typ, Instance):
        return [typ, *typ.args]
    return [typ]


# ---------------------------------------------------------------------------
# Phase 1 – discover the initial public API from module symbol tables
# ---------------------------------------------------------------------------

def _collect_public_names(
    mod_ast: MypyFile,
    excludes: List[str],
    public_api: Set[str],
) -> None:
    """Walk the symbol table of *mod_ast* and add public names to *public_api*."""
    if any(mod_ast.fullname.startswith(e) for e in excludes):
        return
    if _is_private_name(mod_ast.name):
        return
    public_api.add(mod_ast.fullname)

    for name, sym in mod_ast.names.items():
        if _is_private_name(name):
            continue
        node = sym.node
        if isinstance(node, (FuncDef, Decorator)):
            public_api.add(node.fullname)
        elif isinstance(node, TypeInfo):
            if not node.name.startswith("_"):
                public_api.add(node.fullname)
        elif isinstance(node, Var):
            public_api.add(node.fullname)
        elif isinstance(node, OverloadedFuncDef):
            pass  # skip overloaded functions


# ---------------------------------------------------------------------------
# Phase 2 – expand the public API by following type references
# ---------------------------------------------------------------------------

def find_public_api(
    py_modules: list,
    excludes: List[str],
    files: Dict[str, MypyFile],
) -> Set[str]:
    """Return the set of fully-qualified names that form the public API.

    Starting from the initial public symbols, the algorithm transitively
    includes any internal types that are *reachable* through public function
    signatures, class attributes, or variable annotations.
    """
    # Collect the initial public API from each module's symbol table.
    initial: Set[str] = set()
    for mod in py_modules:
        if mod.ast is None:
            continue
        _collect_public_names(mod.ast, excludes, initial)

    module_names = [mod.module for mod in py_modules]

    def _in_package(name: str) -> bool:
        return any(name.startswith(m) for m in module_names)

    # BFS expansion — follow type references to discover leaked internals.
    public_api: Set[str] = set()
    to_expand: List[str] = list(initial)
    while to_expand:
        item = to_expand.pop()
        if item in public_api:
            continue
        public_api.add(item)

        node = lookup_fully_qualified(item, files)
        if node is None:
            continue

        if isinstance(node.node, (FuncDef, Decorator, OverloadedFuncDef)):
            if node.type and isinstance(node.type, CallableType):
                for typ_str in map(str, _get_types(node.type.ret_type)):
                    if _in_package(typ_str):
                        to_expand.append(typ_str)
                for argtype in node.type.arg_types:
                    for typ_str in map(str, _get_types(argtype)):
                        if _in_package(typ_str):
                            to_expand.append(typ_str)

        elif isinstance(node.node, TypeInfo):
            cls_fullname = node.fullname
            for name, _attr in node.node.names.items():
                if _is_private_name(name):
                    continue
                to_expand.append(f"{cls_fullname}.{name}")
            for n in node.node.mro:
                if n.fullname and _in_package(n.fullname):
                    to_expand.append(n.fullname)

        elif isinstance(node.node, Var):
            if node.type is None:
                continue
            for typ_str in map(str, _get_types(node.type)):
                if _in_package(typ_str):
                    to_expand.append(typ_str)

    return public_api


# ---------------------------------------------------------------------------
# Phase 3 – generate stubs, filtering to the public API
# ---------------------------------------------------------------------------

def _make_public_api_generator(
    public_api: Set[str],
    files: Dict[str, MypyFile],
    _all_: Optional[list] = None,
    include_private: bool = False,
    analyzed: bool = True,
    export_less: bool = True,
) -> ASTStubGenerator:
    """Create an ``ASTStubGenerator`` that filters output to *public_api*.

    Prefers subclassing when mypy is installed from source (pure Python).
    Falls back to monkey-patching when mypy is mypyc-compiled.
    """
    try:
        gen = _PublicAPIStubGenerator(
            public_api, files, _all_, include_private, analyzed, export_less,
        )
    except TypeError:
        # mypyc-compiled mypy — cannot subclass; monkey-patch instead.
        gen = ASTStubGenerator(_all_, include_private, analyzed, export_less)
        _patch_generator(gen, public_api)
    return gen


def _patch_generator(gen: ASTStubGenerator, public_api: Set[str]) -> None:
    """Monkey-patch *gen* to filter output to *public_api*."""
    orig_visit_mypy_file = gen.visit_mypy_file
    orig_visit_func_def = gen.visit_func_def
    orig_visit_class_def = gen.visit_class_def

    def visit_mypy_file(o: MypyFile) -> None:
        if not any(name.startswith(o.fullname) for name in public_api):
            return
        orig_visit_mypy_file(o)

    def visit_func_def(o: FuncDef) -> None:
        if o.fullname not in public_api:
            gen.clear_decorators()
            return
        orig_visit_func_def(o)

    def visit_class_def(o: ClassDef) -> None:
        if o.fullname not in public_api:
            return
        orig_visit_class_def(o)

    gen.visit_mypy_file = visit_mypy_file  # type: ignore[assignment]
    gen.visit_func_def = visit_func_def  # type: ignore[assignment]
    gen.visit_class_def = visit_class_def  # type: ignore[assignment]


class _PublicAPIStubGenerator(ASTStubGenerator):
    """``ASTStubGenerator`` subclass that skips symbols outside the public API.

    Only works when mypy is installed from source (pure Python, not mypyc).
    """

    def __init__(
        self,
        public_api: Set[str],
        files: Dict[str, MypyFile],
        _all_: Optional[list] = None,
        include_private: bool = False,
        analyzed: bool = False,
        export_less: bool = False,
    ) -> None:
        super().__init__(_all_, include_private, analyzed, export_less)
        self._public_api = public_api
        self._files = files

    def visit_mypy_file(self, o: MypyFile) -> None:
        if not any(name.startswith(o.fullname) for name in self._public_api):
            return
        super().visit_mypy_file(o)

    def visit_func_def(self, o: FuncDef) -> None:
        if o.fullname not in self._public_api:
            self.clear_decorators()
            return
        super().visit_func_def(o)

    def visit_class_def(self, o: ClassDef) -> None:
        if o.fullname not in self._public_api:
            return
        super().visit_class_def(o)


# ---------------------------------------------------------------------------
# Stub generation for a single module using the public-API generator
# ---------------------------------------------------------------------------

def _generate_public_stub(
    mod: object,
    target: str,
    public_api: Set[str],
    files: Dict[str, MypyFile],
    all_modules: List[str],
) -> None:
    """Generate a .pyi stub for *mod* containing only public API symbols."""
    gen = _make_public_api_generator(
        public_api=public_api,
        files=files,
        _all_=mod.runtime_all,  # type: ignore[attr-defined]
    )
    gen.module_name = mod.module  # type: ignore[attr-defined]
    gen.path = mod.path or ""  # type: ignore[attr-defined]
    gen.sig_generators = gen.get_sig_generators()
    gen.visit_mypy_file(mod.ast)  # type: ignore[attr-defined]
    output = gen.output()
    imports = "".join(gen.get_imports())
    text = imports + output
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w") as f:
        f.write(text)


# ---------------------------------------------------------------------------
# generate_stubs – main orchestration
# ---------------------------------------------------------------------------

def generate_stubs(options: StubgenOptions, public_api_excludes: List[str]) -> None:
    """Generate public-API stubs for the requested packages/modules."""
    mypy_opts = mypy_options(options)
    mypy_opts.export_types = True

    py_modules, c_modules, errors = collect_build_targets(options, mypy_opts)

    # Semantic analysis
    generate_asts_for_modules(py_modules, options.parse_only, mypy_opts, options.verbose)

    # Build the files dict from analysed ASTs.
    files: Dict[str, MypyFile] = {}
    for mod in py_modules:
        if mod.ast is not None:
            files[mod.module] = mod.ast

    # Compute the public API surface.
    public_api = find_public_api(py_modules, public_api_excludes, files)

    all_modules = [mod.module for mod in py_modules]

    for mod in py_modules:
        if mod.ast is None:
            continue
        # Skip modules that have no public API items at all.
        if not any(name.startswith(mod.module) for name in public_api):
            continue

        target = os.path.join(
            options.output_dir,
            mod.module.replace(".", "/"),
        )
        if os.path.basename(mod.path or "") == "__init__.py":
            target = os.path.join(target, "__init__.pyi")
        else:
            target += ".pyi"

        _generate_public_stub(mod, target, public_api, files, all_modules)

    num = len(py_modules) + len(c_modules)
    if not options.quiet:
        print(f"Processed {num} modules")
        for mod in py_modules:
            if mod.ast is not None:
                tgt = os.path.join(
                    options.output_dir,
                    mod.module.replace(".", "/"),
                )
                if os.path.basename(mod.path or "") == "__init__.py":
                    tgt = os.path.join(tgt, "__init__.pyi")
                else:
                    tgt += ".pyi"
                print(f"Generated {tgt}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_options(args: List[str]) -> tuple:
    """Parse CLI arguments, returning ``(StubgenOptions, public_api_excludes)``."""
    parser = argparse.ArgumentParser(
        prog="doxxie",
        description="Generate public-API stubs for a mypy-typed Python package.",
    )
    parser.add_argument(
        "-p", "--package",
        action="append",
        metavar="PACKAGE",
        dest="packages",
        default=[],
        help="generate stubs for package recursively; can be repeated",
    )
    parser.add_argument(
        "-m", "--module",
        action="append",
        metavar="MODULE",
        dest="modules",
        default=[],
        help="generate stub for module; can repeat for more modules",
    )
    parser.add_argument(
        "-o", "--output",
        metavar="PATH",
        dest="output_dir",
        default="out",
        help="change the output directory [default: %(default)s]",
    )
    parser.add_argument(
        "-e", "--public-api-exclude",
        action="append",
        dest="public_api_excludes",
        default=[],
        help="exclude modules/packages from the public API",
    )
    parser.add_argument(
        "--public-api-only",
        action="store_true",
        dest="public_api_only",
        help="only generate stubs for the public API (always on)",
    )
    parser.add_argument(
        "--include-private",
        action="store_true",
        help="include private names in stubs",
    )
    parser.add_argument(
        "--no-import",
        action="store_true",
        help="don't import the modules, just parse and analyze them",
    )
    parser.add_argument(
        "--ignore-errors",
        action="store_true",
        help="ignore errors when generating stubs",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="show more verbose messages",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="show fewer messages",
    )
    parser.add_argument(
        metavar="files",
        nargs="*",
        dest="files",
        help="generate stubs for given files or directories",
    )

    ns = parser.parse_args(args)

    if not os.path.exists(ns.output_dir):
        os.makedirs(ns.output_dir)

    from mypy.defaults import PYTHON3_VERSION
    pyversion = PYTHON3_VERSION

    stubgen_options = StubgenOptions(
        pyversion=pyversion,
        no_import=ns.no_import,
        inspect=False,
        doc_dir="",
        search_path=[".", os.getcwd()],
        interpreter=sys.executable,
        parse_only=False,
        ignore_errors=ns.ignore_errors,
        include_private=ns.include_private,
        output_dir=ns.output_dir,
        modules=ns.modules,
        packages=ns.packages,
        files=ns.files,
        verbose=ns.verbose,
        quiet=ns.quiet,
        export_less=True,
        include_docstrings=False,
    )
    return stubgen_options, ns.public_api_excludes


def main() -> None:
    if "" not in sys.path and "." not in sys.path:
        sys.path.insert(0, "")

    options, excludes = parse_options(sys.argv[1:])
    generate_stubs(options, excludes)


if __name__ == "__main__":
    main()
