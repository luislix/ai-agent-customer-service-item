"""推广模块 demo：商品 -> 通义千问文案 -> 渲染小红书图片卡片 + 输出发布正文。

用法（项目根目录）：
    python -m scripts.run_promotion_demo
产物：data/promo_demo/cover.png、content.png + 控制台打印小红书正文。
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import config  # noqa: E402
from src.llm.factory import build_llm  # noqa: E402
from src.modules.promotion.card_renderer import render_cards  # noqa: E402
from src.modules.promotion.copywriter import write_post  # noqa: E402
from src.modules.promotion.types import Product  # noqa: E402

# 示例商品（实际接选品模块输出）
SAMPLE = Product(
    title="索尼 WH-1000XM4 头戴降噪耳机 95新",
    price=899,
    category="数码好物",
    selling_points=["旗舰级降噪", "95新无暗病", "原装配件全"],
    image_path="",  # 有本地商品图就填路径，没有用占位渐变
)


def main() -> int:
    llm = build_llm()
    print(f"文案 LLM：{llm.name}（{'真实' if llm.name != 'placeholder' else '占位'}）\n生成文案中…")
    post = write_post(SAMPLE, llm, index="01")

    print("=" * 60)
    print("封面标题：", post.title)
    print("副标题　：", post.subtitle)
    print("卖点　　：", " / ".join(post.cover_points))
    print("内容点　：")
    for it in post.content_items:
        print(f"   - {it['lead']}：{it['desc']}")
    print("结尾　　：", post.callout)
    print("-" * 60)
    print("【小红书发布正文】\n" + post.xhs_caption)
    print("=" * 60)

    out_dir = str(Path(config.PROJECT_ROOT) / "data" / "promo_demo")
    try:
        files = render_cards(post, out_dir, image_path=SAMPLE.image_path)
        print("已生成图片卡片：")
        for f in files:
            print("   ", f)
    except Exception as e:  # noqa: BLE001
        print(f"[渲染失败] {e}\n（渲染走系统 Chrome/Edge 无头截图：请确认已装 Chrome/Edge，或在 .env 设 CHROME_PATH）")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
