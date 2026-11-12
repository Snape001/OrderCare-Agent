"""Offline BGE cross-encoder ranking for policy retrieval experiments."""

from __future__ import annotations

import hashlib
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort  # type: ignore[import-untyped]
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

MODEL_ID = "BAAI/bge-reranker-base"
MODEL_REVISION = "2cfc18c9415c912f9d8155881c133215df768a70"
MODEL_FILES = (
    "onnx/model.onnx", "tokenizer.json", "tokenizer_config.json",
    "special_tokens_map.json", "config.json",
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class BGEReranker:
    """Score query and policy passage pairs with the pinned official ONNX model."""

    def __init__(self, cache_dir: Path = Path("data/models/bge-reranker-base")) -> None:
        started = time.perf_counter()
        files: dict[str, Path] = {}
        for name in MODEL_FILES:
            try:
                files[name] = Path(hf_hub_download(
                    repo_id=MODEL_ID, filename=name, revision=MODEL_REVISION,
                    local_dir=str(cache_dir), local_files_only=True,
                ))
            except (FileNotFoundError, OSError):
                files[name] = Path(hf_hub_download(
                    repo_id=MODEL_ID, filename=name, revision=MODEL_REVISION,
                    local_dir=str(cache_dir),
                ))
        self.download_ms = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        self.tokenizer = Tokenizer.from_file(str(files["tokenizer.json"]))
        self.tokenizer.enable_truncation(max_length=512)
        self.tokenizer.enable_padding(pad_id=1, pad_token="<pad>")
        self.session = ort.InferenceSession(
            str(files["onnx/model.onnx"]),
            providers=["CPUExecutionProvider"],
            sess_options=ort.SessionOptions(),
        )
        self.load_ms = (time.perf_counter() - started) * 1000
        self.model_sha256 = file_sha256(files["onnx/model.onnx"])
        self.tokenizer_sha256 = file_sha256(files["tokenizer.json"])

    def score(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        encodings = self.tokenizer.encode_batch([(query, passage) for passage in passages])
        arrays = {
            "input_ids": np.asarray([e.ids for e in encodings], dtype=np.int64),
            "attention_mask": np.asarray([e.attention_mask for e in encodings], dtype=np.int64),
            "token_type_ids": np.asarray([e.type_ids for e in encodings], dtype=np.int64),
        }
        inputs = {item.name: arrays[item.name] for item in self.session.get_inputs()}
        logits: Any = self.session.run(None, inputs)[0]
        return [float(value) for value in np.asarray(logits).reshape(-1)]


@lru_cache(maxsize=1)
def get_reranker() -> BGEReranker:
    """Keep the ONNX Runtime session resident for this Python process."""
    return BGEReranker()
