"""小红书人工发布包：图片、正文和可审计 manifest。"""
from __future__ import annotations

import json
import hashlib
import shutil
from pathlib import Path

from .types import PromoPost


def export_package(post: PromoPost, image_paths: list[str], out_dir: str, source_snapshot: dict) -> str:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    images = []
    for image_path in image_paths:
        source = Path(image_path)
        if not source.is_file():
            raise FileNotFoundError(f"小红书发布包图片不存在：{source}")
        destination = out / source.name
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        images.append({
            "name": destination.name,
            "bytes": destination.stat().st_size,
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        })
    caption_path = out / "caption.txt"
    caption_path.write_text(post.xhs_caption, encoding="utf-8")
    manifest = {
        "channel": "xiaohongshu",
        "title": post.title,
        "subtitle": post.subtitle,
        "caption": post.xhs_caption,
        "images": images,
        "source": source_snapshot,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(out)
