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
    """构造标准小女仆回调报告。"""
    status = result_dict.get("status", "unknown")
    result = result_dict.get("result", "未知结果")
    return f"【小女仆完成! 小女仆汇报】\n任务：「{goal}」\n状态：{status}\n结果：{result}"
