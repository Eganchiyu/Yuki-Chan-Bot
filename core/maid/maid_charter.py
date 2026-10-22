"""自进化准则的代码侧单一来源。

三处共用：
- `maid_prompt.py` 注入小女仆 system prompt（必须精简，控制 token）
- 自改工具（propose_patch / verify_patch / request_self_reload）做路径分级判定
- 说明文档 `docs/evolution-charter.md` 与人读版本对齐

修改本文件等同于修改准则：需要机主同意，且不属于 agent 自改权限范围。
"""

# ---------------------------------------------------------------- 路径分级
# 自由区：改完即生效，只需 git 追溯
FREE_PATHS = ("skills/", "workspace/", "temp/")

# 受限区：必须走 校验 → 试启动 → 切换 → 健康检查 → 失败回滚
RESTRICTED_PATHS = (
    "core/",
    "utils/",
    "modules/",
    "network/",
    "main.py",
    "config.py",
    "init.py",
)

# 禁区：任何情况下不得改动
FORBIDDEN_PATHS = (
    ".git/",
    ".gitignore",
    "deploy/",
    "configs/",
    "data/",
    "yuki_memory/",
    "memory/",
    "logs/",
    "models/",
    "maid_venv/",
    "docs/evolution-charter.md",
    "core/maid/maid_charter.py",
    # 人格：任何情况下不得改动，无例外
    "core/prompts.py",
)

# 敏感改动：允许但必须额外留档并向机主汇报（对应准则第 1 条）
SENSITIVE_HINTS = ("yuki_memory", "chromadb", "embedding", "collection", "vector")

# ---------------------------------------------------------------- 限额
# 硬限额只做「防呆兜底」，真正的放行判断交给宿主侧模型审查（deploy/reviewer.py）。
# 数值放宽是因为复杂功能改造常常横向涉及多个文件，卡在 3 个文件会逼模型拆碎改动。
MAX_PATCH_FILES = 10          # 单次 patch 文件数上限
MAX_PATCH_ADDED_LINES = 1000  # 单次 patch 净增行数上限
MAX_PATCH_REMOVED_RATIO = 0.5  # 单个文件删掉超过原行数这个比例就拒绝（防误删整模块）
MAX_EVOLVE_PER_HOUR = 3      # 每小时自改上限
MAX_EVOLVE_PER_DAY = 10      # 每日自改上限
COOLDOWN_AFTER_FAILURES = 2  # 连续失败几次进入冷却
COOLDOWN_HOURS = 6           # 冷却时长

# ---------------------------------------------------------------- 验证门
# 对应准则第 5 条，deploy/verify.sh 按顺序执行
VERIFY_GATES = ("compileall", "import", "tests", "dry_run", "health")


def classify_path(path: str) -> str:
    """返回 "forbidden" / "free" / "restricted" / "unknown"。禁区优先判定。"""
    p = (path or "").replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    p = p.lstrip("/")
    for prefix in FORBIDDEN_PATHS:
        if p == prefix or p.startswith(prefix):
            return "forbidden"
    for prefix in FREE_PATHS:
        if p == prefix or p.startswith(prefix):
            return "free"
    for prefix in RESTRICTED_PATHS:
        if p == prefix or p.startswith(prefix):
            return "restricted"
    return "unknown"


def is_sensitive(diff_text: str) -> bool:
    """粗判 patch 是否触及数据/向量相关敏感面，用于额外留档。"""
    low = (diff_text or "").lower()
    return any(hint in low for hint in SENSITIVE_HINTS)


# ---------------------------------------------------------------- prompt 片段
EVOLUTION_CHARTER = """
### 自进化准则（硬约束，违反即被工具层拒绝）

1. **数据优先**：`yuki_memory/`、`data/`、`memory/` 是不可再生资产。禁止删除、覆盖、重建、改 schema；只允许追加。
2. **改动分级**：
   - 自由区：`skills/`、`workspace/`、`temp/`。
   - 受限区：`core/`、`utils/`、`modules/`、`network/`、`main.py`、`config.py`——必须走校验→试启动→切换→健康检查。
   - 禁区（一律拒绝）：`deploy/`、`.git/`、`.gitignore`、`configs/`、`data/`、`yuki_memory/`、`memory/`、`logs/`、`models/`、`maid_venv/`、`maid_approval.py` 的拦截规则、本准则文件。
3. **小步**：单次 patch ≤ 10 个文件、净增 ≤ 1000 行；超过会被驳回，请拆分。禁止顺手重构，禁止整模块重写。
   每个 patch 会先经一次独立模型审查：只看出改动是否服务于任务目标、是否删功能、是否碰数据。被驳回时按意见改，不要原样重提。
4. **实证**：每个 patch 必须说明 改了什么 / 为什么 / 怎么验证 / 失败怎么回滚。缺一项不许提交。
5. **验证先行**：编译 → 测试 → 试启动 → 健康检查，任一级失败都不许请求切换，带报错重试。
6. **诚实**：失败必须上报，不许隐藏，不许无证据宣称完成。
7. **速率**：每小时 ≤ 3 次、每日 ≤ 10 次自改；连续 2 次切换失败进入 6 小时冷却。
8. **不许削弱防御**：日志、trace、审批、限流、单实例锁、健康检查、回滚脚本都不得弱化或绕过。
9. **人格禁区**：`core/prompts.py` 的人格文本与 `configs/` 中的人格配置是**硬禁区**，任何时候都不得改动，没有例外。人格只能由机主本人修改。
10. **可追溯**：一次自改 = 一个 `self-evolve: ...` 提交；成功切换打 tag `good-<时间戳>`。
"""
