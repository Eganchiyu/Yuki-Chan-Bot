from datetime import datetime


class MaidCapabilityBoundary:
    """小女仆能力边界判定，避免把明显不合适的任务交给后台执行。"""

    BLOCKED_KEYWORDS = ["转账", "支付", "删除系统", "格式化", "破解", "盗号"]
    HIGH_COST_KEYWORDS = ["训练模型", "大型项目重写", "全网爬取", "无限", "长期监控"]

    @classmethod
    def judge(cls, goal: str) -> dict:
        text = goal or ""
        if not text.strip():
            return {"allowed": False, "reason": "任务目标为空", "suggestion": "请补充明确的任务目标。"}
        if any(keyword in text for keyword in cls.BLOCKED_KEYWORDS):
            return {"allowed": False, "reason": "任务涉及高风险操作", "suggestion": "可以改为提供安全的操作说明或风险分析。"}
        if any(keyword in text for keyword in cls.HIGH_COST_KEYWORDS):
            return {"allowed": False, "reason": "任务实现成本过高", "suggestion": "建议拆分为更小的阶段性任务。"}
        return {"allowed": True, "reason": "任务在小女仆可处理范围内", "suggestion": ""}


def build_maid_task(goal: str, chat_id: str = None, mode: str = "group", source: str = "yuki") -> dict:
    """构造标准小女仆任务，供工具链和标签委托共用。"""
    return {
        "goal": goal,
        "chat_id": str(chat_id) if chat_id is not None else None,
        "mode": mode,
        "source": source,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def build_maid_report(goal: str, result_dict: dict) -> str:
    """构造标准小女仆回调报告。前缀格式固定，附加信息统一追加在末尾。"""
    status = result_dict.get("status", "unknown")
    result = result_dict.get("result", "未知结果")
    lines = [
        "【小女仆完成! 小女仆汇报】",
        f"任务：「{goal}」",
        f"状态：{status}",
        f"结果：{result}",
    ]

    meta = []
    if result_dict.get("rounds") is not None:
        meta.append(f"轮次：{result_dict['rounds']}")
    if result_dict.get("elapsed") is not None:
        meta.append(f"耗时：{result_dict['elapsed']}s")
    if result_dict.get("trace"):
        meta.append(f"trace：{result_dict['trace']}")
    if result_dict.get("state"):
        meta.append(f"快照：{result_dict['state']}")
    if meta:
        lines.append(" | ".join(meta))

    return "\n".join(lines)
