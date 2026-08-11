"""卡片渲染：把 PromoPost 填进 HTML 模板，用系统 Chrome/Edge 无头截图成 1080×1440 PNG。

主流方案（参考 Auto-Redbook-Skills）：内容 -> HTML/CSS -> 浏览器截图，比文生图更可控、
文字清晰、风格统一。这里直接调系统已装的 Chrome/Edge 无头模式（零 Python 依赖，
规避 Python 3.14 下 playwright/greenlet 装不上的问题）。
"""
from __future__ import annotations

import html as _html
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .types import PromoPost

_TPL_DIR = Path(__file__).resolve().parent / "templates"
CARD_W, CARD_H = 1080, 1440

_BROWSER_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def _find_browser() -> str:
    env = os.environ.get("CHROME_PATH")
    if env and Path(env).exists():
        return env
    for c in _BROWSER_CANDIDATES:
        if Path(c).exists():
            return c
    for name in ("chrome", "chrome.exe", "msedge", "msedge.exe", "chromium"):
        p = shutil.which(name)
        if p:
            return p
    raise RuntimeError("未找到 Chrome/Edge，请装 Chrome 或在 .env 设 CHROME_PATH")


def _hl(text: str) -> str:
    """转义 HTML 后，把 **关键词** 变成荧光高亮 span。"""
    esc = _html.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r'<span class="hl">\1</span>', esc)


def _bold(text: str) -> str:
    esc = _html.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc)


def _photo_bg(image_path: str) -> str:
    if image_path and Path(image_path).exists():
        uri = Path(image_path).resolve().as_uri()
        return f"url('{uri}')"
    # 无图时的占位：暖色斜向渐变 + 提示
    return ("linear-gradient(135deg,#F0D9B5,#E59A2B)")


def _fill(tpl: str, mapping: dict) -> str:
    for k, v in mapping.items():
        tpl = tpl.replace("{{" + k + "}}", str(v))
    return tpl


def build_cover_html(post: PromoPost) -> str:
    tpl = (_TPL_DIR / "cover.html").read_text(encoding="utf-8")
    points = "".join(
        f'<div class="pt"><span class="dot">✓</span>{_html.escape(p)}</div>'
        for p in post.cover_points
    )
    return _fill(tpl, {
        "kicker": _html.escape(post.kicker), "index": _html.escape(post.index),
        "title_html": _hl(post.title), "subtitle": _html.escape(post.subtitle),
        "price": _html.escape(post.price), "points_html": points,
        "handle": _html.escape(post.handle), "footer_note": _html.escape(post.footer_note),
        "photo_bg": _photo_bg(""),  # 商品图由调用方设置，见 render_cards 的 image_path
    })


def build_content_html(post: PromoPost) -> str:
    tpl = (_TPL_DIR / "content.html").read_text(encoding="utf-8")
    items = "".join(
        f'<div class="item"><div class="num">{i+1}</div>'
        f'<div class="it-body"><div class="lead">{_html.escape(it["lead"])}</div>'
        f'<div class="desc">{_html.escape(it["desc"])}</div></div></div>'
        for i, it in enumerate(post.content_items)
    )
    return _fill(tpl, {
        "eyebrow": _html.escape(post.content_eyebrow),
        "heading_html": _hl(post.content_heading),
        "items_html": items, "callout_html": _bold(post.callout),
        "handle": _html.escape(post.handle), "footer_note": _html.escape(post.footer_note),
    })


def _screenshot(html: str, out_path: Path, scale: int = 2) -> None:
    """用无头浏览器把 HTML 截成图。窗口设为卡片尺寸，整窗截图即整张卡。"""
    browser = _find_browser()
    with tempfile.TemporaryDirectory() as tmp:
        html_file = Path(tmp) / "card.html"
        html_file.write_text(html, encoding="utf-8")
        user_dir = Path(tmp) / "udd"  # 独立 profile，避免和用户已开的浏览器冲突
        cmd = [
            browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--no-first-run", "--no-default-browser-check",
            f"--user-data-dir={user_dir}",
            f"--force-device-scale-factor={scale}",
            f"--window-size={CARD_W},{CARD_H}",
            "--default-background-color=00000000",
            "--virtual-time-budget=5000",   # 给 Web 字体/布局加载时间
            f"--screenshot={out_path}",
            html_file.as_uri(),
        ]
        subprocess.run(cmd, timeout=90, capture_output=True)
    if not out_path.exists():
        raise RuntimeError(f"截图失败，未生成 {out_path}（检查浏览器/字体网络）")


def _ensure_local_image(image_path: str, out_dir: Path) -> str:
    """商品图若是远程 URL（如 1688 主图）则下载到本地；下载失败/非 http 原样返回。"""
    if not image_path or not image_path.startswith(("http://", "https://")):
        return image_path
    try:
        import urllib.request

        ext = ".png" if image_path.lower().split("?")[0].endswith(".png") else ".jpg"
        dst = out_dir / f"_product{ext}"
        req = urllib.request.Request(image_path, headers={
            "User-Agent": "Mozilla/5.0", "Referer": "https://www.1688.com/",
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
        if not data:
            return ""
        dst.write_bytes(data)
        return str(dst)
    except Exception:  # noqa: BLE001 下载失败 -> 回退占位渐变
        return ""


def render_cards(post: PromoPost, out_dir: str, image_path: str = "") -> list[str]:
    """渲染封面 + 内容卡为 PNG，返回文件路径列表。用系统 Chrome/Edge 无头截图。
    image_path 支持本地路径或远程 URL（远程会先下载，失败则用占位渐变）。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    local_image = _ensure_local_image(image_path, out)
    cover_html = build_cover_html(post).replace(_photo_bg(""), _photo_bg(local_image))
    content_html = build_content_html(post)

    saved = []
    for name, content in (("cover", cover_html), ("content", content_html)):
        path = out / f"{name}.png"
        _screenshot(content, path)
        saved.append(str(path))
    return saved
