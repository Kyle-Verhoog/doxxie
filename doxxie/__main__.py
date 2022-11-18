import ast
import logging
import os
import pkgutil
import setuptools
import sys
from typing import Sequence

import mypy
from mypy.dmypy_server import Server
from mypy.inspections import InspectionEngine


log = logging.getLogger(__name__)


def get_type(self, position):
    engine = InspectionEngine(
        self.fine_grained_manager,
        force_reload=True,
    )
    # result = engine.get_type("ddtrace/__init__.py:24:1:24:6")
    print(position)
    result = engine.get_type(position)
    return result["out"]


def find_packages(root_mod: str) -> Sequence[str]:
    # pkgs = ["%s.%s" % (root_mod, submod) for submod in setuptools.find_packages(root_mod)]
    # return pkgs
    mods = []
    for dirname, subdirs, fnames in os.walk(root_mod):
        for fname in fnames:
            if fname.endswith(".py"):
                mod = os.path.splitext(os.path.join(dirname, fname))[0]
                mod = mod.replace(os.path.sep, ".")
                mods.append(mod)
        # mods = set(pkgutil.iter_modules([dir, subdirs]))
        # mods += [m for m in pkgutil.iter_modules([dirname] + subdirs)]
    return mods


def filter_public_modules(modnames: Sequence[str]) -> Sequence[str]:
    public_mods = []
    for modname in modnames:
        if any(part.startswith("_") for part in modname.split(".")):
            continue
        public_mods.append(modname)
    return public_mods


def get_module_public_api(node: ast.AST) -> Sequence[ast.AST]:
    if isinstance(node, str):
        return [node] if is_public_name(node) else []
    elif isinstance(node, ast.Name):
        return [node] if is_public_name(node.id) else []
    elif isinstance(node, ast.Assign):
        nodes = []
        for t in node.targets:
            nodes += get_module_public_api(t)
        return nodes
    elif isinstance(node, ast.FunctionDef):
        if is_public_name(node.name):
            return [node]
    elif isinstance(node, ast.ClassDef):
        nodes = [node] if is_public_name(node.name) else []
        for n in node.body:
            nodes += get_module_public_api(n)
        return nodes
    elif isinstance(node, ast.If):
        pass
    elif isinstance(node, ast.Module):
        pass
    else:
        # raise ValueError("%r %r" % (node, type(node)))
        pass
    nodes = []
    for child in ast.iter_child_nodes(node):
        nodes += get_module_public_api(child)
    return nodes


def is_public_name(name: str) -> bool:
    return not name.startswith("_")


def is_public(node: ast.AST) -> bool:
    if isinstance(node, str):
        return is_public_name(node)
    if isinstance(node, ast.Name):
        return is_public(node.id)
    if isinstance(node, ast.ClassDef):
        return is_public(node.name)
    if isinstance(node, ast.FunctionDef):
        return is_public(node.name)
    raise ValueError("%r %r not supported" % (node, type(node)))


if __name__ == "__main__":
    log_level = "INFO"
    logging.basicConfig(level=log_level)
    root_mod = sys.argv[1]
    internal_mods = ["ddtrace.vendor", "ddtrace.internal", "ddtrace.contrib"]
    ignore_names = ["TYPE_CHECKING", "log", "logger"]
    sources, options = mypy.main.process_options(
        ["-i", root_mod], require_targets=False, server_options=True
    )
    server = Server(options, "")
    server.cmd_check(["ddtrace/tracer.py"], False, False, 92)

    all_mods = find_packages(root_mod)
    log.info("found %r modules for %r", len(all_mods), root_mod)
    filtered_mods = []
    for mod in all_mods:
        if any(mod.startswith(int_mod) for int_mod in internal_mods):
            for int_mod in internal_mods:
                if mod.startswith(int_mod):
                    log.debug(
                        "module %r skipped due to declared internal module %r",
                        mod,
                        int_mod,
                    )
            continue
        filtered_mods.append(mod)
    log.info("found %r declared internal modules", len(all_mods) - len(filtered_mods))
    log.debug("mods to check: %r", [m for m in filtered_mods])

    public_mods = filter_public_modules(filtered_mods)
    log.info("%r modules public modules found", len(all_mods) - len(filtered_mods))
    log.debug("public mods: %r", public_mods)

    public_api = []
    for pubmod in public_mods:
        mod_file_path = pubmod.replace(".", os.path.sep) + ".py"
        with open(mod_file_path) as f:
            parsed_mod = ast.parse(f.read())
            nodes = [(mod_file_path, n) for n in get_module_public_api(parsed_mod)]
            public_api += nodes

    print(public_api)
    for fn, node in public_api:
        if isinstance(node, ast.Name):
            print(
                node.id,
                get_type(
                    server,
                    "%s:%s:%s:%s:%s"
                    % (
                        fn,
                        node.lineno,
                        node.col_offset + 1,
                        node.lineno,
                        node.end_col_offset,
                    ),
                ),
            )
