# Releasing

1. Create and push a semantic version tag matching `v*.*.*`.
2. Wait for the Create Draft Release workflow to finish. Its reusable verification
   calls ordinary Python package CI with the release platform matrix enabled,
   plus CodeQL for Python and Actions. No separate verification run starts on tags.
3. Validation runs the full documentation, lint, type, and test suite, runtime
   advisory audits, file-backed Django regressions, and both MVCC modes on macOS,
   Linux, and Windows. It builds and clean-installs both package archives and
   checks their versions against the tag. The ordinary current-dependency job
   also runs, including its audit and full checks. Dependency review remains
   specific to pull requests.
4. Only after all required checks pass does release-notes-scribe create the actual
   GitHub draft release. Review the generated notes and click Publish.
5. The `release: published` event starts Upload Python Package. It checks out
   `github.event.release.tag_name` with full history, rebuilds the wheel and source
   distribution, and uploads them using PyPI Trusted Publishing. It trusts draft
   preparation and does not rerun validation or package-install smoke tests.

Ordinary GitHub draft creation does not trigger these workflows. The supported
validated path is push tag, wait for successful checks and the generated draft,
review, then Publish. Manually created drafts have no validation guarantee.
Do not move the tag between validation and publication. Failed preparation must
be fixed and successfully rerun before publication.

The publisher rebuilds from the same release tag; it does not retrieve archives
from draft preparation. Package builds fetch the full Git history and tags
because the version comes from Git. Only the publication job has
`id-token: write`, and it retains the `release` environment and
`python-publish.yml` Trusted Publisher identity. Validation has read-only
repository contents access; CodeQL also has security-event upload permission.
Publishing the GitHub Release remains a human action.

To run the same validation before creating a tag, push the branch and start:

```bash
gh workflow run verify-release.yml --ref main
```

This checks all three platforms, current dependencies, CodeQL, and both package
archives. It does not create a release or upload to PyPI. A tag run additionally
checks archive versions against the tag.
