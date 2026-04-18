import re
from config import MAX_MESSAGE_LENGTH
from utils.logger import get_logger

logger = get_logger("cq_protocol")

def smart_truncate(content, max_len = MAX_MESSAGE_LENGTH, suffix="..."):
    """
    保留原有调试好的逻辑：智能截断超长消息并保留CQ码完整性
    """
    # 如果没超过长度，直接原样返回，不做任何处理
    if len(content) <= max_len:
        return content

    # --- 以下是你调试好的原始算法逻辑，完全不动 ---
    logger.info(f"[System] 检测到超长消息 ({len(content)} 字符)")
    parts = re.split(r'(\[CQ:.*?\])', content)
    result = []

    for part in parts:
        if not part:
            continue

        if part.startswith('[CQ:') and part.endswith(']'):
            result.append(part)

        else:
            if len(part) > 100:
                half = 40
                part = part[:half] + suffix + part[-half:]
            result.append(part)

    content = ''.join(result)
    logger.info(f"[System] 压缩后长度: {len(content)} 字符")

    return content


class CQProtocol:
    """纯粹的翻译官：只管文本替换，不碰网络"""

    @staticmethod
    def replace_other_CQ_codes(text: str) -> str:
        """把所有多媒体码换成占位符"""
        text = re.sub(r'\[CQ:image[^\]]*\]', '[图片]', text)
        text = re.sub(r'\[CQ:face[^\]]*\]', '[表情]', text)
        text = re.sub(r'\[CQ:record[^\]]*\]', '[语音]', text)
        text = re.sub(r'\[CQ:video[^\]]*\]', '[视频]', text)
        text = re.sub(r'\[CQ:file[^\]]*\]', '[文件]', text)
        text = re.sub(r'\[CQ:json[^\]]*\]', '[小程序]', text)
        return text

    @staticmethod
    def is_at_me(text: str, self_id: str) -> bool:
        return f"[CQ:at,qq={self_id}]" in text

    @staticmethod
    def extract_at_uids(text: str):
        """只负责把文本里的 QQ 号都找出来，不查名字"""
        return re.findall(r'\[CQ:at,qq=(\d+|all)\]', text)

    @staticmethod
    def extract_reply_matches(text: str):
        return re.findall(r'\[CQ:reply,id=(\d+)\]', text)

    @staticmethod
    def replace_at_placeholder(text, qq, nickname):
        """只负责把特定的 CQ 码换成名字"""
        pattern = rf'\[CQ:at,qq={qq}[^\]]*\]'
        text = re.sub(pattern, f"@{nickname}", text)
        return text
    @staticmethod
    def replace_reply_placeholder(data) -> str:
        if not data:
            logger.error("[CQProtocol] 引用历史回复消息错误")
            return "【引用不明历史消息】"
        sender = data.get("sender", {}).get("nickname", "人")
        text = re.sub(r'\[CQ:.*?\]', '', data.get("raw_message", ""))
        text = smart_truncate(text)
        return f"【引用{sender}的消息: {text}】"
