# Python and pytest Rules

## Evidence and declarations

Parse Python with the standard-library AST; never import target modules or run
pytest collection. Explicit top-level `import pytest` / `from pytest import ...`
(including aliases), or an ancestor pytest configuration section, establishes
framework context. Names alone do not establish pytest. Reassigned module aliases
are not trusted.

Recognize top-level `test*` functions (including async functions) and methods in
non-inheriting `Test*` classes without `__init__`. Retain class-qualified names.
Do not count nested helper functions, fixture factories, or parameter rows.
Inherited classes and custom constructors are not resolved. Configuration files
and declaration-free `conftest.py` are context, not suspected test sources.

Read `[pytest]` in `pytest.ini`, `.pytest.ini` and `tox.ini`, `[tool:pytest]` in
`setup.cfg`, and the literal `[tool.pytest.ini_options]` section in `pyproject.toml`.
INI content is parsed with interpolation disabled; TOML sections are recognized
lexically for Python 3.10 compatibility. Executable configuration is never loaded.
Collection patterns, ignore rules and conditional imports are not applied.

## Status and parameterization

Recognized `pytest.mark.parametrize` marks indicate framework parameterization.
Function/class decorators and module/class `pytestmark` lists are inspected.
Unconditional `mark.skip` is skipped. `skipif`, `xfail`, and runtime
`pytest.skip`/`pytest.xfail` yield unknown status; no conditions are evaluated.
Per-row marks do not set the entire declaration's status.

Body loops/comprehensions set `body_iteration`, not framework parameterization,
and never increase the static declaration count. Category evidence is conservative:
unresolved fixtures, imports, services or mocked dependencies remain unknown.

## Limitations

This is static declaration discovery, not pytest's runtime collection contract.
Dynamic decorators/aliases, plugins, inherited tests, hook modifications, fixture
resolution and arbitrary Python binding changes are not resolved. A syntax error
is reported explicitly; the file is not imported or silently treated as a
successfully parsed module. Test-like Python without pytest evidence is retained
as suspected declarations and contributes no recognized definitions.
