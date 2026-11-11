# modules/debug/context_snapshot.py
import copy
import datetime
import math
import re
import threading
import uuid
from collections import Counter, defaultdict, deque
from typing import Any, Optional


SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"tp-[A-Za-z0-9_-]{12,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
    re.compile(r"(authorization\s*[:=]\s*)[^\s,;}]+", re.IGNORECASE),
    re.compile(r"(napcat[_-]?token\s*[:=]\s*)[^\s,;}]+", re.IGNORECASE),
]


PIPELINE_STAGES = [
    "prepare_message_batch",
    "normalize_incoming_content",
    "prepare_chat_context",
    "retrieve_memories",
    "decide_reply_action",
    "generate_reply",
    "send_reply",
    "finalize_conversation",
]

STAGE_LABELS = {
    "prepare_message_batch": "读取缓冲",
    "normalize_incoming_content": "内容归一化",
    "prepare_chat_context": "加载上下文",
    "retrieve_memories": "RAG 记忆检索",
    "decide_reply_action": "回复决策",
    "generate_reply": "LLM 生成 & 工具",
    "send_reply": "分段发送",
    "finalize_conversation": "收尾与日记",
}


def utc_now_str() -> str:
    """返回统一格式的快照时间。"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def estimate_tokens(text: str) -> int:
    """第一版使用字符数粗估 token。"""
    if not text:
        return 0
    return max(1, len(str(text)) // 2)


def redact_text(text: str) -> str:
    """脱敏字符串中的 API Key 和 token。"""
    value = str(text)
    for pattern in SECRET_PATTERNS:
        if pattern.pattern.startswith("(authorization") or pattern.pattern.startswith("(napcat"):
            value = pattern.sub(r"\1<REDACTED>", value)
        else:
            value = pattern.sub("<REDACTED>", value)
    return value


def sanitize_value(value: Any) -> Any:
    """递归脱敏快照内容，避免 Debug 页面暴露密钥。"""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_value(item) for item in value]
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            key_str = str(key)
            if re.search(r"api[_-]?key|secret|token|authorization|password", key_str, re.IGNORECASE):
                sanitized[key_str] = "<REDACTED>" if item else item
            else:
                sanitized[key_str] = sanitize_value(item)
        return sanitized
    return value


def build_token_estimate(messages: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    """按 role 统计字符数与 token 粗估。"""
    by_role = {}
    total_chars = 0
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "unknown")
        content = message.get("content") or ""
        if not isinstance(content, str):
            content = str(content)
        char_count = len(content)
        total_chars += char_count
        by_role[role] = by_role.get(role, 0) + estimate_tokens(content)
    return {
        "total_chars": total_chars,
        "estimated_tokens": estimate_tokens("x" * total_chars) if total_chars else 0,
        "by_role": by_role,
    }


def _extract_tools_from_snapshot(snapshot: dict[str, Any]) -> list[str]:
    explicit = snapshot.get("tools_used")
    if isinstance(explicit, list) and explicit:
        return [str(x) for x in explicit if x]
    names = []
    for t in snapshot.get("tool_trace") or []:
        if isinstance(t, dict):
            for c in t.get("calls") or []:
                if isinstance(c, dict) and c.get("name"):
                    names.append(str(c["name"]))
    for m in snapshot.get("built_messages") or []:
        if isinstance(m, dict):
            if m.get("role") == "tool" and m.get("name"):
                names.append(str(m["name"]))
            for tc in m.get("tool_calls") or []:
                fn = (tc.get("function") or {}).get("name") if isinstance(tc, dict) else None
                if fn:
                    names.append(str(fn))
    return names


def summarize_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """生成列表视图所需的轻量摘要。"""
    combined_text = str(snapshot.get("combined_text") or "")
    answer_text = str(snapshot.get("answer_text") or "")
    latency = snapshot.get("latency") or {}
    token_estimate = snapshot.get("token_estimate") or {}
    diaries = snapshot.get("relevant_diaries") or []
    tools_used = _extract_tools_from_snapshot(snapshot)
    return {
        "snapshot_id": snapshot.get("snapshot_id"),
        "chat_id": snapshot.get("chat_id"),
        "mode": snapshot.get("mode"),
        "created_at": snapshot.get("created_at"),
        "updated_at": snapshot.get("updated_at"),
        "stage": snapshot.get("stage"),
        "stage_status": snapshot.get("stage_status", "done"),
        "combined_text_preview": combined_text[:120],
        "answer_text_preview": answer_text[:120],
        "message_count": snapshot.get("message_count", 0),
        "incoming_count": snapshot.get("incoming_count", 0),
        "senders": snapshot.get("senders") or [],
        "should_reply": snapshot.get("should_reply"),
        "skip_reply": bool(snapshot.get("skip_reply", False)),
        "ice_break": bool(snapshot.get("ice_break", False)),
        "force_reply": bool(snapshot.get("force_reply", False)),
        "built_message_count": len(snapshot.get("built_messages") or []),
        "estimated_tokens": token_estimate.get("estimated_tokens", 0),
        "by_role": token_estimate.get("by_role") or {},
        "latency_total": latency.get("total"),
        "latency": latency,
        "rag_count": len(diaries),
        "rag_interest": snapshot.get("rag_interest"),
        "energy": snapshot.get("energy"),
        "activity": snapshot.get("activity"),
        "bioclock": snapshot.get("bioclock"),
        "llm_rounds": snapshot.get("llm_rounds", 0),
        "tools_used": tools_used,
        "errors": snapshot.get("errors") or [],
    }


class ContextSnapshotStore:
    """线程安全的内存快照存储，只保留最近 N 条，并提供实时运行态与聚合遥测分析。"""

    def __init__(self, maxlen: int = 200):
        self._items = deque(maxlen=maxlen)
        self._lock = threading.RLock()
        self._runtime_yuki = None
        self._runtime_sender = None
        self._runtime_group_state = None

    def bind_runtime(self, yuki=None, sender=None, group_active_state=None) -> None:
        """绑定主程序运行时引用，用于在 WebUI 中展示实时精力、生物钟、活跃度与连接状态。"""
        with self._lock:
            if yuki is not None:
                self._runtime_yuki = yuki
            if sender is not None:
                self._runtime_sender = sender
            if group_active_state is not None:
                self._runtime_group_state = group_active_state

    def put(self, snapshot: dict[str, Any]) -> str:
        """写入新快照并返回 snapshot_id。"""
        now = utc_now_str()
        item = sanitize_value(copy.deepcopy(snapshot or {}))
        snapshot_id = str(item.get("snapshot_id") or uuid.uuid4())
        item["snapshot_id"] = snapshot_id
        item.setdefault("created_at", now)
        item["updated_at"] = now
        item.setdefault("stage", "created")
        item.setdefault("latency", {})
        item.setdefault("errors", [])
        item.setdefault("built_messages", [])
        item["token_estimate"] = build_token_estimate(item.get("built_messages"))
        with self._lock:
            self._items.append(item)
        return snapshot_id

    def update(self, snapshot_id: str, **fields) -> None:
        """按 snapshot_id 更新快照字段，未命中时静默忽略。"""
        if not snapshot_id:
            return
        updates = sanitize_value(copy.deepcopy(fields))
        updates["updated_at"] = utc_now_str()
        with self._lock:
            for item in reversed(self._items):
                if item.get("snapshot_id") == snapshot_id:
                    item.update(updates)
                    if "built_messages" in updates or "token_estimate" not in item:
                        item["token_estimate"] = build_token_estimate(item.get("built_messages"))
                    return

    def latest(self, chat_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        """查询全局或指定 chat_id 的最新快照。"""
        cid = str(chat_id) if chat_id else None
        with self._lock:
            for item in reversed(self._items):
                if cid is None or str(item.get("chat_id")) == cid:
                    return copy.deepcopy(item)
        return None

    def list_recent(self, limit: int = 50, chat_id: Optional[str] = None) -> list[dict[str, Any]]:
        """返回最近快照摘要列表。"""
        cid = str(chat_id) if chat_id else None
        limit = max(1, min(int(limit or 50), 200))
        rows = []
        with self._lock:
            for item in reversed(self._items):
                if cid is not None and str(item.get("chat_id")) != cid:
                    continue
                rows.append(summarize_snapshot(item))
                if len(rows) >= limit:
                    break
        return rows

    def get(self, snapshot_id: str) -> Optional[dict[str, Any]]:
        """按 snapshot_id 获取完整快照。"""
        with self._lock:
            for item in self._items:
                if item.get("snapshot_id") == snapshot_id:
                    return copy.deepcopy(item)
        return None

    def yuki_runtime_state(self) -> dict[str, Any]:
        """采集 Yuki 实时生理指标（24h 生物钟曲线、各群精力/活跃度/欲望、连接与女仆状态）。"""
        now = datetime.datetime.now()
        now_hour = round(now.hour + now.minute / 60.0, 2)

        try:
            from config import cfg
            from core.brain import YukiState
            calc_weight = YukiState._calculate_smooth_time_weight
            current_weight = round(float(YukiState.get_smooth_time_weight()), 3)
            max_energy = float(getattr(cfg, "MAX_ENERGY", 100.0) or 100.0)
            initial_energy = float(getattr(cfg, "INITIAL_ENERGY", 100.0) or 100.0)
            recovery_per_min = float(getattr(cfg, "RECOVERY_PER_MIN", 0.8) or 0.8)
            cost_per_reply = float(getattr(cfg, "COST_PER_REPLY", 4.0) or 4.0)
            target_groups = [str(g) for g in (getattr(cfg, "TARGET_GROUPS", []) or [])]
            robot_name = str(getattr(cfg, "ROBOT_NAME", "Yuki") or "Yuki")
            self_qq = str(getattr(cfg, "SELF_QQ", "") or "")
            llm_model = str(getattr(cfg, "LLM_MODEL", "") or "")
            sig_alpha = float(getattr(cfg, "SIGMOID_ALPHA", 0.1) or 0.1)
            sig_centre = float(getattr(cfg, "SIGMOID_CENTRE", 45.0) or 45.0)
        except Exception:
            def calc_weight(t: float) -> float:
                return 1.0
            current_weight = 1.0
            max_energy = 100.0
            initial_energy = 100.0
            recovery_per_min = 0.8
            cost_per_reply = 4.0
            target_groups = []
            robot_name = "Yuki"
            self_qq = ""
            llm_model = ""
            sig_alpha = 0.1
            sig_centre = 45.0

        # 24h 生物钟采样曲线 (每 0.5 小时一个点)
        bioclock_curve = []
        for idx in range(49):
            h = round(idx * 0.5, 1)
            w = round(float(calc_weight(min(h, 23.99))), 3)
            bioclock_curve.append({"hour": h, "label": f"{int(h):02d}:{30 if idx % 2 else 0:02d}", "weight": w})

        if 1.0 <= now_hour < 7.0:
            phase_label = "🌙 深度睡眠谷"
        elif 7.0 <= now_hour < 9.2:
            phase_label = "🌅 晨间元气峰"
        elif 11.5 <= now_hour < 14.2:
            phase_label = "🍓 午间活跃峰"
        elif 18.0 <= now_hour < 22.5:
            phase_label = "✨ 晚间黄金峰"
        elif now_hour >= 23.5 or now_hour < 1.0:
            phase_label = "💤 困倦入睡期"
        else:
            phase_label = "🌸 日常巡航态"

        with self._lock:
            yuki = self._runtime_yuki
            sender = self._runtime_sender
            group_state = self._runtime_group_state or {}
            items = list(self._items)

        # 汇总已知群组及其最近一次快照的指标作为兜底
        last_snap_by_chat: dict[str, dict[str, Any]] = {}
        for it in items:
            cid = str(it.get("chat_id") or "")
            if cid:
                last_snap_by_chat[cid] = it

        all_group_ids = []
        seen_g = set()
        for cid in target_groups:
            if cid and cid not in seen_g:
                seen_g.add(cid)
                all_group_ids.append(cid)
        if yuki is not None:
            for cid in list(getattr(yuki, "energy", {}).keys()) + list(getattr(yuki, "group_activity", {}).keys()):
                cid_s = str(cid)
                if cid_s and cid_s not in seen_g:
                    seen_g.add(cid_s)
                    all_group_ids.append(cid_s)
        for cid, snap in last_snap_by_chat.items():
            if snap.get("mode") == "group" and cid not in seen_g:
                seen_g.add(cid)
                all_group_ids.append(cid)

        groups = []
        for cid in all_group_ids:
            snap = last_snap_by_chat.get(cid) or {}
            energy_val = snap.get("energy")
            activity_val = snap.get("activity")
            desire_val = None
            ice_fails = 0
            if yuki is not None:
                raw_e = getattr(yuki, "energy", {}).get(cid)
                last_up = getattr(yuki, "last_update", {}).get(cid)
                if raw_e is not None:
                    if isinstance(last_up, datetime.datetime):
                        mins = max(0.0, (now - last_up).total_seconds() / 60.0)
                        energy_val = min(max_energy, float(raw_e) + mins * recovery_per_min)
                    else:
                        energy_val = float(raw_e)
                raw_act = getattr(yuki, "group_activity", {}).get(cid)
                if raw_act is not None:
                    activity_val = float(raw_act)
                raw_des = getattr(yuki, "desire_to_start_topic", {}).get(cid)
                if raw_des is not None:
                    desire_val = float(raw_des)
                ice_fails = int((getattr(yuki, "ice_break_fail_count", {}) or {}).get(cid, 0) or 0)

            if energy_val is None:
                energy_val = initial_energy
            if activity_val is None:
                activity_val = 0.0
            if desire_val is None:
                # 依据公式实时计算预估欲望
                act_norm = min(float(activity_val) / 5.0, 1.0)
                follow_d = act_norm * 80.0 * (float(energy_val) / 100.0)
                ice_d = (1.0 - act_norm) * 60.0 * max(0.0, (float(energy_val) - 60.0) / 40.0)
                total_d = max(follow_d, ice_d) * current_weight
                try:
                    desire_val = 100.0 / (1.0 + math.exp(-sig_alpha * (total_d - sig_centre)))
                except OverflowError:
                    desire_val = 0.0

            energy_val = round(max(0.0, min(max_energy, float(energy_val))), 1)
            activity_val = round(max(0.0, min(10.0, float(activity_val))), 2)
            desire_val = round(max(0.0, min(100.0, float(desire_val))), 1)
            groups.append({
                "chat_id": cid,
                "energy": energy_val,
                "max_energy": max_energy,
                "energy_pct": round(energy_val / max(1.0, max_energy) * 100.0, 1),
                "sleeping": energy_val < 13.0,
                "activity": activity_val,
                "activity_pct": round(min(100.0, activity_val * 10.0), 1),
                "desire": desire_val,
                "ice_break_fails": ice_fails,
                "enabled": bool(group_state.get(cid, True)) if isinstance(group_state, dict) else True,
            })

        try:
            from core.focus import focus_manager
            focused_chats = [
                cid for cid in seen_g | set(last_snap_by_chat.keys())
                if focus_manager.is_focused(cid)
            ]
        except Exception:
            focused_chats = []

        maid_tasks = {}
        if yuki is not None:
            maid_tasks = dict(getattr(yuki, "maid_current_tasks", {}) or {})

        napcat_online = bool(getattr(sender, "connected", False)) if sender is not None else None

        return {
            "robot_name": robot_name,
            "self_qq": self_qq,
            "llm_model": llm_model,
            "napcat_online": napcat_online,
            "bioclock": {
                "now_hour": now_hour,
                "current_weight": current_weight,
                "phase_label": phase_label,
                "curve": bioclock_curve,
            },
            "energy_config": {
                "max_energy": max_energy,
                "cost_per_reply": cost_per_reply,
                "recovery_per_min": recovery_per_min,
                "sleep_threshold": 13.0,
            },
            "groups": groups,
            "maid_tasks": maid_tasks,
            "phone_focused_chats": focused_chats,
        }

    def analytics(self) -> dict[str, Any]:
        """聚合全量快照与手机轨迹的多维统计数据，供前端图表渲染。"""
        with self._lock:
            items = [copy.deepcopy(x) for x in self._items]

        total = len(items)
        replied = 0
        dived = 0
        skipped = 0
        running = 0
        errored = 0

        stage_sums: dict[str, list[float]] = {s: [] for s in PIPELINE_STAGES}
        total_latencies: list[float] = []

        role_totals: Counter = Counter()
        total_tokens_list: list[int] = []
        recent_series = []

        tool_counter: Counter = Counter()
        turns_with_tools = 0
        total_llm_rounds = 0

        chat_stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"chat_id": "", "mode": "group", "turns": 0, "replied": 0, "dived": 0, "tokens_sum": 0, "lat_sum": 0.0, "lat_cnt": 0}
        )

        rag_counts: list[int] = []
        rag_interests: list[float] = []

        for item in items:
            cid = str(item.get("chat_id") or "unknown")
            mode = str(item.get("mode") or "group")
            errs = item.get("errors") or []
            is_skip = bool(item.get("skip_reply"))
            sr = item.get("should_reply")
            stage = str(item.get("stage") or "")

            if errs:
                errored += 1
            elif is_skip:
                skipped += 1
            elif sr is False:
                dived += 1
            elif sr is True and (item.get("answer_text") or stage == "finalize_conversation"):
                replied += 1
            elif stage not in ("finalize_conversation", "stopped"):
                running += 1
            else:
                dived += 1

            lat = item.get("latency") or {}
            for s in PIPELINE_STAGES:
                v = lat.get(s)
                if isinstance(v, (int, float)) and v >= 0:
                    stage_sums[s].append(float(v) * 1000.0)
            t_lat = lat.get("total")
            t_lat_ms = round(float(t_lat) * 1000.0, 1) if isinstance(t_lat, (int, float)) else 0.0
            if t_lat_ms > 0:
                total_latencies.append(t_lat_ms)

            te = item.get("token_estimate") or {}
            est_tok = int(te.get("estimated_tokens") or 0)
            by_role = te.get("by_role") or {}
            if est_tok > 0:
                total_tokens_list.append(est_tok)
            for r_k, r_v in by_role.items():
                role_totals[r_k] += int(r_v or 0)

            tools_used = _extract_tools_from_snapshot(item)
            if tools_used:
                turns_with_tools += 1
                for tn in tools_used:
                    tool_counter[tn] += 1
            total_llm_rounds += int(item.get("llm_rounds") or (1 if est_tok else 0))

            diaries = item.get("relevant_diaries")
            if isinstance(diaries, list):
                rag_counts.append(len(diaries))
            ri = item.get("rag_interest")
            if isinstance(ri, (int, float)):
                rag_interests.append(float(ri))

            cs = chat_stats[cid]
            cs["chat_id"] = cid
            cs["mode"] = mode
            cs["turns"] += 1
            if sr is True and not is_skip:
                cs["replied"] += 1
            else:
                cs["dived"] += 1
            cs["tokens_sum"] += est_tok
            if t_lat_ms > 0:
                cs["lat_sum"] += t_lat_ms
                cs["lat_cnt"] += 1

        # 最近 24 条序列用于趋势图
        for item in items[-24:]:
            te = item.get("token_estimate") or {}
            br = te.get("by_role") or {}
            lat = item.get("latency") or {}
            t_ms = round(float(lat.get("total") or 0) * 1000.0, 1)
            ts_str = str(item.get("updated_at") or item.get("created_at") or "")
            short_time = ts_str.split(" ")[-1] if " " in ts_str else ts_str
            recent_series.append({
                "snapshot_id": item.get("snapshot_id"),
                "chat_id": item.get("chat_id"),
                "mode": item.get("mode"),
                "time": short_time,
                "should_reply": item.get("should_reply"),
                "skip_reply": bool(item.get("skip_reply", False)),
                "total_tokens": int(te.get("estimated_tokens") or 0),
                "system": int(br.get("system") or 0),
                "user": int(br.get("user") or 0),
                "assistant": int(br.get("assistant") or 0),
                "tool": int(br.get("tool") or 0),
                "latency_ms": t_ms,
                "rag_count": len(item.get("relevant_diaries") or []),
            })

        stage_breakdown = []
        raw_stage_avgs = {}
        for s in PIPELINE_STAGES:
            vals = stage_sums[s]
            avg_v = sum(vals) / len(vals) if vals else 0.0
            raw_stage_avgs[s] = avg_v
        sum_stage_avgs = sum(raw_stage_avgs.values()) or 1.0
        for s in PIPELINE_STAGES:
            vals = stage_sums[s]
            avg_v = round(raw_stage_avgs[s], 1)
            max_v = round(max(vals), 1) if vals else 0.0
            stage_breakdown.append({
                "stage": s,
                "label": STAGE_LABELS.get(s, s),
                "avg_ms": avg_v,
                "max_ms": max_v,
                "count": len(vals),
                "share_pct": round(raw_stage_avgs[s] / sum_stage_avgs * 100.0, 1) if vals else 0.0,
            })

        sorted_lat = sorted(total_latencies)
        avg_lat_ms = round(sum(sorted_lat) / len(sorted_lat), 1) if sorted_lat else 0.0
        p95_lat_ms = round(sorted_lat[min(len(sorted_lat) - 1, int(len(sorted_lat) * 0.95))], 1) if sorted_lat else 0.0

        sum_all_tokens = sum(total_tokens_list)
        avg_tokens = int(round(sum_all_tokens / len(total_tokens_list))) if total_tokens_list else 0
        max_tokens = max(total_tokens_list) if total_tokens_list else 0

        chat_list = []
        for cs in chat_stats.values():
            turns_n = max(1, cs["turns"])
            chat_list.append({
                "chat_id": cs["chat_id"],
                "mode": cs["mode"],
                "turns": cs["turns"],
                "replied": cs["replied"],
                "dived": cs["dived"],
                "reply_rate": round(cs["replied"] / turns_n * 100.0, 1),
                "avg_tokens": int(round(cs["tokens_sum"] / turns_n)),
                "avg_latency_ms": round(cs["lat_sum"] / cs["lat_cnt"], 1) if cs["lat_cnt"] else 0.0,
            })
        chat_list.sort(key=lambda x: x["turns"], reverse=True)

        tool_ranking = [
            {"name": name, "count": cnt}
            for name, cnt in tool_counter.most_common(12)
        ]

        # 聚合手机轨迹数据
        phone_stats = {
            "session_count": 0,
            "total_steps": 0,
            "success_rate": 100.0,
            "avg_step_ms": 0.0,
            "timing_shares": {},
        }
        try:
            from modules.debug.phone_trace import phone_trace_store
            p_sessions = phone_trace_store.list_sessions(limit=80)
            phone_stats["session_count"] = len(p_sessions)
            step_ms_list = []
            step_ok = 0
            step_total = 0
            tb_sums = Counter()
            for ps in p_sessions:
                full_s = phone_trace_store.get_session(ps.get("session_id") or "")
                for st in (full_s or {}).get("steps") or []:
                    step_total += 1
                    if st.get("success", True):
                        step_ok += 1
                    if st.get("elapsed_ms"):
                        step_ms_list.append(int(st["elapsed_ms"]))
                    for k, v in (st.get("timing_breakdown") or {}).items():
                        if isinstance(v, (int, float)) and v >= 0:
                            tb_sums[k] += float(v)
            phone_stats["total_steps"] = step_total
            phone_stats["success_rate"] = round(step_ok / step_total * 100.0, 1) if step_total else 100.0
            phone_stats["avg_step_ms"] = round(sum(step_ms_list) / len(step_ms_list), 1) if step_ms_list else 0.0
            tb_total = sum(tb_sums.values()) or 1.0
            phone_stats["timing_shares"] = {
                k: {"sum_ms": round(v, 1), "pct": round(v / tb_total * 100.0, 1)}
                for k, v in tb_sums.items()
            }
        except Exception:
            pass

        rag_hits = sum(1 for c in rag_counts if c > 0)
        return {
            "ok": True,
            "generated_at": utc_now_str(),
            "decisions": {
                "total": total,
                "replied": replied,
                "dived": dived,
                "skipped": skipped,
                "running": running,
                "errored": errored,
                "reply_rate": round(replied / total * 100.0, 1) if total else 0.0,
            },
            "latency": {
                "avg_total_ms": avg_lat_ms,
                "p95_total_ms": p95_lat_ms,
                "stages": stage_breakdown,
            },
            "tokens": {
                "total_tokens": sum_all_tokens,
                "avg_tokens": avg_tokens,
                "max_tokens": max_tokens,
                "by_role": dict(role_totals),
                "recent_series": recent_series,
            },
            "tools": {
                "total_tool_calls": sum(tool_counter.values()),
                "turns_with_tools": turns_with_tools,
                "total_llm_rounds": total_llm_rounds,
                "ranking": tool_ranking,
            },
            "rag": {
                "turns_checked": len(rag_counts),
                "hit_count": rag_hits,
                "hit_rate": round(rag_hits / len(rag_counts) * 100.0, 1) if rag_counts else 0.0,
                "avg_recall_count": round(sum(rag_counts) / len(rag_counts), 2) if rag_counts else 0.0,
                "avg_interest": round(sum(rag_interests) / len(rag_interests), 3) if rag_interests else 0.0,
            },
            "chats": chat_list[:15],
            "phone": phone_stats,
            "yuki_state": self.yuki_runtime_state(),
        }

    def status(self) -> dict[str, Any]:
        """返回全局状态摘要。"""
        with self._lock:
            items = list(self._items)
        active_chats = sorted({str(item.get("chat_id")) for item in items if item.get("chat_id")})
        latest = items[-1] if items else None
        return {
            "ok": True,
            "generated_at": utc_now_str(),
            "snapshot_count": len(items),
            "active_chats": active_chats,
            "latest_snapshot_id": latest.get("snapshot_id") if latest else None,
            "latest_snapshot_at": latest.get("updated_at") if latest else None,
            "yuki_state": self.yuki_runtime_state(),
        }


context_snapshot_store = ContextSnapshotStore()
