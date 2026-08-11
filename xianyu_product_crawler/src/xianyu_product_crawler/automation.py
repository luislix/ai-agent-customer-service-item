"""单机、串行的 Chrome 扩展自动采集任务状态。"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TERMINAL_STATES = {"completed", "failed", "blocked", "cancelled"}


@dataclass
class AutomationTask:
    id: str
    keyword: str
    search_url: str
    output_dir: str
    max_items: int
    delay_seconds: float
    state: str = "queued"
    message: str = "等待 Chrome 扩展领取任务"
    discovered: int = 0
    collected: int = 0
    failed: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "keyword": self.keyword,
            "search_url": self.search_url,
            "output_dir": self.output_dir,
            "max_items": self.max_items,
            "delay_seconds": self.delay_seconds,
            "state": self.state,
            "message": self.message,
            "discovered": self.discovered,
            "collected": self.collected,
            "failed": self.failed,
            "events": list(self.events[-50:]),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class AutomationTaskStore:
    """本机任务队列；同一时间只允许一个非终态任务。"""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._tasks: dict[str, AutomationTask] = {}
        self._queue: list[str] = []

    def create(
        self,
        keyword: str,
        *,
        search_url: str,
        output_dir: str | Path,
        max_items: int = 20,
        delay_seconds: float = 2.0,
    ) -> AutomationTask:
        keyword = str(keyword or "").strip()
        if not keyword:
            raise ValueError("关键词不能为空")
        if not search_url.startswith(("http://", "https://")):
            raise ValueError("搜索地址必须是 http/https URL")
        if max_items < 1:
            raise ValueError("max_items 必须大于 0")
        if delay_seconds < 0:
            raise ValueError("delay_seconds 不能小于 0")
        with self._condition:
            if any(task.state not in TERMINAL_STATES for task in self._tasks.values()):
                raise RuntimeError("已有采集任务运行中，请等待任务完成")
            task = AutomationTask(
                id=uuid.uuid4().hex[:12],
                keyword=keyword,
                search_url=search_url,
                output_dir=str(Path(output_dir)),
                max_items=max_items,
                delay_seconds=delay_seconds,
            )
            self._tasks[task.id] = task
            self._queue.append(task.id)
            self._condition.notify_all()
            return task

    def claim_next(self) -> AutomationTask | None:
        with self._condition:
            while self._queue:
                task = self._tasks[self._queue.pop(0)]
                if task.state != "queued":
                    continue
                self._update(task, "running", "Chrome 扩展已领取任务")
                return task
        return None

    def get(self, task_id: str) -> AutomationTask | None:
        with self._condition:
            return self._tasks.get(task_id)

    def record_event(self, task_id: str, payload: dict[str, Any]) -> AutomationTask:
        with self._condition:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError("任务不存在")
            state = str(payload.get("state") or "").strip()
            if state and state not in {"running", *TERMINAL_STATES}:
                raise ValueError("任务状态非法")
            if task.state in TERMINAL_STATES and state and state != task.state:
                raise ValueError("终态任务不能回退")
            if state:
                task.state = state
            message = payload.get("message")
            if message is not None:
                task.message = str(message)[:500]
            for field_name in ("discovered", "collected", "failed"):
                if field_name in payload:
                    value = payload[field_name]
                    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                        raise ValueError(f"{field_name} 必须是非负整数")
                    setattr(task, field_name, value)
            event = {"at": datetime.now(timezone.utc).isoformat(), **payload}
            task.events.append(event)
            task.updated_at = event["at"]
            self._condition.notify_all()
            return task

    def wait(self, task_id: str, timeout: float | None = None) -> AutomationTask:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError("任务不存在")
            while task.state not in TERMINAL_STATES:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    raise TimeoutError("采集任务等待超时")
                self._condition.wait(remaining)
            return task

    @staticmethod
    def _update(task: AutomationTask, state: str, message: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        task.state = state
        task.message = message
        task.updated_at = now
        task.events.append({"at": now, "state": state, "message": message})
