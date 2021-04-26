# doxxie

[![Read the Docs](https://img.shields.io/readthedocs/doxxie?style=for-the-badge)](https://doxxie.readthedocs.io/)
[![Pyversions](https://img.shields.io/pypi/pyversions/doxxie.svg?style=for-the-badge)](https://pypi.org/project/doxxie/)
[![PypiVersions](https://img.shields.io/pypi/v/doxxie.svg?style=for-the-badge)](https://pypi.org/project/doxxie/)
[![Tests](https://img.shields.io/github/workflow/status/Kyle-Verhoog/doxxie/CI?label=Tests&style=for-the-badge)](https://github.com/Kyle-Verhoog/doxxie/actions?query=workflow%3ACI)

<img align="right" src="https://www.dropbox.com/s/5tjxiwtg927c5qf/Photo%202021-04-04%2C%2012%2053%2022.jpg?raw=1" alt="doxxie logo" width="300px"/>

`doxxie` extends the
[`stubgen`](https://mypy.readthedocs.io/en/stable/stubgen.html) module of
[mypy](http://mypy-lang.org/) to  outputs the true public API of a mypy-typed
Python library. `doxxie`'s output can be checked into source control and
[verified with a CI job](#ci-job) to ensure changes to the public API are
intentional and documented.


`doxxie` burrows into the public API of a library and recursively digs out any
types exposed by public attributes and functions until the true public API is
reached.


## installation

Install from PyPI:

```sh
$ pip install doxxie
```

Note that `doxxie` relies on mypy internal classes which sometimes come
compiled in the mypy PyPI package. Installing mypy from git may be required:

```sh
# Known compatible commit, others may work as well
$ pip install git+git://github.com/python/mypy.git@66c2ac516305f194a9bc37c1ebf7f22d62d6141c
```


## usage


```bash
$ doxxie --public-api-only mypkg --output public_api
```

This command will output the public api stubs of `mypkg` to the `public_api`
directory.


### excluding modules

Modules can be excluded with the `--public-api-exclude/-e` argument.


```bash
$ doxxie --public-api-only pkg -e pkg.internal --output public_api
```


## output

`doxxie` outputs [PEP-484](https://www.python.org/dev/peps/pep-0484/) stubs of
the given Python package(s).


### example

See
[`docs/example`](https://github.com/Kyle-Verhoog/doxxie/tree/main/docs/example)
for an example.


## ci job

`doxxie` can be used to help avoid accidental changes to the public API of a
library. To do this, check the generated stub files generated by `doxxie` into
source control and enforce that changes are always committed by using a CI job.


### github workflow

This workflow compares the generated API to the one stored in the repo. If
there are any differences then the public API might have been unintentionally
broken.

Note that with this approach it is necessary to exclude the `public_api`
directory from being formatted (unless a step is added after `doxxie` to
format).

```yaml
name: Public API check
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
      - name: Install dependencies
        run: pip install doxxie git+git://github.com/python/mypy.git@66c2ac516305f194a9bc37c1ebf7f22d62d6141c
      - name: Run doxxie
        run: doxxie --public-api-only <your pkg> --output public_api
      - name: Ensure no changes have been made
        run: git diff --exit-code
```
