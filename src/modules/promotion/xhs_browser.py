"""小红书创作后台浏览器填充。

该模块只准备待发布笔记，不点击最终发布按钮。浏览器使用本地持久化
profile 保存登录态，凭证不会进入数据库或日志。
"""
from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


CREATOR_HOME = "https://creator.xiaohongshu.com/new/home"
READY_MARKER = "READY_FOR_MANUAL_PUBLISH"
LOGIN_MARKER = "LOGIN_REQUIRED"


class XHSBrowserError(RuntimeError):
    """浏览器填充失败。"""


@dataclass(frozen=True)
class XHSBrowserConfig:
    profile_dir: str
    session: str = "xhs-promotion"
    cli: str = "npx --yes --package @playwright/cli playwright-cli"
    headed: bool = True
    timeout_seconds: int = 360

    @classmethod
    def from_env(cls, project_root: str | Path) -> "XHSBrowserConfig":
        root = Path(project_root)
        profile = os.environ.get("XHS_BROWSER_PROFILE", str(root / ".xhs-browser-profile"))
        cli = os.environ.get(
            "XHS_PLAYWRIGHT_CLI",
            "npx --yes --package @playwright/cli playwright-cli",
        )
        headed = os.environ.get("XHS_BROWSER_HEADED", "true").lower() not in {"0", "false", "no"}
        timeout = int(os.environ.get("XHS_BROWSER_TIMEOUT", "360"))
        return cls(
            profile_dir=profile,
            session=os.environ.get("XHS_BROWSER_SESSION", "xhs-promotion"),
            cli=cli,
            headed=headed,
            timeout_seconds=timeout,
        )


def browser_title(title: str) -> str:
    """去掉 LLM 标题中的 Markdown 标记，作为平台标题。"""
    return title.replace("**", "").replace("__", "").strip()


def _js_string(value: str) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def _fill_script(asset_dir: Path, title: str, caption: str) -> str:
    cover = (asset_dir / "cover.png").resolve()
    content = (asset_dir / "content.png").resolve()
    if not cover.is_file() or not content.is_file():
        raise XHSBrowserError(f"小红书发布包缺少图片：{asset_dir}")
    return f"""async (page) => {{
  await page.goto({_js_string(CREATOR_HOME)}, {{waitUntil: 'domcontentloaded'}});
  if (/\\/login/.test(page.url())) {{
    console.log({_js_string(LOGIN_MARKER)});
    await page.waitForURL(/\\/new\\/home/, {{timeout: 300000, waitUntil: 'domcontentloaded'}});
  }}
  const entry = page.getByText('发布图文笔记', {{exact: true}});
  if (await entry.count()) await entry.first().click();
  await page.locator('input[type="file"]').setInputFiles([
    {_js_string(str(cover))},
    {_js_string(str(content))}
  ]);
  await page.getByPlaceholder('填写标题会有更多赞哦').fill({_js_string(browser_title(title))});
  await page.locator('[contenteditable="true"]').first().fill({_js_string(caption)});
  console.log({_js_string(READY_MARKER)});
}}"""


class XHSBrowserPublisher:
    """通过 playwright-cli 填充内容，并停留在人工发布前。"""

    def __init__(self, config: XHSBrowserConfig):
        self.config = config

    def _command(self, *args: str) -> list[str]:
        return shlex.split(self.config.cli) + [f"-s={self.config.session}", *args]

    def _run(self, *args: str, timeout: int | None = None) -> str:
        try:
            completed = subprocess.run(
                self._command(*args),
                text=True,
                capture_output=True,
                timeout=timeout or self.config.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise XHSBrowserError(f"小红书浏览器命令执行失败：{exc}") from exc
        output = (completed.stdout or "") + (completed.stderr or "")
        if completed.returncode != 0:
            raise XHSBrowserError(output.strip() or f"playwright-cli 退出码 {completed.returncode}")
        return output

    def prepare(self, asset_dir: str, title: str, caption: str) -> str:
        """打开创作页、上传两张图片并填入文案，返回终端输出。"""
        profile = Path(self.config.profile_dir).expanduser()
        profile.mkdir(parents=True, exist_ok=True)
        open_args = ["open", CREATOR_HOME]
        if self.config.headed:
            open_args.append("--headed")
        open_args.extend(["--persistent", "--profile", str(profile)])
        self._run(*open_args)
        script = _fill_script(Path(asset_dir), title, caption)
        with tempfile.NamedTemporaryFile("w", suffix=".mjs", encoding="utf-8", delete=False) as handle:
            handle.write(script)
            script_path = handle.name
        try:
            output = self._run(
                "run-code", "--filename", script_path,
                timeout=self.config.timeout_seconds,
            )
        finally:
            Path(script_path).unlink(missing_ok=True)
        if READY_MARKER not in output:
            raise XHSBrowserError(output.strip() or "小红书页面未进入发布确认状态")
        return output
