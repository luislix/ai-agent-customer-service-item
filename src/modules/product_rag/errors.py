class ProductSnapshotValidationError(ValueError):
    """商品快照不符合外部输入契约。"""


class ProductRagUnavailable(RuntimeError):
    """生产 RAG 依赖暂不可用。"""
