"""闲鱼消息通道抽象：把"收发私信"与"业务逻辑"解耦。

- XianyuMessageChannel：通道接口（拉取/发送消息）。
- SimulatedChannel：内存模拟通道，现在就能跑，用于端到端验证 Agent/调度逻辑与跑测试。
- XianyuLiveChannel：真实通道骨架。闲鱼实时私信走逆向 WebSocket 协议
  （sign 签名我们已在 Phase 0 验证可用；完整收发需集成 cv-cat/XianYuApis），
  此处保留接入点：把 XianYuApis 的 WS 客户端塞进 connect()/iter_messages()/send() 即可。
"""
from __future__ import annotations

from collections.abc import Iterator

from .types import BuyerMessage


class XianyuMessageChannel:
    """通道接口。"""

    def iter_messages(self) -> Iterator[BuyerMessage]:
        raise NotImplementedError

    def send(self, conversation_id: str, text: str) -> bool:
        raise NotImplementedError


class SimulatedChannel(XianyuMessageChannel):
    """内存模拟通道：预置一批买家消息，发送的回复记录到 sent 便于断言/查看。"""

    def __init__(self, inbox: list[BuyerMessage] | None = None):
        self.inbox: list[BuyerMessage] = inbox or []
        self.sent: list[tuple[str, str]] = []  # (conversation_id, text)

    def push(self, msg: BuyerMessage) -> None:
        self.inbox.append(msg)

    def iter_messages(self) -> Iterator[BuyerMessage]:
        while self.inbox:
            yield self.inbox.pop(0)

    def send(self, conversation_id: str, text: str) -> bool:
        self.sent.append((conversation_id, text))
        return True


class XianyuLiveChannel(XianyuMessageChannel):
    """真实闲鱼通道（骨架）。Phase 1 下一步：集成 XianYuApis 的 WebSocket 客户端。

    Phase 0 已验证：用 _m_h5_tk 做 md5(token&t&appKey&data) 签名的 mtop 调用可成功，
    这是收发私信同款签名机制。实时收发需要：
      1. 建立 WS 连接（wss://wss-goofish... ），带 cookie 与握手包；
      2. 解析 Protobuf 同步包得到买家消息 -> 产出 BuyerMessage；
      3. send() 经 WS 下行发送回复。
    建议直接复用 cv-cat/XianYuApis 作为依赖，在此适配为本接口。
    """

    def __init__(self, cookie: str):
        self.cookie = cookie

    def iter_messages(self) -> Iterator[BuyerMessage]:  # pragma: no cover
        raise NotImplementedError("待集成 XianYuApis 的 WebSocket 收消息")

    def send(self, conversation_id: str, text: str) -> bool:  # pragma: no cover
        raise NotImplementedError("待集成 XianYuApis 的 WebSocket 发消息")
