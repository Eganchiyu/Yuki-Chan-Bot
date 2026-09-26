# core/engine_decision.py
from config import cfg
from utils.logger import get_logger

logger = get_logger("engine")


class EngineDecisionService:
    """负责群聊回复意愿判定。"""

    def __init__(self, yuki):
        self.yuki = yuki

    async def decide_to_reply(self, history, message_objs, chat_id, force_reply=False, rag_interest=0.0):
        """
        [精力核心融合版] 混合硬性规则与加权积分引擎
        以精力值为基底，削弱话题惯性，维持中等主人依赖。
        """
        cid = str(chat_id)

        current_e = self.yuki.update_energy(chat_id)
        self.yuki.update_desire_to_reply(chat_id)
        desire = self.yuki.desire_to_start_topic.get(cid, 0)

        if not hasattr(self.yuki, 'topic_hormone'):
            self.yuki.topic_hormone = {}

        current_hormone = self.yuki.topic_hormone.get(cid, 0.0)
        new_hormone = current_hormone * 0.60 + (rag_interest * 10)
        new_hormone = min(new_hormone, 100.0)
        self.yuki.topic_hormone[cid] = new_hormone

        human_calling = False
        bot_calling_only = True
        question_mark = False
        is_master = False

        master_identifiers = [cfg.MASTER_NAME, "池宇健"]
        master_qq_str = str(cfg.TARGET_QQ)

        for m in message_objs:
            raw_text = m.get("raw_text", "").lower()
            if not m.get("is_bot"):
                bot_calling_only = False

            if any(kw in raw_text for kw in cfg.keywords):
                if not m.get("is_bot"):
                    human_calling = True

            if any(q in raw_text for q in ["?", "？", "吗", "呢", "怎么", "什么", "谁", "为什么"]):
                question_mark = True

            if (
                any(mid in raw_text for mid in master_identifiers)
                or master_qq_str in raw_text
                or m.get("user_id") == cfg.TARGET_QQ
            ):
                is_master = True

        if force_reply or human_calling:
            logger.info(f"[Decision] 触发强制回复或直接召唤，立即响应")
            return True

        if bot_calling_only and any(any(kw in m["raw_text"].lower() for kw in cfg.keywords) for m in message_objs):
            self.yuki.desire_to_start_topic[cid] *= 0.8
            logger.info(f"[Decision] 防套娃机制触发：纯 BOT 召唤，静默")
            # return False

        if current_e >= 85:
            logger.info(f"[Decision] 精力充沛({current_e:.1f})，强制开启活跃模式")
            return True

        if current_e < cfg.MIN_ACTIVE_ENERGY and not is_master:
            logger.info(f"[Decision] 精力枯竭({current_e:.1f})且无哥哥大人在场，拒绝回复")
            return False

        reply_score = 0.0
        reply_score += current_e * 0.4
        reply_score += desire * 0.2
        reply_score += new_hormone * 0.2

        if question_mark:
            reply_score += 10

        if is_master:
            reply_score += 20
            logger.debug(f"[Decision] 检测到哥哥大人发言，触发中等依赖修正 +15")

        threshold = 55.0
        will_reply = reply_score >= threshold

        logger.info(
            f"[Decision] 模糊地带 {reply_score:.1f}/{threshold:.0f} -> 发言:{will_reply}"
            f" (精力{current_e:.1f} 激素{new_hormone:.1f} 欲{desire:.1f} 主人:{is_master})"
        )
        logger.debug(
            f"[Decision] 模糊地带明细 | 精力:{current_e:.1f} 激素:{new_hormone:.1f} 欲:{desire:.1f} "
            f"主人:{is_master} | 总分:{reply_score:.1f}/{threshold} -> 发言:{will_reply}"
        )
        return will_reply
