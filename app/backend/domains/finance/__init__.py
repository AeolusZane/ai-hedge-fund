"""Finance domain pack.

This package only re-exports the executor type. Registration with the
core executor registry is a separate side-effect module (`pack.py`) so
that submodules like `agents/` or `tools/` can be imported (e.g. by
existing services) without triggering circular schema imports.
"""
