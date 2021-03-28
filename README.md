# doxxie

[![Read the Docs](https://img.shields.io/readthedocs/doxxie?style=for-the-badge)](https://doxxie.readthedocs.io/)
[![Pyversions](https://img.shields.io/pypi/pyversions/doxxie.svg?style=for-the-badge)](https://pypi.org/project/doxxie/)
[![PypiVersions](https://img.shields.io/pypi/v/doxxie.svg?style=for-the-badge)](https://pypi.org/project/doxxie/)
[![Tests](https://img.shields.io/github/workflow/status/Kyle-Verhoog/doxxie/CI?label=Tests&style=for-the-badge)](https://github.com/Kyle-Verhoog/doxxie/actions?query=workflow%3ACI)
[![Codecov](https://img.shields.io/codecov/c/github/Kyle-Verhoog/doxxie?style=for-the-badge)](https://codecov.io/gh/Kyle-Verhoog/doxxie)


`doxxie` is a [`mypy`](http://mypy-lang.org/) plugin that outputs the true
public API of a mypy-typed Python library. `doxxie`'s output can be checked
into source control to ensure changes to the public API are intentional and
documented.


## how?

`doxxie` starts with the public API of a library and then recursively adds the
types used in attributes and functions to the API. This can expose internal
data structures which are accidentally leaked through the public API.


## installation

Install from PyPI:

```sh
pip install doxxie
```

or install from source:

```sh
pip install git+https://github.com/Kyle-Verhoog/doxxie.git
```


## usage

Add `doxxie` to the plugins section of your mypy config:

```ini
[mypy]
files = module/
plugins = doxxie
```

Then run `mypy` with an environment variable specifying which modules to
include:

```bash
$ DOXXIE_INCLUDES=module mypy --no-incremental
```

A file `.public_api` will be output with the public API of `module`.

**Note:** The `--no-incremental` flag is necessary as `doxxie` cannot get
access to cached typing information.


## configuration

All configuration is done via environment variables.

- `DOXXIE_INCLUDES`: comma-separated list of modules to include in the public API
  - example: "mod1,mod2"
  - default: ""
- `DOXXIE_EXCLUDES`: comma-separated list of modules to exclude from the public API
  - example: "mod1.internal,mod1.vendor"
  - default: ""
- `DOXXIE_OUTFILE`: file to output the results
  - example: "my_public_api"
  - default: `.public_api`
- `DOXXIE_DEBUG`: enable debug logging
  - default
