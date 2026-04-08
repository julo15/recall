"""Tests for recall.embedding.encode() progress_callback."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from recall.embedding import encode


def _fake_encoding(ids: list[int]):
    """Create a minimal fake encoding object returned by tokenizer.encode_batch."""
    enc = MagicMock()
    enc.ids = ids
    enc.attention_mask = [1] * len(ids)
    return enc


def _make_fake_session_and_tokenizer(token_len: int = 4, embed_dim: int = 384):
    """Return (session, tokenizer) mocks that produce deterministic outputs."""
    session = MagicMock()
    inp = MagicMock()
    inp.name = "input_ids"
    session.get_inputs.return_value = [inp]

    def run_side_effect(_output_names, feeds):
        batch_size = feeds["input_ids"].shape[0]
        seq_len = feeds["input_ids"].shape[1]
        # Return random token embeddings: (batch, seq_len, embed_dim)
        return [np.random.randn(batch_size, seq_len, embed_dim).astype(np.float32)]

    session.run.side_effect = run_side_effect

    tokenizer = MagicMock()
    tokenizer.encode_batch.side_effect = lambda texts: [
        _fake_encoding([1] * token_len) for _ in texts
    ]

    return session, tokenizer


@patch("recall.embedding._get_session")
def test_progress_callback_called_correctly(mock_get_session):
    """progress_callback receives (done, total) after each batch."""
    session, tokenizer = _make_fake_session_and_tokenizer()
    mock_get_session.return_value = (session, tokenizer)

    texts = ["a", "b", "c", "d", "e"]
    callback = MagicMock()

    encode(texts, batch_size=2, progress_callback=callback)

    # ceil(5 / 2) = 3 batches
    assert callback.call_count == 3
    callback.assert_any_call(2, 5)
    callback.assert_any_call(4, 5)
    callback.assert_any_call(5, 5)  # clamped on last batch


@patch("recall.embedding._get_session")
def test_progress_callback_single_batch(mock_get_session):
    """When all texts fit in one batch, callback is called once."""
    session, tokenizer = _make_fake_session_and_tokenizer()
    mock_get_session.return_value = (session, tokenizer)

    texts = ["a", "b"]
    callback = MagicMock()

    encode(texts, batch_size=10, progress_callback=callback)

    assert callback.call_count == 1
    callback.assert_called_once_with(2, 2)


@patch("recall.embedding._get_session")
def test_progress_callback_none_by_default(mock_get_session):
    """When progress_callback is None (default), no callback errors occur."""
    session, tokenizer = _make_fake_session_and_tokenizer()
    mock_get_session.return_value = (session, tokenizer)

    texts = ["a", "b", "c"]

    # Should not raise — just verifying the default None path works
    result = encode(texts, batch_size=2)
    assert result.shape[0] == 3


@patch("recall.embedding._get_session")
def test_progress_callback_exact_multiple(mock_get_session):
    """When len(texts) is an exact multiple of batch_size, done equals total on last call."""
    session, tokenizer = _make_fake_session_and_tokenizer()
    mock_get_session.return_value = (session, tokenizer)

    texts = ["a", "b", "c", "d"]
    callback = MagicMock()

    encode(texts, batch_size=2, progress_callback=callback)

    assert callback.call_count == 2
    callback.assert_any_call(2, 4)
    callback.assert_any_call(4, 4)
