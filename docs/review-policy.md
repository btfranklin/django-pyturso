# Review Policy

Every change must pass `pdm run check`. Changes to public backend behavior,
connection/transaction state, SQL generation, schema handling, test-database
lifecycle, dependency support, or release evidence are major code changes and
also require a deep codebase council review.

Changes that reorganize module ownership, abstractions, dependency direction,
or the test/evidence architecture are major structural changes. They require a
structural clarity and maintainability review after correctness findings have
been remediated.

Each required review records the reviewed commit, concrete findings and
pressure points, a disposition for every item, closure confirmation, and the
final tested commit. Automated validation can prove that this metadata exists
and points at the current commit; maintainer judgment closes the review.

Valid dispositions are `fixed`, `not applicable`, `declined`, and `deferred`.
Critical/high findings and any finding that contradicts a current support or
release claim block completion.
