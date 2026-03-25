"""Tests for recall --json output contract."""

import json
import shutil
import subprocess

import pytest

RECALL_BIN = shutil.which("recall") or "/Users/julianlo/.local/bin/recall"

recall_installed = pytest.mark.skipif(
    not shutil.which("recall") and not shutil.which(RECALL_BIN),
    reason="recall is not installed",
)

EXPECTED_FIELDS = {"agent", "role", "session_id", "project", "timestamp", "score", "resume_cmd", "text"}


def _run_recall(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [RECALL_BIN, *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


@recall_installed
def test_json_output_schema():
    """Run recall --json -n 1 'test', parse JSON, assert all fields present with correct types."""
    result = _run_recall("--json", "-n", "1", "test")
    assert result.returncode == 0, f"recall failed: {result.stderr}"

    data = json.loads(result.stdout)
    assert isinstance(data, list), "Expected a JSON array"

    if len(data) == 0:
        pytest.skip("No results returned; cannot validate field types")

    item = data[0]

    assert isinstance(item["agent"], str)
    assert isinstance(item["role"], str)
    assert isinstance(item["session_id"], str)
    assert isinstance(item["project"], str)
    assert isinstance(item["timestamp"], float)
    assert isinstance(item["score"], float)
    assert 0.0 <= item["score"] <= 1.0
    assert isinstance(item["resume_cmd"], str)
    assert isinstance(item["text"], str)


@recall_installed
def test_json_output_empty_query_returns_array():
    """Verify that a nonsense query returns a valid JSON array (possibly empty)."""
    result = _run_recall("--json", "xyznonexistent12345")
    assert result.returncode == 0, f"recall failed: {result.stderr}"

    data = json.loads(result.stdout)
    assert isinstance(data, list), "Expected a JSON array even for zero results"


@recall_installed
def test_json_field_names():
    """Assert the exact field names match the contract — no extra, no missing."""
    result = _run_recall("--json", "-n", "1", "test")
    assert result.returncode == 0, f"recall failed: {result.stderr}"

    data = json.loads(result.stdout)
    assert isinstance(data, list)

    if len(data) == 0:
        pytest.skip("No results returned; cannot validate field names")

    for item in data:
        assert set(item.keys()) == EXPECTED_FIELDS, (
            f"Field mismatch: extra={set(item.keys()) - EXPECTED_FIELDS}, "
            f"missing={EXPECTED_FIELDS - set(item.keys())}"
        )


@recall_installed
def test_json_role_values():
    """If results returned, verify role is either 'user' or 'assistant'."""
    result = _run_recall("--json", "-n", "5", "test")
    assert result.returncode == 0, f"recall failed: {result.stderr}"

    data = json.loads(result.stdout)
    assert isinstance(data, list)

    if len(data) == 0:
        pytest.skip("No results returned; cannot validate role values")

    for item in data:
        assert item["role"] in ("user", "assistant"), (
            f"Unexpected role value: {item['role']!r}"
        )
