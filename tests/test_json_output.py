"""Tests for recall --json output contract."""

import json
import shutil
import subprocess

import pytest

RECALL_BIN = shutil.which("recall")

recall_installed = pytest.mark.skipif(
    RECALL_BIN is None,
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
    assert isinstance(item["timestamp"], (int, float))
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


@recall_installed
def test_json_stdout_is_pure_json():
    """Verify stdout contains no preamble text — just pure JSON.

    This catches the bug where status messages leak to stdout instead of stderr.
    """
    result = _run_recall("--json", "-n", "1", "test")
    assert result.returncode == 0, f"recall failed: {result.stderr}"

    stripped = result.stdout.lstrip()
    assert stripped.startswith("["), (
        f"Expected stdout to start with '[' (JSON array), "
        f"but got: {stripped[:80]!r}"
    )


@recall_installed
def test_json_mode_stderr_is_valid():
    """When running in --json mode, any stderr JSON lines should be valid JSON with expected schema."""
    result = _run_recall("--json", "-n", "1", "test")
    assert result.returncode == 0, f"recall failed: {result.stderr}"

    # Parse any JSON lines from stderr
    for line in result.stderr.strip().splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        data = json.loads(line)
        assert "status" in data, f"stderr JSON missing 'status': {data}"
        if data["status"] == "indexing":
            if "count" in data:
                # Initial line: {"status": "indexing", "count": N}
                assert isinstance(data["count"], int), f"count is not int: {data}"
                assert data["count"] > 0, f"count should be positive: {data}"
            elif "done" in data and "total" in data:
                # Progress line: {"status": "indexing", "done": N, "total": M}
                assert isinstance(data["done"], int), f"done is not int: {data}"
                assert isinstance(data["total"], int), f"total is not int: {data}"
                assert data["done"] <= data["total"], f"done should be <= total: {data}"
            else:
                pytest.fail(f"indexing status has unexpected shape: {data}")


@recall_installed
def test_json_reindex_emits_indexing_status():
    """Force a full reindex to guarantee the indexing status JSON appears on stderr."""
    # Stream stderr line-by-line so we can stop as soon as we see the indexing
    # status line, rather than waiting for the entire reindex to finish.
    proc = subprocess.Popen(
        [RECALL_BIN, "--reindex", "--json", "-n", "1", "test"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        found_indexing = False
        for line in proc.stderr:
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            data = json.loads(line)
            if data.get("status") == "indexing" and "count" in data:
                assert isinstance(data["count"], int), f"count is not int: {data}"
                assert data["count"] > 0, f"count should be positive: {data}"
                found_indexing = True
                break
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    assert found_indexing, (
        f"Expected indexing status JSON on stderr during --reindex, "
        f"but stderr was: {result.stderr[:200]!r}"
    )
