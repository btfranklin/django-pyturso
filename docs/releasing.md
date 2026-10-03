# Releasing

1. Run `pdm run check-full` and `pdm run test-mvcc` with both an in-memory and
   a disposable file database. Then run `pdm run build` and `pdm run package-test`.
2. Create and push a semantic version tag matching `v*.*.*`.
3. The tag verifies the backend on macOS, Linux, and Windows, then builds and
   clean-installs the exact tagged artifacts. Each platform runs the MVCC
   application checks with both database types.
4. The same tag creates a GitHub draft release. Review its notes and publish it
   after verification completes.
5. Publishing the GitHub Release triggers PyPI Trusted Publishing.

Before upload, the publication job checks the lockfile and the full test gate.
It builds both archives, checks their version against the release tag, and
clean-installs each archive for the Django smoke tests.

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
