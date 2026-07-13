# Documentation

- [Architecture](architecture.md): package boundaries and supported runtime.
- [Backend contract](design/backend-contract.md): v1 behavior and exclusions.
- [Native platform CI deployment guide](../NATIVE_PLATFORM_CI.md): deferred
  native-runner evidence procedure.
- [Review policy](review-policy.md): required reasoning-review gates and evidence.
- [Django provenance](design/django-provenance.md): exact reference source and
  adaptation ledger.
- [Driver/platform evidence](design/evidence/driver-platform-matrix.md):
  reproducible Phase 0A observations.
- [Migration corpus evidence](design/evidence/migration-corpus.md): reversible
  schema/data digests and residue checks.
- [Compatibility status](compatibility.md): verified behavior and intentional driver boundaries.
- [Configuration](configuration.md): accepted database settings and initialization.
- [Transactions](transactions.md): transaction and constraint lifecycle.
- [Test runner](test-runner.md): supported file/memory test modes and rejections.
- [Switching from SQLite](switching.md): offline migration and rollback procedure.
- [Django capability declarations](capabilities.md): fixed framework
  compatibility facts.
- [Post-v1 roadmap](roadmap.md): explicitly deferred optional and operational
  capabilities.
- [Testing](testing.md): test taxonomy, commands, and durable evidence.
- [Coverage and mutation](testing-coverage.md): measured branch ratchets,
  artifacts, and mutation policy.
- [Upstream Django lane](testing-upstream.md): pinned source, manifest, and
  intentional differences.
- [Hardening](testing-hardening.md): property, fault-injection, stress, and
  recovery coverage.
- [Performance](performance.md): correctness-first workloads, query caps, and timing policy.
- [Security and supply chain](security.md): path and SQL boundaries, dependency
  policy, exceptions, and workflows.
