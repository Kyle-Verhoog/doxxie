# example

`lib` defines a simple Python package with a public module `api` and a
internal module `_internal`.

To generate the public API stubs under the `public_api` directory:

```bash
$ doxxie --public-api-only --output public_api lib
```
