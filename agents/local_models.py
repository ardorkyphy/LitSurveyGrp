# -*- coding: utf-8 -*-
"""Local retrieval models used by evidence selection.

Model weights are intentionally stored under ``agents/models`` so the agent
layer can use them without depending on Hugging Face cache locations.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


AGENTS_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_ROOT = AGENTS_DIR / "models"
DEFAULT_EMBEDDING_REPO = "BAAI/bge-m3"
DEFAULT_RERANKER_REPO = "BAAI/bge-reranker-base"


@dataclass(frozen=True)
class LocalModelSpec:
    role: str
    repo_id: str
    path: Path
    required: bool = True


def default_specs(model_root: Path | None = None, include_reranker: bool = True) -> list[LocalModelSpec]:
    root = Path(model_root or os.environ.get("LSG_LOCAL_MODEL_DIR", "") or DEFAULT_MODEL_ROOT)
    specs = [
        LocalModelSpec("embedding", DEFAULT_EMBEDDING_REPO, root / "bge-m3", required=True),
    ]
    if include_reranker:
        specs.append(LocalModelSpec("reranker", DEFAULT_RERANKER_REPO, root / "bge-reranker-base", required=False))
    return specs


def model_ready(path: Path) -> bool:
    path = Path(path)
    if not path.exists() or not (path / "config.json").exists():
        return False
    weight_files = list(path.glob("*.safetensors")) + list(path.glob("*.bin"))
    return any(item.is_file() and item.stat().st_size > 10_000_000 for item in weight_files)


def detect_device(preferred: str = "auto") -> str:
    if preferred and preferred != "auto":
        return preferred
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def gpu_status() -> dict:
    try:
        import torch

        available = bool(torch.cuda.is_available())
        return {
            "torch": getattr(torch, "__version__", ""),
            "cuda_available": available,
            "device_count": int(torch.cuda.device_count()) if available else 0,
            "device_name": torch.cuda.get_device_name(0) if available else "",
        }
    except Exception as exc:
        return {"torch": "", "cuda_available": False, "device_count": 0, "device_name": "", "error": str(exc)}


def download_models(
    model_root: Path | None = None,
    include_reranker: bool = True,
    force: bool = False,
    endpoint: str = "",
) -> list[dict]:
    if endpoint:
        os.environ["HF_ENDPOINT"] = endpoint.rstrip("/")
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    from huggingface_hub import snapshot_download

    records = []
    for spec in default_specs(model_root, include_reranker=include_reranker):
        spec.path.mkdir(parents=True, exist_ok=True)
        skipped = model_ready(spec.path) and not force
        if not skipped:
            snapshot_download(
                repo_id=spec.repo_id,
                local_dir=str(spec.path),
                local_dir_use_symlinks=False,
            )
        records.append({
            "role": spec.role,
            "repo_id": spec.repo_id,
            "path": str(spec.path),
            "ready": model_ready(spec.path),
            "skipped": skipped,
        })
    return records


def load_embedding_model(model_root: Path | None = None, device: str = "auto"):
    from sentence_transformers import SentenceTransformer

    spec = default_specs(model_root, include_reranker=False)[0]
    model_path = spec.path if model_ready(spec.path) else spec.repo_id
    return SentenceTransformer(str(model_path), device=detect_device(device))


def embed_texts(texts: Iterable[str], model_root: Path | None = None, device: str = "auto") -> list[list[float]]:
    model = load_embedding_model(model_root=model_root, device=device)
    vectors = model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False)
    return vectors.tolist()


def load_reranker_model(model_root: Path | None = None, device: str = "auto"):
    from sentence_transformers import CrossEncoder

    specs = default_specs(model_root, include_reranker=True)
    spec = next(item for item in specs if item.role == "reranker")
    model_path = spec.path if model_ready(spec.path) else spec.repo_id
    return CrossEncoder(str(model_path), device=detect_device(device))


def rerank(query: str, passages: Iterable[str], model_root: Path | None = None, device: str = "auto") -> list[dict]:
    model = load_reranker_model(model_root=model_root, device=device)
    passages = list(passages)
    scores = model.predict([(query, passage) for passage in passages])
    return [
        {"index": index, "score": float(score), "text": passages[index]}
        for index, score in sorted(enumerate(scores), key=lambda item: float(item[1]), reverse=True)
    ]


def status(model_root: Path | None = None, include_reranker: bool = True) -> dict:
    specs = default_specs(model_root, include_reranker=include_reranker)
    return {
        "model_root": str(Path(model_root or os.environ.get("LSG_LOCAL_MODEL_DIR", "") or DEFAULT_MODEL_ROOT)),
        "gpu": gpu_status(),
        "models": [
            {
                "role": spec.role,
                "repo_id": spec.repo_id,
                "path": str(spec.path),
                "ready": model_ready(spec.path),
                "required": spec.required,
            }
            for spec in specs
        ],
    }


def self_test(model_root: Path | None = None, device: str = "auto", include_reranker: bool = True) -> dict:
    texts = [
        "This study identifies a gap in aging biomarker validation.",
        "The method uses a cohort design and proteomic measurements.",
        "The article discusses unrelated publishing metadata.",
    ]
    vectors = embed_texts(texts, model_root=model_root, device=device)
    result = {
        "device": detect_device(device),
        "embedding_vectors": len(vectors),
        "embedding_dimension": len(vectors[0]) if vectors else 0,
    }
    if include_reranker:
        ranked = rerank("methods and data used in the study", texts, model_root=model_root, device=device)
        result["reranker_top_index"] = ranked[0]["index"] if ranked else None
        result["reranker_top_score"] = ranked[0]["score"] if ranked else None
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage local agent retrieval models")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--model-root", type=Path, default=None, help="model directory; defaults to agents/models")
        subparser.add_argument("--no-reranker", action="store_true", help="skip optional reranker model")

    download = subparsers.add_parser("download", help="download local models into agents/models")
    add_common(download)
    download.add_argument("--force", action="store_true", help="redownload even when config.json exists")
    download.add_argument("--endpoint", default="", help="optional Hugging Face-compatible endpoint, e.g. https://hf-mirror.com")

    stat = subparsers.add_parser("status", help="show GPU and local model status")
    add_common(stat)

    test = subparsers.add_parser("self-test", help="load local models and run a small inference")
    add_common(test)
    test.add_argument("--device", default="auto", help="auto, cuda, or cpu")

    args = parser.parse_args(argv)
    if args.command == "download":
        payload = download_models(
            args.model_root,
            include_reranker=not args.no_reranker,
            force=args.force,
            endpoint=args.endpoint,
        )
    elif args.command == "status":
        payload = status(args.model_root, include_reranker=not args.no_reranker)
    elif args.command == "self-test":
        payload = self_test(args.model_root, device=args.device, include_reranker=not args.no_reranker)
    else:
        parser.error(f"unsupported command: {args.command}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
