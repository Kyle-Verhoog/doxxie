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
        == """
{'pkg.fn': {'arg_kinds': [0],
            'arg_names': ['a'],
            'type': {'arg_types': ['builtins.int'],
                     'ret_type': 'builtins.int'}}}\n""".lstrip()
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
        == """
{'pkg._InternalType': {'bases': ['builtins.object'],
                       'mro': ['pkg._InternalType', 'builtins.object']},
 'pkg.public_fn': {'arg_kinds': [],
                   'arg_names': [],
                   'type': {'arg_types': [], 'ret_type': 'pkg._InternalType'}}}\n""".lstrip()
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
        == """
{'pkg.Public': {'bases': ['pkg._InternalType1', 'pkg._InternalType2'],
                'mro': ['pkg.Public',
                        'pkg._InternalType1',
                        'pkg._InternalType0',
                        'pkg._InternalType2',
                        'builtins.object']},
 'pkg._InternalType0': {'bases': ['builtins.object'],
                        'mro': ['pkg._InternalType0', 'builtins.object']},
 'pkg._InternalType0.public_method': {'arg_kinds': [0],
                                      'arg_names': ['self'],
                                      'type': {}},
 'pkg._InternalType1': {'bases': ['pkg._InternalType0'],
                        'mro': ['pkg._InternalType1',
                                'pkg._InternalType0',
                                'builtins.object']},
 'pkg._InternalType2': {'bases': ['builtins.object'],
                        'mro': ['pkg._InternalType2', 'builtins.object']}}\n""".lstrip()
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
{'pkg.InitClass': {'bases': ['builtins.object'],
                   'mro': ['pkg.InitClass', 'builtins.object']},
 'pkg.InitClass.__init__': {'arg_kinds': [0, 0, 0],
                            'arg_names': ['self', 'a', 'b'],
                            'type': {'arg_types': ['pkg.InitClass',
                                                   'builtins.int',
                                                   'builtins.str'],
                                     'ret_type': {'.class': 'NoneType'}}},
 'pkg.a.A': {'bases': ['builtins.object'],
             'mro': ['pkg.a.A', 'builtins.object']},
 'pkg.a.A.__init__': {'arg_kinds': [0, 0, 0],
                      'arg_names': ['self', 'a', 'b'],
                      'type': {'arg_types': ['pkg.a.A',
                                             'builtins.int',
                                             'builtins.str'],
                               'ret_type': {'.class': 'NoneType'}}},
 'pkg.a.A.a': {'type': 'builtins.int'},
 'pkg.a.A.d': {'type': 'pkg.internal.ExposedClass2'},
 'pkg.a.A.e': {'type': {'.class': 'Instance',
                        'args': ['builtins.str', 'pkg.internal.ExposedClass11'],
                        'type_ref': 'builtins.dict'}},
 'pkg.a.A.public_method': {'arg_kinds': [0], 'arg_names': ['self'], 'type': {}},
 'pkg.a.A.public_method_internal_argument': {'arg_kinds': [0, 0],
                                             'arg_names': ['self', 'arg'],
                                             'type': {'arg_types': ['pkg.a.A',
                                                                    'pkg.internal.ExposedClass5'],
                                                      'ret_type': {'.class': 'NoneType'}}},
 'pkg.a.A.public_method_internal_return': {'arg_kinds': [0],
                                           'arg_names': ['self'],
                                           'type': {'arg_types': ['pkg.a.A'],
                                                    'ret_type': 'pkg.internal.ExposedClass3'}},
 'pkg.a.A.public_method_internal_return_union': {'arg_kinds': [0],
                                                 'arg_names': ['self'],
                                                 'type': {'arg_types': ['pkg.a.A'],
                                                          'ret_type': {'.class': 'UnionType',
                                                                       'items': ['pkg.internal.ExposedClass6',
                                                                                 'pkg.internal.ExposedClass7']}}},
 'pkg.a.hello': {'arg_kinds': [],
                 'arg_names': [],
                 'type': {'arg_types': [], 'ret_type': 'builtins.int'}},
 'pkg.a.pub_var1': {'type': 'pkg.internal.ExposedClass12'},
 'pkg.a.pub_var2': {'type': 'pkg.internal.ExposedClass12'},
 'pkg.a.public_function_internal_return': {'arg_kinds': [],
                                           'arg_names': [],
                                           'type': {'arg_types': [],
                                                    'ret_type': 'pkg.internal.ExposedClass9'}},
 'pkg.a.var': {'type': 'pkg.internal.ExposedClass8'},
 'pkg.func': {'arg_kinds': [0],
              'arg_names': ['a'],
              'type': {'arg_types': ['builtins.int'],
                       'ret_type': 'builtins.int'}},
 'pkg.internal.ExposedClass10': {'bases': ['builtins.object'],
                                 'mro': ['pkg.internal.ExposedClass10',
                                         'builtins.object']},
 'pkg.internal.ExposedClass10.public_method': {'arg_kinds': [0],
                                               'arg_names': ['self'],
                                               'type': {}},
 'pkg.internal.ExposedClass11': {'bases': ['builtins.object'],
                                 'mro': ['pkg.internal.ExposedClass11',
                                         'builtins.object']},
 'pkg.internal.ExposedClass11.public_method': {'arg_kinds': [0],
                                               'arg_names': ['self'],
                                               'type': {}},
 'pkg.internal.ExposedClass12': {'bases': ['builtins.object'],
                                 'mro': ['pkg.internal.ExposedClass12',
                                         'builtins.object']},
 'pkg.internal.ExposedClass2': {'bases': ['builtins.object'],
                                'mro': ['pkg.internal.ExposedClass2',
                                        'builtins.object']},
 'pkg.internal.ExposedClass2.__init__': {'arg_kinds': [0],
                                         'arg_names': ['self'],
                                         'type': {}},
 'pkg.internal.ExposedClass2.public_method': {'arg_kinds': [0],
                                              'arg_names': ['self'],
                                              'type': {}},
 'pkg.internal.ExposedClass3': {'bases': ['builtins.object'],
                                'mro': ['pkg.internal.ExposedClass3',
                                        'builtins.object']},
 'pkg.internal.ExposedClass3.__init__': {'arg_kinds': [0],
                                         'arg_names': ['self'],
                                         'type': {}},
 'pkg.internal.ExposedClass3.public_method': {'arg_kinds': [0],
                                              'arg_names': ['self'],
                                              'type': {'arg_types': ['pkg.internal.ExposedClass3'],
                                                       'ret_type': 'pkg.internal.ExposedClass4'}},
 'pkg.internal.ExposedClass4': {'bases': ['builtins.object'],
                                'mro': ['pkg.internal.ExposedClass4',
                                        'builtins.object']},
 'pkg.internal.ExposedClass4.__init__': {'arg_kinds': [0],
                                         'arg_names': ['self'],
                                         'type': {}},
 'pkg.internal.ExposedClass4.public_method': {'arg_kinds': [0],
                                              'arg_names': ['self'],
                                              'type': {}},
 'pkg.internal.ExposedClass5': {'bases': ['builtins.object'],
                                'mro': ['pkg.internal.ExposedClass5',
                                        'builtins.object']},
 'pkg.internal.ExposedClass5.__init__': {'arg_kinds': [0],
                                         'arg_names': ['self'],
                                         'type': {}},
 'pkg.internal.ExposedClass5.public_method': {'arg_kinds': [0],
                                              'arg_names': ['self'],
                                              'type': {}},
 'pkg.internal.ExposedClass6': {'bases': ['builtins.object'],
                                'mro': ['pkg.internal.ExposedClass6',
                                        'builtins.object']},
 'pkg.internal.ExposedClass6.public_method': {'arg_kinds': [0],
                                              'arg_names': ['self'],
                                              'type': {}},
 'pkg.internal.ExposedClass7': {'bases': ['builtins.object'],
                                'mro': ['pkg.internal.ExposedClass7',
                                        'builtins.object']},
 'pkg.internal.ExposedClass7.public_method': {'arg_kinds': [0],
                                              'arg_names': ['self'],
                                              'type': {}},
 'pkg.internal.ExposedClass8': {'bases': ['builtins.object'],
                                'mro': ['pkg.internal.ExposedClass8',
                                        'builtins.object']},
 'pkg.internal.ExposedClass8.public_method': {'arg_kinds': [0],
                                              'arg_names': ['self'],
                                              'type': {}},
 'pkg.internal.ExposedClass9': {'bases': ['builtins.object'],
                                'mro': ['pkg.internal.ExposedClass9',
                                        'builtins.object']},
 'pkg.internal.ExposedClass9.public_method': {'arg_kinds': [0],
                                              'arg_names': ['self'],
                                              'type': {}}}\n""".lstrip()
    )
