# Releasing

1. Run `pdm run check`, then `pdm run build` and `pdm run package-test`.
2. Create and push a semantic version tag matching `v*.*.*`.
3. The tag verifies the backend on macOS, Linux, and Windows, then builds and
   clean-installs the exact tagged artifacts.
4. The same tag creates a GitHub draft release. Review its notes and publish it
   after verification completes.
5. Publishing the GitHub Release triggers PyPI Trusted Publishing.

The draft-release workflow creates release notes. The verification workflow only
tests the tag and artifacts; it does not publish a release or upload to PyPI.
