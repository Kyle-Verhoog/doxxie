.. toctree::
   :maxdepth: 2
   :hidden:

   self
   release_notes
   contributing


doxxie
======


System Requirements
-------------------

``doxxie`` supports Python 3.6+ and can be run with CPython or PyPy.


Installation
------------

doxxie can be installed from PyPI with::

        pip install doxxie


.. note::
   riot does not yet have a stable API so it is recommended to pin the riot
   version to avoid having to deal with breaking changes.


Usage
-----

Add ``doxxie`` to the plugins section of your mypy config::

        [mypy]
        plugins = doxxie

Then run ``mypy`` with an environment variable specifying which modules to include::

        $ DOXXIE_INCLUDES=module mypy

A file ``.public_api`` will be output with the public API of ``module``.


Configuration
-------------

All configuration is done via environment variables.

- ``DOXXIE_INCLUDES``: comma-separated list of modules to include in the public API
  - example: "mod1,mod2"
  - default: ""
- ``DOXXIE_EXCLUDES``: comma-separated list of modules to exclude from the public API
  - example: "mod1.internal,mod1.vendor"
  - default: ""
- ``DOXXIE_OUTFILE``: file to output the results
  - example: "my_public_api"
  - default: ``.public_api``
- ``DOXXIE_DEBUG``: enable debug logging
  - default
