# Releasing

1. Run `pdm run check-full` and `pdm run test-mvcc` with both an in-memory and
   a disposable file database. Then run `pdm run build` and `pdm run package-test`.
2. Create and push a semantic version tag matching `v*.*.*`.
3. The tag verifies the backend on macOS, Linux, and Windows, then builds and
   clean-installs the exact tagged artifacts. Each platform runs the MVCC
   application checks with both database types.
4. The same tag creates a GitHub draft release. Review its notes and publish it
   after verification completes.
5. Publishing the GitHub Release starts the same verification workflow again
   for the release commit. PyPI Trusted Publishing waits for that run to pass.

Before upload, the reusable verification workflow checks the release commit on
macOS, Linux, and Windows. Each platform runs the full check and both MVCC modes.
The package job waits for all platforms, builds both archives, checks their
version against the release tag, and clean-installs each archive for the Django
smoke tests. It stores the verified archives as a workflow artifact.

The publication job runs only after verification succeeds. It downloads those
archives from the same run and uploads them without a rebuild. A failed,
cancelled, or incomplete verification cannot start publication. Only the
publication job has `id-token: write`; the verification jobs retain read-only
repository access. Publishing the GitHub Release remains a human action.

To run the platform and package checks before you create a tag, push the branch
and start the verification workflow:

```bash
gh workflow run verify-release.yml --ref main
```

This run checks the selected branch on all three platforms and verifies both
package archives. A tag run also checks that each artifact version matches the
tag.

Package build jobs fetch the full Git history and tags. The package version
comes from the latest version tag and the commits after it.

The draft-release workflow creates release notes. The verification workflow only
tests the branch or tag and artifacts; it does not publish a release or upload
to PyPI.
