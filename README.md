# doxxie

[![Read the Docs](https://img.shields.io/readthedocs/doxxie?style=for-the-badge)](https://doxxie.readthedocs.io/)
[![Pyversions](https://img.shields.io/pypi/pyversions/doxxie.svg?style=for-the-badge)](https://pypi.org/project/doxxie/)
[![PypiVersions](https://img.shields.io/pypi/v/doxxie.svg?style=for-the-badge)](https://pypi.org/project/doxxie/)
[![Tests](https://img.shields.io/github/workflow/status/Kyle-Verhoog/doxxie/CI?label=Tests&style=for-the-badge)](https://github.com/Kyle-Verhoog/doxxie/actions?query=workflow%3ACI)

<img align="right" src="https://www.dropbox.com/s/5tjxiwtg927c5qf/Photo%202021-04-04%2C%2012%2053%2022.jpg?raw=1" alt="doxxie logo" width="300px"/>

`doxxie` is a [mypy](http://mypy-lang.org/) plugin that outputs the true public
API of a mypy-typed Python library. `doxxie`'s output can be checked into
source control and [verified with a CI job](#ci-job) to ensure changes to the public API
are intentional and documented.


`doxxie` burrows into the public API of a library and recursively digs out any
types exposed by public attributes and functions until the true public API is
reached.


## installation

Install from PyPI:

```sh
$ pip install doxxie
```


## usage

Add `doxxie` to the plugins section of your [mypy config
file](https://mypy.readthedocs.io/en/stable/config_file.html):

```ini
[mypy]
files = mylib/
plugins = doxxie
```

Then run mypy with an environment variable specifying which modules to
include:

```bash
$ DOXXIE_INCLUDES=mylib mypy --no-incremental
```

A file `.public_api` will be output with the public API of `mylib`.

**Note:** The `--no-incremental` flag is necessary as `doxxie` cannot get
access to mypy's cached typing information.

## output

`doxxie` outputs a `.public_api` file which contains a listing of all the
public variables of the modules specified.

### example

*See docs/example for the code shown below*

Consider the following Python library `lib`:

```
lib/
├── __init__.py
├── api/
│   └── __init__.py
└── _internal/
    └── __init__.py
```

```python
# api/__init__.py
from lib._internal import LeakedPrivate, Private

class Public:
    def __init__(self):
        self.public_attr: int = 5
        self.public_leak: LeakedPrivate = LeakedPrivate()
        self._private: Private = Private()

    def public_method(self) -> None:
        pass

    def _private_method(self) -> str:
        return "hi"
```


```python
# _internal/__init__.py
class LeakedPrivate:
    def public_method(self) -> None:
        pass

class Private:
    pass
```

Running `DOXXIE_INCLUDES=pkg.api DOXXIE_EXCLUDES=pkg._internal mypy` will
output the following to `.public_api`:

```python
{'lib.Private': {'bases': ['builtins.object'],
                 'mro': ['lib.Private', 'builtins.object']},
 'lib.Private.public_method': {'arg_kinds': [0],
                               'arg_names': ['self'],
                               'type': {'arg_types': ['lib.Private'],
                                        'ret_type': {'.class': 'NoneType'}}},
 'lib._internal.LeakedPrivate': {'bases': ['builtins.object'],
                                 'mro': ['lib._internal.LeakedPrivate',
                                         'builtins.object']},
 'lib._internal.LeakedPrivate.public_method': {'arg_kinds': [0],
                                               'arg_names': ['self'],
                                               'type': {'arg_types': ['lib._internal.LeakedPrivate'],
                                                        'ret_type': {'.class': 'NoneType'}}},
 'lib.api.Public': {'bases': ['builtins.object'],
                    'mro': ['lib.api.Public', 'builtins.object']},
 'lib.api.Public.__init__': {'arg_kinds': [0],
                             'arg_names': ['self'],
                             'type': {}},
 'lib.api.Public.public_attr': {'type': 'builtins.int'},
 'lib.api.Public.public_leak': {'type': 'lib._internal.LeakedPrivate'},
 'lib.api.Public.public_method': {'arg_kinds': [0],
                                  'arg_names': ['self'],
                                  'type': {'arg_types': ['lib.api.Public'],
                                           'ret_type': {'.class': 'NoneType'}}}}
```


## configuration

All configuration is done via environment variables.

- `DOXXIE_INCLUDES`: comma-separated list of modules to include in the public
  API. Only items found under the modules provided will be included in the
  public API output.
  - example: `"mod1,mod2"`
  - default: `""` (nothing will be included by default)
- `DOXXIE_EXCLUDES`: comma-separated list of modules to exclude from the public
  API. These modules will be ignored initially but items from these modules may
  be exposed by the public API and included in the output.
  - example: `"mod1.internal,mod1.vendor"`
  - default: `""`
- `DOXXIE_OUTFILE`: file to output the results
  - example: `"my_public_api"`
  - default: `".public_api"`
- `DOXXIE_DERIVE_OUTFILE`: file to output derivation results for each item
  included in the public API. This output can be used to show what chain of
  attributes led to an item being exposed.
  - example: `"public_api_derivation"`
  - default: disabled
- `DOXXIE_DEBUG`: enable debug logging
  - example: `"1"`
  - default: disabled


## ci job

`doxxie` can be used to help avoid accidental changes to the public API of a
library. To do this, check the `.public_api` file generated by `doxxie` into
source control and enforce that changes to it are always committed by using a
CI job.

### github workflow

```yaml
name: CI
on:
  pull_request:
  push:
    branches:
      - main
jobs:
  check_api:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - name: install dependencies
        run: pip install mypy doxxie
      - run: DOXXIE_INCLUDES=doxxie DOXXIE_OUTFILE=.public_api_delta mypy --no-incremental
      - run: diff .public_api .public_api_delta
```
