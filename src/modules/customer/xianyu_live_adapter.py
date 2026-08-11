"""把 XianYuApis 的 XianyuLive 与我们的 Agent 桥接起来（按其真实 API 对齐）。

XianYuApis 真实结构（vendor/XianYuApis/goofish_live.py）：
  class XianyuLive(cookies_str):
      async def main()                     # 常驻：连 WS、init、心跳、收消息
      async def handle_message(message, ws)# 每条消息：解密 -> 取 send_user_name/id、send_message、cid
                                           #   原版是硬编码回显，这里改为走我们的 bridge
      async def send_msg(ws, cid, toid, message)  # 发送（make_text 构造文本消息）

集成策略：子类化 XianyuLive，仅重写 handle_message 的"决定回什么"部分，
复用其解密/WS/发送能力。XianYuApis 不可导入时本模块的 build_agent_live 抛 ImportError，
由运行器捕获并给安装指引。
"""
from __future__ import annotations

import json
import os

from pathlib import Path

from ...config import config
from .xianyu_live import XianyuLiveBridge

# 设为 1 时打印解密后的完整消息结构（调试用）。结构已摸清，默认关闭。
_DEBUG_DUMP = os.environ.get("XIANYU_DEBUG_DUMP", "0") == "1"


def _load_item_floors() -> dict:
    """读取每件商品的议价下限配置 data/item_floors.json: {item_id: 最低成交价}。"""
    p = Path(config.PROJECT_ROOT) / "data" / "item_floors.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


_ITEM_FLOORS = _load_item_floors()


def stable_device_id(unb: str, gen) -> str:
    """每个账号固定一个 device_id（首次用 gen 生成后落盘，之后复用）。

    XianYuApis 的 generate_device_id 每次随机，会让闲鱼看到"同账号频繁换设备"而触发风控。
    固定下来伪装成同一台设备，是降低风控最关键的一步。
    """
    p = Path(config.PROJECT_ROOT) / "data" / "device_ids.json"
    store = {}
    if p.exists():
        try:
            store = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            store = {}
    if unb in store:
        return store[unb]
    did = gen(unb)
    store[unb] = did
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    return did


# ---- 纯函数：消息解析/过滤/取itemId（可离线用真实消息回放测试，不依赖网络/XianYuApis）----

def find_item_id(m: dict) -> str:
    """从解密消息里取 item_id。实测在 reminderUrl 的 itemId= 参数里。"""
    try:
        ext = m["1"]["10"]
    except Exception:  # noqa: BLE001
        return ""
    for key in ("reminderUrl", "reminderNotice", "bizTag"):
        val = str(ext.get(key, ""))
        if "itemId=" in val:
            return val.split("itemId=")[1].split("&")[0]
        if "item_id=" in val:
            return val.split("item_id=")[1].split("&")[0]
    return ""


def find_peer_id(m: dict) -> str:
    """从 reminderUrl 取 peerUserId（系统订单消息里"对方=买家"的 id），用于付款后回复。"""
    try:
        ext = m["1"]["10"]
    except Exception:  # noqa: BLE001
        return ""
    val = str(ext.get("reminderUrl", ""))
    if "peerUserId=" in val:
        return val.split("peerUserId=")[1].split("&")[0]
    return ""


# 订单状态系统消息识别关键词。「已付款」属系统消息(contentType!=1)，会被 parse_buyer_message
# 过滤，故单独识别以驱动发货。字段路径(reminderContent/bizTag)是基于已摸清的文本消息结构的
# 最佳推断；真机抓到「已付款」系统消息后用 XIANYU_DEBUG_DUMP=1 核对实际位置再微调即可。
_ORDER_PAID_KW = ("已付款", "买家已付款", "等待发货", "等待您发货", "待发货", "付款成功", "交易成功")
_ORDER_SHIPPED_KW = ("已发货", "卖家已发货", "等待确认收货", "等待收货")
_ORDER_CLOSED_KW = ("交易关闭", "已退款", "退款成功", "退款完成")
# 明确"尚未付款"，优先排除，避免把待付款误判为已付款（安全）
_ORDER_UNPAID_KW = ("等待买家付款", "等待付款", "买家未付款", "待付款")


def parse_order_event(m: dict) -> dict | None:
    """识别订单状态系统消息，返回 {event, conversation_id, item_id, buyer_id, text}；非订单事件 None。

    event ∈ {"paid","shipped","closed"}；仅 "paid" 用于触发发货。结构不符/无关键词 -> None，
    届时 paid 维持 False、走人工发货（安全降级）。
    """
    try:
        ext = m["1"]["10"]
        cid = m["1"]["2"].split("@")[0]
    except Exception:  # noqa: BLE001
        return None
    blob = " ".join(
        str(ext.get(k, "")) for k in
        ("reminderContent", "reminderTitle", "reminderNotice", "redReminder", "bizTag")
    )
    if not blob.strip():
        return None
    if any(k in blob for k in _ORDER_UNPAID_KW):
        return None  # 尚未付款，绝不触发发货
    if any(k in blob for k in _ORDER_PAID_KW):
        event = "paid"
    elif any(k in blob for k in _ORDER_SHIPPED_KW):
        event = "shipped"
    elif any(k in blob for k in _ORDER_CLOSED_KW):
        event = "closed"
    else:
        return None
    return {
        "event": event,
        "conversation_id": cid,
        "item_id": find_item_id(m),
        "buyer_id": find_peer_id(m),
        "text": str(ext.get("reminderContent", "")).strip(),
    }


def parse_buyer_message(m: dict, myid: str | None = None) -> dict | None:
    """把解密消息解析为 raw dict；若非"买家发来的真实文本"则返回 None（过滤）。

    过滤掉：已读回执/系统同步包（结构对不上）、系统安全提示(contentType=14 / bizTag含SECURITY)、
    自己发出的消息(myid)。实测字段：
      文本    m["1"]["10"]["reminderContent"]
      昵称    m["1"]["10"]["reminderTitle"]
      买家id  m["1"]["10"]["senderUserId"]
      会话id  m["1"]["2"]（去掉 @goofish）
      子类型  m["1"]["6"]["3"]["4"]（1=文本）
    """
    try:
        ext = m["1"]["10"]
        send_user_name = ext["reminderTitle"]
        send_user_id = ext["senderUserId"]
        send_message = ext["reminderContent"]
        cid = m["1"]["2"].split("@")[0]
        content_subtype = m["1"]["6"]["3"]["4"]
    except Exception:  # noqa: BLE001
        return None
    if content_subtype != 1:
        return None
    if "SECURITY" in str(ext.get("bizTag", "")):
        return None
    if myid is not None and str(send_user_id) == str(myid):
        return None
    return {
        "conversation_id": cid,
        "buyer_id": send_user_id,
        "buyer_name": send_user_name,
        "text": send_message,
    }


def build_agent_live(cookies_str: str, bridge: XianyuLiveBridge):
    """惰性导入 XianYuApis，返回一个已接入 Agent 的 XianyuLive 实例。"""
    # 这些 import 依赖 vendor/XianYuApis 已在 sys.path 中（由运行器负责加入）
    import asyncio
    import random

    from goofish_live import XianyuLive  # type: ignore
    from goofish_apis import XianyuApis  # type: ignore
    from message import make_text  # type: ignore
    from utils.goofish_utils import decrypt, generate_device_id  # type: ignore
    from loguru import logger  # type: ignore

    class AgentXianyuLive(XianyuLive):
        def __init__(self, cookies):
            super().__init__(cookies)
            # 关键：用固定 device_id 覆盖随机的，并据此重建 xianyu 客户端（降低风控）
            self.device_id = stable_device_id(self.myid, generate_device_id)
            self.xianyu = XianyuApis(self.cookies, self.device_id)
            logger.info(f"使用固定 device_id: {self.device_id}")
            self.bridge = bridge

        async def handle_message(self, message, websocket):
            try:
                data = message["body"]["syncPushPackage"]["data"][0]["data"]
                decoded = decrypt(data)
                m = json.loads(decoded)
            except Exception:
                return  # 非聊天/无法解密的同步包，跳过
            if _DEBUG_DUMP:
                logger.info("=== 解密消息原始结构 ===\n"
                            + json.dumps(m, ensure_ascii=False, indent=2))

            raw = parse_buyer_message(m, myid=self.myid)
            if raw is None:
                # 非买家文本：可能是订单状态系统消息（如"已付款"），单独识别以驱动发货
                await self._handle_order_event(m, websocket)
                return  # 其余系统消息/非文本/自己发的，已过滤

            logger.info(f"收到买家[{raw['buyer_name']}]消息: {raw['text']}")
            # 补全商品上下文（item_id 在消息里则反查价格/标题，供议价与发货判断）
            self._enrich_item(m, raw)

            reply = self.bridge.handle_raw(raw)   # DRY-RUN 返回 None；LIVE 返回回复文本
            if reply:
                # 拟人延迟：模拟"读消息+打字"，消除秒回的机器人特征
                delay = random.uniform(config.REPLY_DELAY_MIN, config.REPLY_DELAY_MAX)
                logger.info(f"拟人延迟 {delay:.1f}s 后回复…")
                await asyncio.sleep(delay)
                await self.send_msg(websocket, raw["conversation_id"],
                                    raw["buyer_id"], make_text(reply))
                logger.info(f"已回复[{raw['buyer_name']}]: {reply}")

        async def _handle_order_event(self, m: dict, websocket) -> None:
            """处理订单状态系统消息：仅"已付款"触发发货流程（建工单 + 确认话术）。

            is_virtual 无法从消息可靠判断，默认按实物走人工发货工单（安全）；
            如需虚拟品自动发货，可在此按 item_id 查本地虚拟品配置再传 is_virtual=True。
            """
            event = parse_order_event(m)
            if not event or event["event"] != "paid":
                return
            logger.info(f"订单事件[已付款] item={event['item_id']} cid={event['conversation_id']}")
            reply = self.bridge.handle_paid_event(
                conversation_id=event["conversation_id"],
                buyer_id=event["buyer_id"],
                item_id=event["item_id"],
            )
            if reply and event["buyer_id"]:
                delay = random.uniform(config.REPLY_DELAY_MIN, config.REPLY_DELAY_MAX)
                await asyncio.sleep(delay)
                await self.send_msg(websocket, event["conversation_id"],
                                    event["buyer_id"], make_text(reply))
                logger.info(f"已付款确认已回复: {reply}")

        def _enrich_item(self, m: dict, raw: dict) -> None:
            """找到 item_id 则反查商品详情，补全 item_title/item_price，并按本地配置补 floor_price。

            真实字段（实测 mtop.taobao.idle.pc.detail）：
              data.itemDO.title       商品标题
              data.itemDO.soldPrice   一口价（元，字符串）；'99999999' 或 defaultPrice=True 表示"价格私聊"
              data.itemDO.desc        描述
            议价下限 floor_price 闲鱼不提供（属卖家私有），从本地 data/item_floors.json 读取
            （{item_id: 最低可成交价}）；未配置则不让价（安全）。
            """
            item_id = find_item_id(m)
            if not item_id:
                return
            raw["item_id"] = item_id
            try:
                info = self.xianyu.get_item_info(item_id)
                item = (info.get("data", {}) if isinstance(info, dict) else {}).get("itemDO", {})
                title = item.get("title") or ""
                if title:
                    raw["item_title"] = title
                # 价格：占位/价格私聊 -> 视为无价（不参与议价）
                if not item.get("defaultPrice") and str(item.get("soldPrice")) not in ("", "99999999"):
                    try:
                        raw["item_price"] = float(item["soldPrice"])
                    except (TypeError, ValueError):
                        pass
                # 议价下限：本地配置
                floor = _ITEM_FLOORS.get(str(item_id))
                if floor is not None:
                    raw["floor_price"] = float(floor)
                logger.info(f"商品上下文: 《{title}》 价={raw.get('item_price',0)} 底价={raw.get('floor_price',0)}")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"反查商品 {item_id} 失败（不影响回复）：{e}")

    return AgentXianyuLive(cookies_str)
