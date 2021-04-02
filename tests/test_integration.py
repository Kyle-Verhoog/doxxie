import os
import subprocess
import sys
from typing import Any
from typing import Dict
from typing import Optional

import pytest


TEST_DIR = os.path.dirname(__file__)


@pytest.fixture
def dox_tmp_path(tmp_path):
    """Create a tmp_path/pkg module and a mypy config file that installs
    doxxie.
    """
    d = tmp_path / "pkg"
    d.mkdir()
    f = tmp_path / "pkg" / "__init__.py"
    f.write_text("")
    f = tmp_path / "mypy.ini"
    f.write_text(
        """
[mypy]
files = ./
plugins = doxxie
    """
    )
    yield tmp_path


def run(
    cmd: str, path: str, env: Optional[Dict[str, str]] = None
) -> "subprocess.CompletedProcess[Any]":
    e = os.environ.copy()
    e.update(env or {})
    if sys.version_info < (3, 7, 0):
        return subprocess.run(
            cmd.split(" "),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            env=e,
            cwd=path,
        )
    else:
        return subprocess.run(
            cmd.split(" "), capture_output=True, env=e, cwd=path, text=True
        )


def test_mypy_failed_typecheck(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    f = d / "__init__.py"
    f.write_text(
        """
def fn(a):
    # type: (int) -> int
    return None
    """
    )
    f = d / "__init__.py"
    p = run("mypy pkg", tmp_path)
    assert p.returncode == 1
    assert "error: Incompatible return value type" in p.stdout


def test_mypy_successful_typecheck(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    f = d / "__init__.py"
    f.write_text(
        """
def fn(a):
    # type: (int) -> int
    return 2
    """
    )
    f = d / "__init__.py"
    p = run("mypy pkg", tmp_path)
    assert p.returncode == 0
    assert "no issues found in 1 source file" in p.stdout
    assert p.stderr == ""


def test_doxxie_with_success(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    f = d / "__init__.py"
    f.write_text(
        """
def fn(a):
    # type: (int) -> int
    return 2
    """
    )
    f = tmp_path / "mypy.ini"
    f.write_text(
        """
[mypy]
files = pkg/
plugins = doxxie
    """
    )
    p = run("mypy", tmp_path, dict(DOXXIE_INCLUDES="pkg"))
    assert p.returncode == 0
    assert "no issues found in 1 source file" in p.stdout
    assert p.stderr == ""

    outfile = tmp_path / ".public_api"
    assert (
        outfile.read_text()
        == "{'pkg.fn': 'Gdef/FuncDef (pkg.fn) : def (a: builtins.int) -> builtins.int'}\n"
    )


def test_public_fn_argument_expose(dox_tmp_path):
    f = dox_tmp_path / "pkg" / "__init__.py"
    f.write_text(
        """
class _InternalType:
    pass

def public_fn() -> _InternalType:
    return _InternalType()
    """
    )
    p = run("mypy", dox_tmp_path, dict(DOXXIE_INCLUDES="pkg"))
    assert p.returncode == 0
    outfile = dox_tmp_path / ".public_api"
    assert (
        outfile.read_text()
        == "{'pkg._InternalType': 'Gdef/TypeInfo (pkg._InternalType)', 'pkg.public_fn': 'Gdef/FuncDef (pkg.public_fn) : def () -> pkg._InternalType'}\n"
    )


def test_expose_through_mro(dox_tmp_path):
    f = dox_tmp_path / "pkg" / "__init__.py"
    f.write_text(
        """
class _InternalType0:
    def public_method(self):
        pass

class _InternalType1(_InternalType0):
    pass

class _InternalType2:
    pass

class Public(_InternalType1, _InternalType2):
    pass
    """
    )
    p = run("mypy", dox_tmp_path, dict(DOXXIE_INCLUDES="pkg"))
    assert p.returncode == 0
    outfile = dox_tmp_path / ".public_api"
    assert (
        outfile.read_text()
        == "{'pkg.Public': 'Gdef/TypeInfo (pkg.Public)', 'pkg._InternalType0': 'Gdef/TypeInfo (pkg._InternalType0)', 'pkg._InternalType0.public_method': 'Mdef/FuncDef (pkg._InternalType0.public_method)', 'pkg._InternalType1': 'Gdef/TypeInfo (pkg._InternalType1)', 'pkg._InternalType2': 'Gdef/TypeInfo (pkg._InternalType2)'}\n"
    )


def test_private_module(dox_tmp_path):
    d = dox_tmp_path / "pkg" / "_internal"
    d.mkdir()
    f = dox_tmp_path / "pkg" / "__init__.py"
    f.write_text("")
    f = dox_tmp_path / "pkg" / "_internal" / "__init__.py"
    f.write_text(
        """
def fn():
    pass
    """
    )

    p = run("mypy", dox_tmp_path, dict(DOXXIE_INCLUDES="pkg"))
    assert p.returncode == 0
    outfile = dox_tmp_path / ".public_api"
    assert outfile.read_text() == "{}\n"


def test_comprehensive():
    d = os.path.join(TEST_DIR, "comprehensive")
    p = run(
        "mypy --no-incremental",
        d,
        dict(DOXXIE_DEBUG="1", DOXXIE_INCLUDES="pkg", DOXXIE_EXCLUDES="pkg.internal"),
    )
    assert p.returncode == 0
    assert p.stdout == "Success: no issues found in 3 source files\n"
    with open(os.path.join(d, ".public_api"), "r") as f:
        output = f.read()

    assert (
        output
        == """
{'pkg.InitClass': 'Gdef/TypeInfo (pkg.InitClass)',
 'pkg.InitClass.__init__': 'Mdef/FuncDef (pkg.InitClass.__init__) : def (self: pkg.InitClass, a: builtins.int, b: builtins.str)',
 'pkg.a.A': 'Gdef/TypeInfo (pkg.a.A)',
 'pkg.a.A.__init__': 'Mdef/FuncDef (pkg.a.A.__init__) : def (self: pkg.a.A, a: builtins.int, b: builtins.str)',
 'pkg.a.A.a': 'Mdef/Var (pkg.a.A.a) : builtins.int',
 'pkg.a.A.d': 'Mdef/Var (pkg.a.A.d) : pkg.internal.ExposedClass2',
 'pkg.a.A.e': 'Mdef/Var (pkg.a.A.e) : builtins.dict[builtins.str, pkg.internal.ExposedClass11]',
 'pkg.a.A.public_method': 'Mdef/FuncDef (pkg.a.A.public_method)',
 'pkg.a.A.public_method_internal_argument': 'Mdef/FuncDef (pkg.a.A.public_method_internal_argument) : def (self: pkg.a.A, arg: pkg.internal.ExposedClass5)',
 'pkg.a.A.public_method_internal_return': 'Mdef/FuncDef (pkg.a.A.public_method_internal_return) : def (self: pkg.a.A) -> pkg.internal.ExposedClass3',
 'pkg.a.A.public_method_internal_return_union': 'Mdef/FuncDef (pkg.a.A.public_method_internal_return_union) : def (self: pkg.a.A) -> Union[pkg.internal.ExposedClass6, pkg.internal.ExposedClass7]',
 'pkg.a.A.public_propery_internal_return': 'Mdef/Decorator (pkg.a.A.public_propery_internal_return) : def (self: pkg.a.A) -> pkg.internal.ExposedClass10',
 'pkg.a.hello': 'Gdef/FuncDef (pkg.a.hello) : def () -> builtins.int',
 'pkg.a.pub_var1': 'Gdef/Var (pkg.a.pub_var1) : pkg.internal.ExposedClass12',
 'pkg.a.pub_var2': 'Gdef/Var (pkg.a.pub_var2) : pkg.internal.ExposedClass12',
 'pkg.a.public_function_internal_return': 'Gdef/FuncDef (pkg.a.public_function_internal_return) : def () -> pkg.internal.ExposedClass9',
 'pkg.a.var': 'Gdef/Var (pkg.a.var) : pkg.internal.ExposedClass8',
 'pkg.func': 'Gdef/FuncDef (pkg.func) : def (a: builtins.int) -> builtins.int',
 'pkg.internal.ExposedClass10': 'Gdef/TypeInfo (pkg.internal.ExposedClass10)',
 'pkg.internal.ExposedClass10.public_method': 'Mdef/FuncDef (pkg.internal.ExposedClass10.public_method)',
 'pkg.internal.ExposedClass11': 'Gdef/TypeInfo (pkg.internal.ExposedClass11)',
 'pkg.internal.ExposedClass11.public_method': 'Mdef/FuncDef (pkg.internal.ExposedClass11.public_method)',
 'pkg.internal.ExposedClass12': 'Gdef/TypeInfo (pkg.internal.ExposedClass12)',
 'pkg.internal.ExposedClass2': 'Gdef/TypeInfo (pkg.internal.ExposedClass2)',
 'pkg.internal.ExposedClass2.__init__': 'Mdef/FuncDef (pkg.internal.ExposedClass2.__init__)',
 'pkg.internal.ExposedClass2.public_method': 'Mdef/FuncDef (pkg.internal.ExposedClass2.public_method)',
 'pkg.internal.ExposedClass3': 'Gdef/TypeInfo (pkg.internal.ExposedClass3)',
 'pkg.internal.ExposedClass3.__init__': 'Mdef/FuncDef (pkg.internal.ExposedClass3.__init__)',
 'pkg.internal.ExposedClass3.public_method': 'Mdef/FuncDef (pkg.internal.ExposedClass3.public_method) : def (self: pkg.internal.ExposedClass3) -> pkg.internal.ExposedClass4',
 'pkg.internal.ExposedClass4': 'Gdef/TypeInfo (pkg.internal.ExposedClass4)',
 'pkg.internal.ExposedClass4.__init__': 'Mdef/FuncDef (pkg.internal.ExposedClass4.__init__)',
 'pkg.internal.ExposedClass4.public_method': 'Mdef/FuncDef (pkg.internal.ExposedClass4.public_method)',
 'pkg.internal.ExposedClass5': 'Gdef/TypeInfo (pkg.internal.ExposedClass5)',
 'pkg.internal.ExposedClass5.__init__': 'Mdef/FuncDef (pkg.internal.ExposedClass5.__init__)',
 'pkg.internal.ExposedClass5.public_method': 'Mdef/FuncDef (pkg.internal.ExposedClass5.public_method)',
 'pkg.internal.ExposedClass6': 'Gdef/TypeInfo (pkg.internal.ExposedClass6)',
 'pkg.internal.ExposedClass6.public_method': 'Mdef/FuncDef (pkg.internal.ExposedClass6.public_method)',
 'pkg.internal.ExposedClass7': 'Gdef/TypeInfo (pkg.internal.ExposedClass7)',
 'pkg.internal.ExposedClass7.public_method': 'Mdef/FuncDef (pkg.internal.ExposedClass7.public_method)',
 'pkg.internal.ExposedClass8': 'Gdef/TypeInfo (pkg.internal.ExposedClass8)',
 'pkg.internal.ExposedClass8.public_method': 'Mdef/FuncDef (pkg.internal.ExposedClass8.public_method)',
 'pkg.internal.ExposedClass9': 'Gdef/TypeInfo (pkg.internal.ExposedClass9)',
 'pkg.internal.ExposedClass9.public_method': 'Mdef/FuncDef (pkg.internal.ExposedClass9.public_method)'}\n""".lstrip()
    )
