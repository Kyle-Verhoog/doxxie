"""Tests that validate doxxie's public API extraction by creating real Python
packages in a tmpdir, running doxxie against them, and checking the generated
stubs.

Each test creates a minimal package, runs doxxie with --public-api-only, and
asserts on what appears (and what doesn't) in the generated .pyi files.  The
assertions are written so a human can read the test and immediately understand
what the expected public API surface is.
"""
import os
import subprocess
import textwrap

import pytest


def run_doxxie(pkg_dir: str, pkg_name: str, output_dir: str) -> None:
    """Run doxxie --public-api-only on *pkg_name* from *pkg_dir*."""
    subprocess.check_call(
        ["doxxie", "--public-api-only", "-p", pkg_name, "-o", output_dir],
        cwd=pkg_dir,
    )


def read_stub(output_dir: str, rel_path: str) -> str:
    """Return the contents of a generated .pyi file."""
    path = os.path.join(output_dir, rel_path)
    assert os.path.exists(path), f"Expected stub not generated: {path}"
    with open(path) as f:
        return f.read()


def write_file(base: str, rel_path: str, content: str) -> None:
    """Write *content* to *base*/*rel_path*, creating directories as needed."""
    full = os.path.join(base, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(textwrap.dedent(content))


# ---------------------------------------------------------------------------
# 1. Public functions are included, private functions are excluded
# ---------------------------------------------------------------------------
class TestPublicPrivateFunctions:
    def test_public_function_appears(self, tmp_path):
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", """\
            def public_fn(x: int) -> str:
                return str(x)

            def _private_fn(x: int) -> str:
                return str(x)
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)
        stub = read_stub(out, "mypkg/__init__.pyi")

        assert "def public_fn(" in stub
        assert "_private_fn" not in stub

    def test_function_with_multiple_args(self, tmp_path):
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", """\
            def add(a: int, b: int) -> int:
                return a + b
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)
        stub = read_stub(out, "mypkg/__init__.pyi")

        assert "def add(a: int, b: int) -> int" in stub

    def test_function_with_default_args(self, tmp_path):
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", """\
            def greet(name: str, greeting: str = "hello") -> str:
                return f"{greeting} {name}"
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)
        stub = read_stub(out, "mypkg/__init__.pyi")

        assert "def greet(" in stub
        assert "name: str" in stub


# ---------------------------------------------------------------------------
# 2. Public classes are included, private classes are excluded
# ---------------------------------------------------------------------------
class TestPublicPrivateClasses:
    def test_public_class_appears(self, tmp_path):
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", """\
            class PublicClass:
                def method(self) -> None:
                    pass

            class _PrivateClass:
                def method(self) -> None:
                    pass
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)
        stub = read_stub(out, "mypkg/__init__.pyi")

        assert "class PublicClass:" in stub
        assert "_PrivateClass" not in stub

    def test_class_init_signature(self, tmp_path):
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", """\
            class Foo:
                def __init__(self, x: int, y: str) -> None:
                    self.x = x
                    self.y = y
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)
        stub = read_stub(out, "mypkg/__init__.pyi")

        assert "class Foo:" in stub
        assert "def __init__(self, x: int, y: str) -> None" in stub

    def test_class_public_methods_only(self, tmp_path):
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", """\
            class MyClass:
                def public_method(self) -> int:
                    return 1

                def _private_method(self) -> int:
                    return 2

                def another_public(self, x: str) -> str:
                    return x
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)
        stub = read_stub(out, "mypkg/__init__.pyi")

        assert "def public_method(self)" in stub
        assert "def another_public(self" in stub
        assert "_private_method" not in stub


# ---------------------------------------------------------------------------
# 3. Module-level variables
# ---------------------------------------------------------------------------
class TestPublicPrivateVariables:
    def test_public_variable_appears(self, tmp_path):
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", """\
            public_var: int = 42
            _private_var: int = 99
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)
        stub = read_stub(out, "mypkg/__init__.pyi")

        assert "public_var" in stub
        assert "_private_var" not in stub

    def test_multiple_assignment_variables(self, tmp_path):
        """x = y = SomeType() should produce stubs for both x and y."""
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", """\
            class T:
                pass

            a = b = T()
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)
        stub = read_stub(out, "mypkg/__init__.pyi")

        assert "a" in stub
        assert "b" in stub


# ---------------------------------------------------------------------------
# 4. Private modules (underscore-prefixed) are excluded unless exposed
# ---------------------------------------------------------------------------
class TestPrivateModules:
    def test_private_module_not_in_output(self, tmp_path):
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", """\
            def public_fn() -> int:
                return 1
        """)
        write_file(pkg, "mypkg/_internal.py", """\
            def internal_fn() -> int:
                return 2
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)

        assert not os.path.exists(os.path.join(out, "mypkg/_internal.pyi"))
        stub = read_stub(out, "mypkg/__init__.pyi")
        assert "public_fn" in stub

    def test_private_subpackage_not_in_output(self, tmp_path):
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", """\
            x: int = 1
        """)
        write_file(pkg, "mypkg/_secret/__init__.py", """\
            class Hidden:
                pass
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)

        assert not os.path.exists(os.path.join(out, "mypkg/_secret"))


# ---------------------------------------------------------------------------
# 5. Internal types exposed via public API are included
# ---------------------------------------------------------------------------
class TestExposedInternalTypes:
    def test_return_type_from_internal_module(self, tmp_path):
        """A public function returning an internal type should cause that
        type to appear in the stubs for the internal module."""
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", """\
            from mypkg._internal import Widget

            def get_widget() -> Widget:
                return Widget()
        """)
        write_file(pkg, "mypkg/_internal.py", """\
            class Widget:
                def render(self) -> str:
                    return "<widget>"
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)

        # Widget is exposed because get_widget() returns it
        init_stub = read_stub(out, "mypkg/__init__.pyi")
        assert "get_widget" in init_stub

        internal_stub = read_stub(out, "mypkg/_internal.pyi")
        assert "class Widget:" in internal_stub
        assert "def render(self)" in internal_stub

    def test_argument_type_from_internal_module(self, tmp_path):
        """A public function accepting an internal type should cause that
        type to appear in the stubs."""
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", """\
            from mypkg._internal import Config

            def configure(c: Config) -> None:
                pass
        """)
        write_file(pkg, "mypkg/_internal.py", """\
            class Config:
                name: str = ""
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)

        internal_stub = read_stub(out, "mypkg/_internal.pyi")
        assert "class Config:" in internal_stub

    def test_class_attribute_type_from_internal_module(self, tmp_path):
        """A public class attribute typed with an internal type should cause
        that type to appear in the stubs."""
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", """\
            from mypkg._internal import Engine

            class Car:
                def __init__(self) -> None:
                    self.engine: Engine = Engine()
        """)
        write_file(pkg, "mypkg/_internal.py", """\
            class Engine:
                horsepower: int = 0
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)

        init_stub = read_stub(out, "mypkg/__init__.pyi")
        assert "class Car:" in init_stub

        internal_stub = read_stub(out, "mypkg/_internal.pyi")
        assert "class Engine:" in internal_stub

    def test_private_internal_class_not_exposed(self, tmp_path):
        """An internal class that starts with _ and is never referenced by
        the public API should not appear in stubs."""
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", """\
            from mypkg._internal import Widget

            def get_widget() -> Widget:
                return Widget()
        """)
        write_file(pkg, "mypkg/_internal.py", """\
            class Widget:
                pass

            class _Secret:
                pass
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)

        internal_stub = read_stub(out, "mypkg/_internal.pyi")
        assert "class Widget:" in internal_stub
        assert "_Secret" not in internal_stub


# ---------------------------------------------------------------------------
# 6. Nested packages
# ---------------------------------------------------------------------------
class TestNestedPackages:
    def test_subpackage_public_api(self, tmp_path):
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", """\
            version: str = "1.0"
        """)
        write_file(pkg, "mypkg/sub/__init__.py", """\
            def sub_fn(x: int) -> int:
                return x

            def _sub_private() -> None:
                pass
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)

        sub_stub = read_stub(out, "mypkg/sub/__init__.pyi")
        assert "def sub_fn(" in sub_stub
        assert "_sub_private" not in sub_stub

    def test_deeply_nested_package(self, tmp_path):
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", "")
        write_file(pkg, "mypkg/a/__init__.py", "")
        write_file(pkg, "mypkg/a/b/__init__.py", """\
            class Deep:
                val: int = 0
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)

        stub = read_stub(out, "mypkg/a/b/__init__.pyi")
        assert "class Deep:" in stub

    def test_nested_private_subpackage_excluded(self, tmp_path):
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", "x: int = 1\n")
        write_file(pkg, "mypkg/public/__init__.py", "y: int = 2\n")
        write_file(pkg, "mypkg/public/_hidden/__init__.py", """\
            class Nope:
                pass
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)

        assert not os.path.exists(os.path.join(out, "mypkg/public/_hidden"))


# ---------------------------------------------------------------------------
# 7. Properties
# ---------------------------------------------------------------------------
class TestProperties:
    def test_property_included(self, tmp_path):
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", """\
            class Foo:
                @property
                def name(self) -> str:
                    return "foo"
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)
        stub = read_stub(out, "mypkg/__init__.pyi")

        assert "@property" in stub
        assert "def name(self) -> str" in stub

    def test_private_property_excluded(self, tmp_path):
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", """\
            class Foo:
                @property
                def public_prop(self) -> int:
                    return 1

                @property
                def _private_prop(self) -> int:
                    return 2
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)
        stub = read_stub(out, "mypkg/__init__.pyi")

        assert "public_prop" in stub
        assert "_private_prop" not in stub


# ---------------------------------------------------------------------------
# 8. Union and generic types expose internal classes
# ---------------------------------------------------------------------------
class TestComplexTypes:
    def test_union_return_type_exposes_both(self, tmp_path):
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", """\
            from typing import Union
            from mypkg._internal import A, B

            def get() -> Union[A, B]:
                return A()
        """)
        write_file(pkg, "mypkg/_internal.py", """\
            class A:
                pass

            class B:
                pass

            class C:
                pass
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)

        internal_stub = read_stub(out, "mypkg/_internal.pyi")
        assert "class A:" in internal_stub
        assert "class B:" in internal_stub
        # C is never exposed
        assert "class C:" not in internal_stub

    def test_dict_value_type_exposes_internal(self, tmp_path):
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", """\
            from typing import Dict
            from mypkg._internal import Val

            class Store:
                def __init__(self) -> None:
                    self.data: Dict[str, Val] = {}
        """)
        write_file(pkg, "mypkg/_internal.py", """\
            class Val:
                v: int = 0
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)

        internal_stub = read_stub(out, "mypkg/_internal.pyi")
        assert "class Val:" in internal_stub


# ---------------------------------------------------------------------------
# 9. Callable type annotations
# ---------------------------------------------------------------------------
class TestCallableTypes:
    def test_callable_argument(self, tmp_path):
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", """\
            from typing import Callable

            def apply(fn: Callable[[int], str]) -> str:
                return fn(1)
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)
        stub = read_stub(out, "mypkg/__init__.pyi")

        assert "def apply(" in stub
        assert "Callable" in stub


# ---------------------------------------------------------------------------
# 10. Public module alongside private module
# ---------------------------------------------------------------------------
class TestModuleMix:
    def test_public_module_file(self, tmp_path):
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", "")
        write_file(pkg, "mypkg/api.py", """\
            def endpoint() -> str:
                return "/api"
        """)
        write_file(pkg, "mypkg/_impl.py", """\
            def helper() -> str:
                return "h"
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)

        api_stub = read_stub(out, "mypkg/api.pyi")
        assert "def endpoint()" in api_stub
        assert not os.path.exists(os.path.join(out, "mypkg/_impl.pyi"))


# ---------------------------------------------------------------------------
# 11. Class with only private members produces empty class stub
# ---------------------------------------------------------------------------
class TestEdgeCases:
    def test_empty_module(self, tmp_path):
        """An empty __init__.py should still produce a stub file."""
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", "")
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)

        assert os.path.exists(os.path.join(out, "mypkg/__init__.pyi"))

    def test_only_private_members_module(self, tmp_path):
        """A module with only private names should produce a stub with none
        of them."""
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", """\
            def _a() -> None:
                pass

            _b: int = 1

            class _C:
                pass
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)
        stub = read_stub(out, "mypkg/__init__.pyi")

        assert "_a" not in stub
        assert "_b" not in stub
        assert "_C" not in stub

    def test_dunder_methods_on_public_class(self, tmp_path):
        """__init__ and operator dunders on public classes should appear.
        Note: __repr__ / __str__ are omitted by stubgen since they don't
        affect the type-level API, but __add__ (which changes return types)
        is included."""
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", """\
            class Vector:
                def __init__(self, x: float, y: float) -> None:
                    self.x = x
                    self.y = y

                def __add__(self, other: "Vector") -> "Vector":
                    return Vector(self.x + other.x, self.y + other.y)
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)
        stub = read_stub(out, "mypkg/__init__.pyi")

        assert "class Vector:" in stub
        assert "__init__" in stub
        assert "__add__" in stub


# ---------------------------------------------------------------------------
# 12. Transitive exposure of internal types (chain)
# ---------------------------------------------------------------------------
class TestTransitiveExposure:
    def test_chain_of_internal_types(self, tmp_path):
        """If public function returns InternalA, and InternalA.method returns
        InternalB, then both InternalA and InternalB should be in the stubs."""
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", """\
            from mypkg._internal import InternalA

            def make() -> InternalA:
                return InternalA()
        """)
        write_file(pkg, "mypkg/_internal.py", """\
            class InternalA:
                def next(self) -> "InternalB":
                    return InternalB()

            class InternalB:
                val: int = 0
        """)
        out = os.path.join(pkg, "out")
        run_doxxie(pkg, "mypkg", out)

        internal_stub = read_stub(out, "mypkg/_internal.pyi")
        assert "class InternalA:" in internal_stub
        assert "class InternalB:" in internal_stub


# ---------------------------------------------------------------------------
# 13. --public-api-exclude flag
# ---------------------------------------------------------------------------
class TestExclude:
    def test_exclude_subpackage(self, tmp_path):
        """Excluded packages should not appear in output at all."""
        pkg = str(tmp_path)
        write_file(pkg, "mypkg/__init__.py", """\
            x: int = 1
        """)
        write_file(pkg, "mypkg/vendor/__init__.py", """\
            class Vendored:
                pass
        """)
        out = os.path.join(pkg, "out")
        subprocess.check_call(
            [
                "doxxie",
                "--public-api-only",
                "-p", "mypkg",
                "-e", "mypkg.vendor",
                "-o", out,
            ],
            cwd=pkg,
        )

        assert not os.path.exists(os.path.join(out, "mypkg/vendor"))
        init_stub = read_stub(out, "mypkg/__init__.pyi")
        assert "x" in init_stub
