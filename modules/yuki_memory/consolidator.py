import datetime
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from config import cfg
from modules.yuki_memory.models import MemoryRecord
from modules.yuki_memory.store import YukiMemoryStore
from utils.llm_client import chat_completion, llm_chat
from utils.logger import get_logger

logger = get_logger("yuki_memory_consolidator")

ALLOWED_CANDIDATE_TYPES = {"fact", "preference", "relationship", "todo", "event", "profile_candidate"}
TYPE_MAPPING = {
    "fact": "fact",
    "preference": "preference",
    "relationship": "relationship",
    "todo": "todo",
    "event": "event",
    "profile_candidate": "profile",
}

COARSE_SAMPLE_PROMPT = """你是 YukiV6 的对话粗筛器。请从输入对话中筛出值得进入长期整理的粗样本。

规则：
1. 只保留可能影响长期记忆、关系、偏好、项目进展、承诺待办、重要事件的信息。
2. 去掉无意义寒暄、重复表情、临时情绪、纯玩笑和无长期价值闲聊。
3. 不要编造，不要扩写。
4. 输出 JSON，不要解释。

输出格式：
{
  "samples": [
    {
      "speaker": "说话人或角色",
      "content": "保留下来的原始要点",
      "reason": "保留原因",
      "importance": 1
    }
  ]
}
"""

BUFFER_SUMMARY_PROMPT = """你是 YukiV6 的 buffer 总结器。请把输入粗样本压缩为一段稳定摘要。

规则：
1. 保留人物、关系、偏好、事实、计划、项目状态和重要事件。
2. 合并重复内容，去掉低价值临时事件。
3. 明确不确定性，不把玩笑当事实。
4. 输出 JSON，不要解释。

输出格式：
{
  "summary": "100-250字的 buffer 摘要",
  "key_points": ["要点1", "要点2"]
}
"""

STRUCTURED_MEMORY_PROMPT = """你是 YukiV6 的长期记忆提取器。请从多段 buffer 摘要中提取结构化记忆候选。

规则：
1. 只能提取摘要中明确表达的信息，禁止编造。
2. 玩笑、反讽、角色扮演、临时情绪不要抽成长期事实。
3. 不要做心理诊断，不要提取敏感隐私信息。
4. subject 不明确时不要提取。
5. evidence 必须引用摘要中的片段。
6. profile_candidate 只是画像候选，不代表可直接入库。
7. 宁可漏掉，不要误提取。
8. 输出 JSON，不要解释。

输出格式：
{
  "memories": [
    {
      "type": "fact|preference|relationship|todo|event|profile_candidate",
      "subject": "明确主体",
      "content": "一条独立、可检索、可更新的记忆",
      "confidence": 0.0,
      "importance": 1,
      "time_scope": "short_term|long_term|past|unknown",
      "evidence": "摘要原文片段",
      "risk": "low|medium|high"
    }
  ]
}
"""

DIARY_PROMPT = """你是 YukiV6 的日记整理器。请根据 buffer 摘要和结构化记忆候选，写一篇短日记。

规则：
1. 日记要保留当天/本段对话最重要的脉络，而不是流水账。
2. 重点写关系变化、长期偏好、项目进展、重要事件和待办。
3. 不要重复列所有细节。
4. 控制在 120-260 字。
5. 保持 Yuki 的可爱口吻，但不要过度撒娇。
6. 直接输出日记正文，不要解释。
"""


@dataclass
class ConsolidationConfig:
    """多层压缩整理参数。"""

    coarse_buffer_size: int = 24
    summary_buffer_size: int = 4
    summary_overlap: int = 1
    max_samples_per_buffer: int = 16
    min_candidate_confidence: float = 0.75
    import_profile: bool = False
    diary_importance: int = 3
    candidate_status: str = "active"
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None


@dataclass
class ConsolidationResult:
    """多层压缩整理结果。"""

    chat_id: str
    raw_count: int
    sample_count: int
    buffer_summaries: List[Dict[str, Any]] = field(default_factory=list)
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    diary: str = ""
    saved_ids: List[str] = field(default_factory=list)


class MultiLayerMemoryConsolidator:
    """多轮多层次压缩整理器。

    处理路径：原始对话 -> 粗样本 -> 重叠 buffer 摘要 -> 结构化候选 -> 短日记 -> YukiMemoryStore。
    """

    def __init__(self, store: Optional[YukiMemoryStore] = None, config: Optional[ConsolidationConfig] = None):
        self.store = store
        self.config = config or ConsolidationConfig()

    async def consolidate(self, chat_id, messages, save=False) -> ConsolidationResult:
        """执行一次多层压缩整理。"""
        normalized = self._normalize_messages(messages)
        result = ConsolidationResult(chat_id=str(chat_id), raw_count=len(normalized), sample_count=0)
        if not normalized:
            return result

        coarse_samples = await self._extract_coarse_samples(normalized)
        result.sample_count = len(coarse_samples)
        if not coarse_samples:
            return result

        result.buffer_summaries = await self._summarize_sample_buffers(coarse_samples)
        if not result.buffer_summaries:
            return result

        result.candidates = await self._extract_structured_candidates(result.buffer_summaries)
        result.diary = await self._write_diary(result.buffer_summaries, result.candidates)

        if save:
            result.saved_ids = self.save_result(result)
        return result

    def save_result(self, result: ConsolidationResult) -> List[str]:
        """将短日记与低风险结构化记忆保存到 YukiMemoryStore。"""
        if self.store is None:
            self.store = YukiMemoryStore()

        saved_ids = []
        now = datetime.datetime.now().timestamp()
        if result.diary.strip():
            diary_id = self._build_id("summary", result.chat_id, result.diary)
            record = MemoryRecord(
                memory_id=diary_id,
                type="summary",
                content=self._format_diary(result.diary),
                chat_id=result.chat_id,
                subject="群聊",
                source="multi_layer_consolidation",
                source_ids=[],
                importance=self.config.diary_importance,
                created_at=now,
                updated_at=now,
                metadata={
                    "raw_count": result.raw_count,
                    "sample_count": result.sample_count,
                    "buffer_count": len(result.buffer_summaries),
                    "consolidation_level": "diary",
                },
            )
            saved_ids.append(self.store.save(record))

        for index, candidate in enumerate(result.candidates):
            if not self._is_importable_candidate(candidate):
                continue
            memory_type = TYPE_MAPPING[candidate["type"]]
            memory_id = self._build_id(memory_type, result.chat_id, candidate["content"])
            record = MemoryRecord(
                memory_id=memory_id,
                type=memory_type,
                content=candidate["content"],
                chat_id=result.chat_id,
                subject=candidate.get("subject"),
                status=self.config.candidate_status,
                confidence=candidate.get("confidence", 1.0),
                importance=candidate.get("importance", 3),
                source="multi_layer_consolidation",
                source_ids=[f"runtime_candidate_{index}"],
                created_at=now,
                updated_at=now,
                metadata={
                    "candidate_type": candidate["type"],
                    "time_scope": candidate.get("time_scope", "unknown"),
                    "evidence": candidate.get("evidence", ""),
                    "risk": candidate.get("risk", "medium"),
                    "consolidation_level": "structured",
                },
            )
            saved_ids.append(self.store.save(record))
        return saved_ids

    async def _extract_coarse_samples(self, messages):
        samples = []
        for buffer in self._chunk_with_overlap(messages, self.config.coarse_buffer_size, 0):
            payload = json.dumps(buffer, ensure_ascii=False)
            parsed = await self._json_chat(COARSE_SAMPLE_PROMPT, payload, max_tokens=900)
            for sample in parsed.get("samples", [])[: self.config.max_samples_per_buffer]:
                normalized = self._sanitize_sample(sample)
                if normalized:
                    samples.append(normalized)
        return samples

    async def _summarize_sample_buffers(self, samples):
        summaries = []
        buffers = self._chunk_with_overlap(
            samples,
            self.config.summary_buffer_size,
            self.config.summary_overlap,
        )
        for index, buffer in enumerate(buffers):
            payload = json.dumps(buffer, ensure_ascii=False)
            parsed = await self._json_chat(BUFFER_SUMMARY_PROMPT, payload, max_tokens=700)
            summary = str(parsed.get("summary", "")).strip()
            if not summary:
                continue
            summaries.append({
                "index": index,
                "summary": summary,
                "key_points": [str(item).strip() for item in parsed.get("key_points", []) if str(item).strip()],
            })
        return summaries

    async def _extract_structured_candidates(self, buffer_summaries):
        payload = json.dumps(buffer_summaries, ensure_ascii=False)
        parsed = await self._json_chat(STRUCTURED_MEMORY_PROMPT, payload, max_tokens=1200)
        candidates = []
        for candidate in parsed.get("memories", []):
            normalized = self._sanitize_candidate(candidate)
            if normalized:
                candidates.append(normalized)
        return candidates

    async def _write_diary(self, buffer_summaries, candidates):
        payload = json.dumps({
            "buffer_summaries": buffer_summaries,
            "structured_candidates": candidates,
        }, ensure_ascii=False)
        diary = await self._llm_chat(
            messages=[
                {"role": "system", "content": DIARY_PROMPT},
                {"role": "user", "content": payload},
            ],
            temperature=0.6,
            top_p=0.8,
            max_tokens=360,
        )
        diary = re.sub(r"\s*FINISHED\s*$", "", diary, flags=re.IGNORECASE).strip()
        if diary:
            return diary
        return self._build_fallback_diary(buffer_summaries, candidates)

    @staticmethod
    def _build_fallback_diary(buffer_summaries, candidates):
        summary_parts = [str(item.get("summary", "")).strip() for item in buffer_summaries]
        summary_parts = [item for item in summary_parts if item]
        if summary_parts:
            base = "；".join(summary_parts[:2])
        else:
            base = "这段对话里没有太多需要长期沉淀的内容。"
        important = [item.get("content", "") for item in candidates if int(item.get("importance", 1) or 1) >= 3]
        if important:
            base = f"{base} 其中比较重要的是：{'；'.join(important[:3])}。"
        return base[:260]

    async def _json_chat(self, system_prompt, user_payload, max_tokens):
        raw_text = await self._llm_chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_payload},
            ],
            temperature=0.2,
            top_p=0.8,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        return self._parse_json(raw_text)

    async def _llm_chat(self, messages, **kwargs):
        if self.config.llm_base_url and self.config.llm_api_key:
            return await chat_completion(
                self.config.llm_base_url,
                self.config.llm_api_key,
                messages,
                model=self.config.llm_model or cfg.LLM_MODEL,
                timeout=120.0,
                **kwargs,
            )
        return await llm_chat(messages=messages, model=self.config.llm_model or cfg.LLM_MODEL, **kwargs)

    @staticmethod
    def _parse_json(raw_text):
        text = str(raw_text or "").strip()
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end >= start:
            text = text[start:end + 1]
        return json.loads(text)

    @staticmethod
    def _normalize_messages(messages):
        normalized = []
        for msg in messages:
            if not isinstance(msg, dict) or msg.get("role") == "system":
                continue
            content = str(msg.get("content", "")).strip()
            if not content:
                continue
            normalized.append({
                "role": str(msg.get("role", "user")),
                "time": str(msg.get("time", "")),
                "content": content,
            })
        return normalized

    @staticmethod
    def _chunk_with_overlap(items, size, overlap):
        if not items:
            return []
        size = max(1, int(size or 1))
        overlap = max(0, min(int(overlap or 0), size - 1))
        step = size - overlap
        return [items[index:index + size] for index in range(0, len(items), step)]

    @staticmethod
    def _sanitize_sample(sample):
        content = str(sample.get("content", "")).strip()
        if not content:
            return None
        try:
            importance = int(sample.get("importance", 1) or 1)
        except (TypeError, ValueError):
            importance = 1
        return {
            "speaker": str(sample.get("speaker", "未知")).strip() or "未知",
            "content": content,
            "reason": str(sample.get("reason", "")).strip(),
            "importance": max(1, min(5, importance)),
        }

    @staticmethod
    def _sanitize_candidate(candidate):
        candidate_type = candidate.get("type")
        if candidate_type not in ALLOWED_CANDIDATE_TYPES:
            return None
        content = str(candidate.get("content", "")).strip()
        subject = str(candidate.get("subject", "")).strip()
        evidence = str(candidate.get("evidence", "")).strip()
        if not content or not subject or not evidence:
            return None
        try:
            confidence = float(candidate.get("confidence", 0) or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        try:
            importance = int(candidate.get("importance", 1) or 1)
        except (TypeError, ValueError):
            importance = 1
        return {
            "type": candidate_type,
            "subject": subject,
            "content": content,
            "confidence": max(0.0, min(1.0, confidence)),
            "importance": max(1, min(5, importance)),
            "time_scope": str(candidate.get("time_scope", "unknown")),
            "evidence": evidence,
            "risk": str(candidate.get("risk", "medium")),
        }

    def _is_importable_candidate(self, candidate):
        if candidate.get("risk") != "low":
            return False
        if float(candidate.get("confidence", 0) or 0) < self.config.min_candidate_confidence:
            return False
        if candidate.get("type") == "profile_candidate" and not self.config.import_profile:
            return False
        if candidate.get("type") == "event" and int(candidate.get("importance", 1) or 1) < 3:
            return False
        if int(candidate.get("importance", 1) or 1) < 2:
            return False
        return candidate.get("type") in TYPE_MAPPING

    @staticmethod
    def _format_diary(diary):
        if diary.startswith("【日记"):
            return diary
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        return f"【日记({timestamp})】：\n{diary}"

    @staticmethod
    def _build_id(memory_type, chat_id, content):
        digest = hashlib.sha1(f"{chat_id}|{memory_type}|{content}".encode("utf-8")).hexdigest()[:16]
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"ymem_{memory_type}_{chat_id}_{timestamp}_{digest}"
