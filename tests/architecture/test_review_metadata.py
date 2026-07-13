"""Review metadata validator contract tests."""

from scripts.validate_review_metadata import validate

SHA = "0123456789abcdef0123456789abcdef01234567"


def test_nonmajor_review_metadata_requires_classification_and_tested_sha() -> None:
    body = f"""
- Major code change: no, documentation only
- Major structural change: no, no ownership changed
- Final tested commit: {SHA}
"""
    assert validate(body, SHA) == []


def test_major_review_metadata_requires_reports_and_closure() -> None:
    body = f"""
- Major code change: yes, transaction behavior changed
- Major structural change: no, module ownership is unchanged
- Final tested commit: {SHA}
"""
    errors = validate(body, SHA)
    assert any("Deep codebase review" in error for error in errors)
    assert any("Finding disposition" in error for error in errors)
    assert any("Reviewer-confirmed closure" in error for error in errors)


def test_final_tested_commit_must_match_head() -> None:
    body = """
- Major code change: no, documentation only
- Major structural change: no, no ownership changed
- Final tested commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
"""
    assert validate(body, SHA) == ["Final tested commit must match the pull-request head SHA"]
