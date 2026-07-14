# Releasing

Releases use three deliberately separate GitHub Actions workflows. Draft
creation and verification start independently from the same signed version tag;
neither workflow owns, invokes, waits for, or delays the other.

## Parallel same-tag preparation

Push a signed semantic version tag matching `v*.*.*`. That single tag push
starts both preparation workflows:

- `create-draft-release.yml` creates the GitHub draft release and generated
  notes. Its `draft-release` job is the only release-creation owner and the only
  preparation job with `contents: write`.
- `verify-release.yml` verifies the tag and commit identity, runs the platform
  and deep-verification lanes, builds and checks the exact versioned artifacts,
  audits dependencies, generates the SBOM and hashes, and attests the results.
  It cannot create or publish a GitHub Release.

Verification has internal dependencies so its final artifact job waits for its
own preflight, platform, and deep-verification jobs. Those dependencies do not
extend to draft creation. Draft creation may finish before or after verification
without changing release ownership.

## Human approval and publication

The generated GitHub Release remains a draft. Before publishing it, a
maintainer reviews the notes and confirms that the verification workflow for the
same tag completed successfully. Publishing the draft is the human approval
gate; verification does not publish it automatically.

`python-publish.yml` listens only for `release.published`. Its `publish` job
checks out the published release, rebuilds the distributions with PDM, and uses
the `release` environment's Trusted Publishing identity to upload to PyPI. No
tag-push workflow owns PyPI publication credentials or publication behavior.

## Policy invariants

The parsed workflow-policy tests enforce:

- identical `push.tags: ["v*.*.*"]` triggers for draft creation and
  verification;
- no trigger or dependency edge between those two workflows;
- exact job ownership and permission scope for draft creation, verification,
  attestation, and PyPI publication;
- tag/commit verification and meaningful command ordering inside verification;
- no release-creation permission, action, command, or secret in verification;
  and
- the exact `release.published` publication trigger.

Comments, disabled or unrelated jobs, and incorrectly nested YAML cannot satisfy
these checks. Formatting, key ordering, and indentation do not affect them.
