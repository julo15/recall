"""Embedding module using ONNX Runtime + tokenizers (replaces sentence-transformers/PyTorch)."""

from __future__ import annotations

import os
import urllib.request
from collections.abc import Callable
from pathlib import Path

import numpy as np

MODEL_DIR = Path(os.path.expanduser("~/.recall/models/all-MiniLM-L6-v2"))
ONNX_PATH = MODEL_DIR / "onnx" / "model.onnx"
TOKENIZER_PATH = MODEL_DIR / "tokenizer.json"

ONNX_URL = "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/onnx/model.onnx"
TOKENIZER_URL = "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/tokenizer.json"

_session = None
_tokenizer = None


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {dest.name}...")
    urllib.request.urlretrieve(url, str(dest))


def _ensure_model_files() -> None:
    if not ONNX_PATH.exists():
        _download(ONNX_URL, ONNX_PATH)
    if not TOKENIZER_PATH.exists():
        _download(TOKENIZER_URL, TOKENIZER_PATH)


def _get_session():
    global _session, _tokenizer
    if _session is not None:
        return _session, _tokenizer

    _ensure_model_files()

    import onnxruntime as ort
    from tokenizers import Tokenizer

    _session = ort.InferenceSession(
        str(ONNX_PATH), providers=["CPUExecutionProvider"]
    )
    _tokenizer = Tokenizer.from_file(str(TOKENIZER_PATH))
    _tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
    _tokenizer.enable_truncation(max_length=256)

    return _session, _tokenizer


def encode(
    texts: list[str],
    batch_size: int = 64,
    show_progress_bar: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
) -> np.ndarray:
    """Encode texts into embeddings. Drop-in replacement for SentenceTransformer.encode()."""
    session, tokenizer = _get_session()

    input_names = {inp.name for inp in session.get_inputs()}
    all_embeddings: list[np.ndarray] = []

    batches = range(0, len(texts), batch_size)
    if show_progress_bar:
        from tqdm import tqdm
        batches = tqdm(batches, desc="Encoding", unit="batch")

    for start in batches:
        batch_texts = texts[start : start + batch_size]
        encodings = tokenizer.encode_batch(batch_texts)

        input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
        attention_mask = np.array(
            [e.attention_mask for e in encodings], dtype=np.int64
        )

        feeds = {"input_ids": input_ids, "attention_mask": attention_mask}
        if "token_type_ids" in input_names:
            feeds["token_type_ids"] = np.zeros_like(input_ids)

        outputs = session.run(None, feeds)
        token_embeddings = outputs[0]  # (batch, seq_len, 384)

        # Mean pooling
        mask_expanded = attention_mask[:, :, np.newaxis].astype(np.float32)
        sum_embeddings = np.sum(token_embeddings * mask_expanded, axis=1)
        sum_mask = np.clip(mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
        mean_pooled = sum_embeddings / sum_mask

        # L2 normalize
        norms = np.linalg.norm(mean_pooled, axis=1, keepdims=True)
        norms = np.clip(norms, a_min=1e-9, a_max=None)
        normalized = mean_pooled / norms

        all_embeddings.append(normalized.astype(np.float32))

        if progress_callback is not None:
            progress_callback(min(start + batch_size, len(texts)), len(texts))

    return np.vstack(all_embeddings)
