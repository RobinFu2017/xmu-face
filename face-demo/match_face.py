"""Extract 512-d buffalo_l embeddings and compare against gallery faces."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
GALLERY_DIR = ROOT / "gallery"
OUTPUT_DIR = ROOT / "output"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DEFAULT_THRESHOLD = 0.40


def load_app():
    from insightface.app import FaceAnalysis

    app = FaceAnalysis(
        name="buffalo_l",
        allowed_modules=["detection", "recognition"],
        providers=["CPUExecutionProvider"],
    )
    app.prepare(ctx_id=-1, det_size=(640, 640))
    return app


def read_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path))
    if image is None:
        raise FileNotFoundError(f"cannot read image: {path}")
    return image


def pick_face(faces: list, source: str):
    if not faces:
        raise ValueError(f"no face detected in {source}")
    if len(faces) > 1:
        print(f"[warn] {source}: {len(faces)} faces, using the largest")
    return max(faces, key=lambda face: float((face.bbox[2] - face.bbox[0]) * (face.bbox[3] - face.bbox[1])))


def extract_embedding(app, image: np.ndarray, source: str) -> tuple[np.ndarray, list[float]]:
    face = pick_face(app.get(image), source)
    embedding = np.asarray(face.normed_embedding, dtype=np.float32)
    if embedding.shape != (512,):
        raise RuntimeError(f"unexpected embedding shape {embedding.shape}, expected (512,)")
    bbox = [float(x) for x in face.bbox.tolist()]
    return embedding, bbox


def list_gallery_images(gallery_dir: Path) -> list[Path]:
    if not gallery_dir.is_dir():
        return []
    return sorted(
        path
        for path in gallery_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def run_self_test(app) -> int:
    from insightface.data import get_image

    image = get_image("t1")
    embedding, bbox = extract_embedding(app, image, "bundled:t1")
    print(f"[self-test] embedding shape={embedding.shape} dtype={embedding.dtype}")
    print(f"[self-test] bbox={bbox}")
    print(f"[self-test] first 8 values={embedding[:8].tolist()}")
    print("[self-test] OK")
    return 0


def run_match(app, query_path: Path, threshold: float) -> int:
    query_image = read_image(query_path)
    query_embedding, query_bbox = extract_embedding(app, query_image, str(query_path))

    print(f"query: {query_path}")
    print(f"embedding dim: {query_embedding.shape[0]}")
    print(f"bbox: {query_bbox}")
    print("embedding:")
    print(np.array2string(query_embedding, max_line_width=120, precision=6, separator=", "))

    gallery_images = list_gallery_images(GALLERY_DIR)
    matches: list[dict] = []

    if not gallery_images:
        print(f"\n[warn] no images in {GALLERY_DIR}; skip comparison")
    else:
        print(f"\nmatches (threshold={threshold:.2f}):")
        for gallery_path in gallery_images:
            try:
                gallery_image = read_image(gallery_path)
                gallery_embedding, _ = extract_embedding(app, gallery_image, str(gallery_path))
                score = cosine_similarity(query_embedding, gallery_embedding)
                matched = score >= threshold
                matches.append(
                    {
                        "name": gallery_path.name,
                        "path": str(gallery_path),
                        "score": score,
                        "matched": matched,
                    }
                )
            except Exception as exc:  # noqa: BLE001 - keep comparing remaining gallery images
                print(f"  {gallery_path.name:<20} ERROR  {exc}")

        matches.sort(key=lambda item: item["score"], reverse=True)
        for item in matches:
            flag = "MATCH" if item["matched"] else ""
            print(f"  {item['name']:<20} {item['score']:.3f}  {flag}".rstrip())

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{query_path.stem}.json"
    payload = {
        "query": str(query_path),
        "embedding_dim": int(query_embedding.shape[0]),
        "bbox": query_bbox,
        "threshold": threshold,
        "embedding": query_embedding.tolist(),
        "matches": matches,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {out_path}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="buffalo_l embedding + gallery match demo")
    parser.add_argument("query", nargs="?", type=Path, help="path to query face image")
    parser.add_argument("--self-test", action="store_true", help="run bundled sample embedding check")
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"cosine similarity threshold (default: {DEFAULT_THRESHOLD})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.self_test and args.query is None:
        print("usage: python match_face.py <query.jpg> | python match_face.py --self-test", file=sys.stderr)
        return 2

    print("loading buffalo_l (CPU / ONNX Runtime)...")
    app = load_app()

    if args.self_test:
        return run_self_test(app)

    query_path = args.query.resolve()
    if not query_path.is_file():
        print(f"query image not found: {query_path}", file=sys.stderr)
        return 1
    return run_match(app, query_path, args.threshold)


if __name__ == "__main__":
    raise SystemExit(main())
