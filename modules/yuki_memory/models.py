import datetime
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


MEMORY_TYPES = {
    "raw",
    "summary",
    "fact",
    "preference",
    "profile",
    "relationship",
    "todo",
    "event",
    "snapshot",
}

MEMORY_STATUSES = {
    "active",
    "candidate",
    "superseded",
    "archived",
    "rejected",
}

MetadataValue = Union[str, int, float, bool]


@dataclass
class MemoryRecord:
    """Yuki-Memory 标准记忆记录。"""

    memory_id: str
    type: str
    content: str
    scope: str = "group"
    chat_id: Optional[str] = None
    subject: Optional[str] = None
    status: str = "active"
    confidence: float = 1.0
    importance: int = 3
    source: str = "unknown"
    source_ids: List[str] = field(default_factory=list)
    supersedes: Optional[str] = None
    created_at: Optional[float] = None
    updated_at: Optional[float] = None
    access_count: int = 0
    last_accessed: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.type not in MEMORY_TYPES:
            raise ValueError(f"不支持的记忆类型: {self.type}")
        if self.status not in MEMORY_STATUSES:
            raise ValueError(f"不支持的记忆状态: {self.status}")
        if not self.content or not self.content.strip():
            raise ValueError("记忆内容不能为空")

        now = datetime.datetime.now().timestamp()
        self.memory_id = str(self.memory_id)
        self.content = self.content.strip()
        self.scope = str(self.scope or "group")
        self.chat_id = str(self.chat_id) if self.chat_id is not None else None
        self.subject = str(self.subject) if self.subject is not None else None
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        self.importance = max(1, min(5, int(self.importance)))
        self.source = str(self.source or "unknown")
        self.source_ids = [str(source_id) for source_id in self.source_ids]
        self.supersedes = str(self.supersedes) if self.supersedes else None
        self.created_at = float(self.created_at) if self.created_at is not None else now
        self.updated_at = float(self.updated_at) if self.updated_at is not None else self.created_at
        self.access_count = int(self.access_count or 0)
        self.last_accessed = float(self.last_accessed) if self.last_accessed is not None else 0.0

    def to_metadata(self) -> Dict[str, MetadataValue]:
        """转换为 Chroma 支持的 metadata。"""
        metadata = {
            "type": self.type,
            "scope": self.scope,
            "chat_id": self.chat_id or "",
            "subject": self.subject or "",
            "status": self.status,
            "confidence": self.confidence,
            "importance": self.importance,
            "source": self.source,
            "source_ids": json.dumps(self.source_ids, ensure_ascii=False),
            "supersedes": self.supersedes or "",
            "created_at": self.created_at or 0.0,
            "updated_at": self.updated_at or 0.0,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed or 0.0,
        }

        for key, value in self.metadata.items():
            if value is None or key in metadata:
                continue
            if isinstance(value, (str, int, float, bool)):
                metadata[key] = value
            else:
                metadata[key] = json.dumps(value, ensure_ascii=False)
        return metadata

    @classmethod
    def from_chroma(cls, memory_id: str, content: str, metadata: Optional[Dict[str, Any]]):
        """从 Chroma 记录还原 MemoryRecord。"""
        metadata = metadata or {}
        source_ids = metadata.get("source_ids") or "[]"
        if isinstance(source_ids, str):
            try:
                source_ids = json.loads(source_ids)
            except json.JSONDecodeError:
                source_ids = [source_ids]

        known_keys = {
            "type", "scope", "chat_id", "subject", "status", "confidence", "importance",
            "source", "source_ids", "supersedes", "created_at", "updated_at",
            "access_count", "last_accessed",
        }
        extra_metadata = {key: value for key, value in metadata.items() if key not in known_keys}

        return cls(
            memory_id=memory_id,
            type=metadata.get("type", "summary"),
            content=content,
            scope=metadata.get("scope", "group"),
            chat_id=metadata.get("chat_id") or None,
            subject=metadata.get("subject") or None,
            status=metadata.get("status", "active"),
            confidence=metadata.get("confidence", 1.0),
            importance=metadata.get("importance", 3),
            source=metadata.get("source", "unknown"),
            source_ids=list(source_ids or []),
            supersedes=metadata.get("supersedes") or None,
            created_at=metadata.get("created_at"),
            updated_at=metadata.get("updated_at"),
            access_count=metadata.get("access_count", 0),
            last_accessed=metadata.get("last_accessed", 0.0),
            metadata=extra_metadata,
        )
