# Python type safety

## Checks

Run the type check for all package code, tests, and scripts:

```bash
pdm run typecheck
```

Both aggregate checks include this command. Mypy uses strict mode. It also
rejects explicit `Any`, types from imports that it cannot inspect, and decorators
that remove type information. It reports code that it considers unreachable.
Generic containers must specify their item types.

Hypothesis declares decorated tests as `Callable[..., None]`. Only the property
test modules permit this decorator type. Their function bodies and explicit
annotations still use all other checks.

## Data boundaries

Use a concrete type when the data shape is known. Use `object` for a value that
the code must inspect before use, or for a value that the code only passes on.
`object` does not permit arbitrary method calls, indexing, or arithmetic.

Database parameters accept iterables or mappings of values. Raw database rows
contain heterogeneous values, so their cells use `object`. PRAGMA queries have
specific tuple types for their result columns. Constraint dictionaries use the
Django stub's `TypedDict`. Schema fields use `Field[Never, object]` for access to
field metadata without permission to set field values.

JSON and TOML enter through standard-library APIs that return dynamic types.
Scripts and test helpers check these values before they return typed data.
Recursive JSON types specify the permitted values in lists and dictionaries.

## External limits

The project has no explicit `Any` annotations in its Python files. This does not
mean that all dependency expressions have static types. Django's ORM, cursor
attribute delegation, model metaclass, and migration interfaces still expose
implicit `Any`. The Turso driver also returns dynamic row types, and sqlparse
has incomplete annotations. The stress tests use a small process protocol
because psutil has no installed stubs.

Keep casts at these known boundaries. A cast supplies a static contract; it does
not check a runtime value. Fetch methods check that driver rows have the tuple format required by this
backend. They reject custom row factories that return another format. SQL parser protocols specify only the members that the
backend reads. Test doubles use concrete casts where a test supplies only part
of a framework object.

Some Django stub declarations differ from the supported runtime. These include
callable column types, commit-hook tuples, backend field metadata, relation
tuples, and selected schema and operation methods. Use a specific mypy error
code and an explanation for each required suppression. Do not use a blanket
ignore or an `Any` cast to avoid a type error.

A full ban on implicit `Any` expressions is not enabled. Such a ban would also
reject many normal Django calls because of the dependency annotations. Review
those boundaries when the dependencies change. Keep internal values concrete
and check data from external inputs before use.
