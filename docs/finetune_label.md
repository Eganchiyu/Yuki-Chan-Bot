# Yuki 微调语料采集与人工打标系统（SFT / DPO）

> 状态：已上线（Phase 1 + Phase 2 已提交并实测通过，容器内全量 `pytest tests -q` = 240 passed）  
> 相关提交：`28bbed8`（Phase 1 全量轨迹采集）、`4fe21ea`（Phase 2 `message_id` 回传与贴表情打标）  
> 唯一事实源：本文档记录当前规划、架构链路、文件地图、Schema 规范及后续检查/导出用法。

---

## 1. 目标与整体规划

### 1.1 核心思路
采用**“全量无损采集 + 长期自然使用 + 零打扰人工打标”**的方式，在日常群聊/私聊中持续积累真实、高纯度的 Yuki 交互数据，与历史存量日志/记忆库共同构成寒假本地模型微调（LoRA SFT / DPO）训练集。

### 1.2 为什么需要新增采集（不能只用 `data/yuki_log.txt`）
* [data/yuki_log.txt](file:///home/asumi/Yuki/data/yuki_log.txt) 记录的是发送前清洗过的结果，**缺失**三类关键训练信号：
  1. 完整的多层输入上下文 `built_messages`（人设、RAG 回忆、小本本、最近滑窗对话）；
  2. 多轮工具调用轨迹（`tool_calls` 与 `tool` 返回消息）；
  3. 保留 `<layout>...</layout>` 内心布局的原始回复 `answer_raw`（发送前会被 `clean_visible_reply()` 剥离）。

### 1.3 已拍板的设计决策
1. **微调定位（分层路由而非全量替代）**：
   * 重点培养**日常人格、`<layout>` 腹黑拉扯、`[MEME:情绪]` 与轻量群聊工具（`skip` / `poke`）**；
   * `phone_action`（原生视觉+控件树多步推理）、`art_draw` 与自主轮工坊仍留给强模型路由。
   * 基座优先选 `Qwen2.5-7B-Instruct`（无内置 `<think>` 标签，不与 `<layout>` 冲突）或显式关闭思考模式的 `Qwen3-8B`；训练框架可选 LLaMA-Factory / Unsloth（QLoRA）。
2. **打标规则（Plan A）**：
   * 仅采信主人 QQ（`cfg.is_master_qq`）的贴表情或引用打标事件；
   * 区分正向 `perfect`（赞/爱心等）、负向 `bad`（踩，可留作 DPO 负样本）、撤回 `removed` 与其他 `reaction`（保留原始 `emoji_id`）。
3. **出站 `message_id` 获取（Plan A）**：
   * `NapCatGateway.send()` 改为走 `call()` 等待 OneBot 响应并取回 `data.message_id`（超时或错误返回 `None`，不重发避免重复消息）。
4. **上下文存储方式**：
   * 每轮直接落盘完整 `input_messages`（剥离 base64 图片载荷并脱敏密钥），保证单行块完全自包含，未来导出零外部依赖。

---

## 2. 现行架构与运行链路

### 2.1 全链路数据流

```text
[1] 轨迹采集（Phase 1）
  SessionPipeline.generate_reply()
    └─► EngineReplyService.api_reply() / chat_with_tools()
          ├─ 缓存本轮 input_messages（初始 built_messages）
          ├─ 缓存轮内 turn_messages（assistant tool_calls + tool 结果 + 工具期合并消息）
          └─ 缓存 tools_used / tool_trace / outcome / llm_rounds
    ├─ 若调用 skip 工具（早停）：
    │     └─► _record_sft_turn(outcome="skip", answer_raw="", answer_text="")
    │           └─► data/sft/traces_YYYY-MM.jsonl
    └─ 若正常/过滤/异常回复：
          └─► SessionPipeline.send_reply()
                ├─ 分段发送文本 / [MEME:] / 语音 / Filtered 彩蛋
                ├─ 收集每条气泡返回的 sent_message_ids（同步写回 shot_live_buffer）
                └─► SessionPipeline.finalize_conversation()
                      └─► _record_sft_turn(answer_raw=保留<layout>, sent_message_ids=...)
                            ├─► data/sft/traces_YYYY-MM.jsonl
                            └─► data/sft/msg_index.jsonl（建立 message_id -> turn_id 索引）

[2] 人工打标（Phase 2）
  (方式 A：群聊贴表情)
    NapCat 推送 notice / group_msg_emoji_like
      └─► listen_main.handle_emoji_like_event()
            ├─ 校验 cfg.is_master_qq(user_id)
            └─► sft_trace_logger.record_label()
                  ├─ 查 msg_index.jsonl 解析 turn_id（未关联 Yuki 轨迹则忽略）
                  └─► 追加写入 data/sft/labels.jsonl

  (方式 B：私聊/群聊引用兜底)
    主人引用 Yuki 消息仅发送 /good /perfect /赞 或 /bad /差 /踩
      └─► listen_main.handle_sft_quote_label()
            ├─ 查 msg_index.jsonl 解析 turn_id（未命中则放行正常聊天）
            └─► 写入 data/sft/labels.jsonl 并拦截本次入站，不进入聊天上下文
```

### 2.2 核心模块与代码位置

| 模块 / 文件 | 职责与关键符号 |
| :--- | :--- |
| [core/sft_logger.py](file:///home/asumi/Yuki/core/sft_logger.py) | `SFTTraceLogger`、`sft_trace_logger`、`strip_media_and_sanitize()`、`classify_emoji_label()`、`record_turn()`、`index_messages()`、`resolve_turn_id()`、`record_label()` |
| [core/engine/engine_reply.py](file:///home/asumi/Yuki/core/engine/engine_reply.py) | `EngineReplyService.chat_with_tools()`（`finally` 缓存 `_last_sft_capture`）、`api_reply()`（异常兜底缓存）、`pop_sft_capture()` |
| [core/engine/engine.py](file:///home/asumi/Yuki/core/engine/engine.py) | `YukiEngine.pop_sft_capture()` 门面透传 |
| [core/session_pipeline.py](file:///home/asumi/Yuki/core/session_pipeline.py) | `SessionPipeline._record_sft_turn()`、`generate_reply()`（`skip` 落盘）、`send_reply()` / `_send_text_segment()` / `_send_meme_segment()`（收集 `sent_message_ids`）、`finalize_conversation()` |
| [network/napcat.py](file:///home/asumi/Yuki/network/napcat.py) | `NapCatGateway.send()`（改用 `call()` 返回 `message_id`）、`send_local_image()` / `send_local_file()` / `send_local_voice()` 透传返回值 |
| [modules/QQNapcatListen/listen_main.py](file:///home/asumi/Yuki/modules/QQNapcatListen/listen_main.py) | `handle_emoji_like_event()`、`handle_sft_quote_label()`、`napcat_listen()` 路由分发 |
| [tests/conftest.py](file:///home/asumi/Yuki/tests/conftest.py) | `isolate_group_state` fixture 自动将 `sft_trace_logger.base_dir` 重定向至 `tmp_path/sft`，防止单测污染生产日志 |
| [tests/test_sft_logger.py](file:///home/asumi/Yuki/tests/test_sft_logger.py) | 脱敏、落盘、`<layout>` + 工具调用采集、`skip` 分支、跨实例索引恢复、贴表情/引用打标单测 |
| [tests/test_napcat.py](file:///home/asumi/Yuki/tests/test_napcat.py) | `test_gateway_send_returns_message_id` 验证 `send()` 返回 `message_id` |

---

## 3. 数据存储位置与格式规范

### 3.1 数据文件位置
默认位于 `cfg.LOG_FILE` 同级目录下的 `sft/`（生产环境即 `data/sft/`，可通过环境变量 `YUKI_SFT_DIR` 覆写；`data/` 已在 `.gitignore` 中，不入 Git）：

```text
data/sft/
├── traces_YYYY-MM.jsonl   # 按月分片的完整单轮训练块（只追加）
├── msg_index.jsonl        # QQ message_id -> turn_id 持久映射（进程重启可恢复）
└── labels.jsonl           # 主人贴表情 / 引用指令打标事件流（只追加）
```

可配合使用的历史存量数据源：
* [data/yuki_log.txt](file:///home/asumi/Yuki/data/yuki_log.txt)：2026-09-11 起的纯文本对话日志（可用于抽风格种子与 `skip` 场景）；
* [yuki_memory/chroma.sqlite3](file:///home/asumi/Yuki/yuki_memory/chroma.sqlite3)：`diaries` collection（6,600+ 篇日记，用于蒸馏 Topic Seeds）；
* [data/shot_memory/](file:///home/asumi/Yuki/data/shot_memory)：群名场面档案（用于事件锚点）；
* [data/chat_history.json](file:///home/asumi/Yuki/data/chat_history.json)：当前在线滑窗（含少量近期原生 `<layout>`）。

### 3.2 `traces_YYYY-MM.jsonl` 字段说明（`schema_version: 1`）

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `turn_id` | `str` | 本轮唯一 ID（优先复用 `debug_snapshot_id` UUID） |
| `ts` | `str` | 落盘时间（`YYYY-MM-DD HH:MM:SS`） |
| `chat_id` / `mode` / `model` | `str` | 会话 ID、模式（`group`/`private`/`master_private`）、实际调用模型名 |
| `ice_break` | `bool` | 是否冷场破冰触发 |
| `outcome` | `str` | `reply` / `skip` / `exhausted` / `filtered` / `error` |
| `llm_rounds` | `int` | 本轮 LLM 请求次数 |
| `senders` | `list[str]` | 本批次入站发言人列表 |
| `combined_text` | `str` | 归一化后的当前输入文本 |
| `relevant_diaries` | `list[dict]` | 检索到的日记列表 `[{"content": ..., "score": ...}]` |
| `input_messages` | `list[dict]` | 送给模型的完整初始消息列表（已把 base64 图片替换为 `<image_omitted>` 并脱敏密钥） |
| `turn_messages` | `list[dict]` | 轮内工具链产生的中间消息（`assistant` `tool_calls` + `tool` 返回 + 合并消息） |
| `tools_used` / `tool_trace` | `list` | 本轮使用的工具名列表与耗时/参数摘要 |
| `answer_raw` | `str` | 原始回复（**保留 `<layout>...</layout>` 与 `[MEME:...]`**；`skip` 时为空串） |
| `answer_text` | `str` | 剥离 `<layout>` 后的可见回复 |
| `sent_message_ids` | `list[str]` | 本轮发往 QQ 的所有分段气泡 `message_id` |

### 3.3 `labels.jsonl` 与表情 ID 映射

每条打标事件包含：`schema_version`、`ts`、`turn_id`、`message_id`、`chat_id`、`user_id`、`emoji_id`、`is_add`、`label`、`source`（`emoji_like` 或 `quote_cmd`）。

`classify_emoji_label(emoji_id, is_add)` 默认映射：
* `is_add == False` → `removed`
* **正向 `perfect`**：`76`（QQ 赞）、`66`（QQ 爱心 ❤️）、`201`（点赞）、`319`（比心）、`128077`（👍）、`10084` / `2764`（❤️）、`👍`、`❤️`、`❤`、`💖`、`✨`
* **负向 `bad`**：`77`（QQ 踩）、`128078`（👎）、`👎`
* **其他表情** → `reaction`（保留原 `emoji_id` 供后续筛选）
* 支持环境变量扩展：`YUKI_SFT_POSITIVE_EMOJIS`、`YUKI_SFT_NEGATIVE_EMOJIS`（逗号分隔）。

---

## 4. 如何检查与使用这些数据

### 4.1 快速巡检采集量与打标情况

```bash
python3 -c '
import json
from pathlib import Path
from collections import Counter

sft = Path("/home/asumi/Yuki/data/sft")
traces = [json.loads(l) for f in sorted(sft.glob("traces_*.jsonl")) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
labels = [json.loads(l) for l in (sft / "labels.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()] if (sft / "labels.jsonl").exists() else []

print("总轮次:", len(traces), "outcome 分布:", Counter(t["outcome"] for t in traces))
print("打标事件总数:", len(labels), "label 分布:", Counter(lb["label"] for lb in labels))

# 计算每轮最终有效标签（同一 turn_id 取最后一次动作，忽略 removed）
final_label = {}
for lb in labels:
    if lb["label"] == "removed":
        final_label.pop(lb["turn_id"], None)
    else:
        final_label[lb["turn_id"]] = lb["label"]

print("当前有效打标轮次:", Counter(final_label.values()))
by_tid = {t["turn_id"]: t for t in traces}
for tid, lbl in list(final_label.items())[-5:]:
    t = by_tid.get(tid)
    if t:
        print(f"[{lbl}] {t[\"ts\"]} | {t[\"combined_text\"][:50]} => {t[\"answer_raw\"][:80]}")
'
```

### 4.2 导出微调训练集时的清洗清单

`traces_*.jsonl` 忠实还原了线上模型实际看到的原始请求结构；正式导出成 LLaMA-Factory / Unsloth（OpenAI Messages / ShareGPT）训练集时，建议在导出脚本里统一做以下 5 步清洗：

1. **合并连续 `system` 消息**：线上 `input_messages` 开头由多条 `role: "system"` 组成（基础人设 + `【回忆】` + `【小本本】` + 工具提示），导出时用 `\n\n` 合并成第 0 条单条 `system`。
2. **裁剪开头孤立 `assistant`**：滑窗截断可能导致历史对话首条是 `assistant`，导出时丢弃开头孤立的 `assistant`，确保 `system` 后第一条是 `user`。
3. **合并相邻同角色 `user` 消息**：当中间某轮 Yuki 潜水未回复时会出现连续 `user`；若训练模板要求严格交替，用 `\n` 合并相邻 `user`，并顺手 `.lstrip()` 清理末尾 `user` 前导空格。
4. **过滤多模态残缺样本**：若训练纯文本 LoRA，过滤掉含 `<image_omitted>` 或当前轮依赖看图但显示 `[图片已过期]` 的样本。
5. **处理合成事件与负样本**：
   * `【等待超时】` 属于 `reply_watch` 注入消息：若只学被动聊天则过滤，若学主动追击则保留；
   * `outcome == "skip"` 且 `tools_used` 含 `"skip"` 的轮次可保留为标准 `tool_calls` 静音样本；
   * `label == "bad"` 的样本不要放进 SFT 正样本，可配对改写后用于 DPO 偏好对齐。

### 4.3 与历史存量数据合并策略
1. 从高价值人工打标样本（`perfect`）+ 现有 [data/chat_history.json](file:///home/asumi/Yuki/data/chat_history.json) 原生 `<layout>` 样本出发，作为风格锚点；
2. 对 [data/yuki_log.txt](file:///home/asumi/Yuki/data/yuki_log.txt) 清洗出的多轮对话片段，用上述锚点做 Few-Shot `<layout>` 逆向补全；
3. 利用 [yuki_memory/chroma.sqlite3](file:///home/asumi/Yuki/yuki_memory/chroma.sqlite3) 与 [data/shot_memory/](file:///home/asumi/Yuki/data/shot_memory) 提供的真实梗做场景扩增，并与本系统攒出的真实带标 Block 合并微调。
