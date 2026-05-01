import gradio as gr
from config import cfg, _ATTR_MAP, _SECTION_HEADERS
from providers.registry import _PROVIDER_REGISTRY
import logging

logger = logging.getLogger("main")


def _get_platform_options():
    """获取已注册平台列表（动态，确保 Provider 发现已完成）"""
    from providers.registry import ProviderRegistry
    ProviderRegistry()
    return sorted(set(list(_PROVIDER_REGISTRY.keys()) + ["openai", "custom"]))


def get_nested(data, path):
    d = data
    for k in path:
        if isinstance(d, dict) and k in d:
            d = d[k]
        else:
            return None
    return d


def set_nested(data, path, value):
    d = data
    for k in path[:-1]:
        if k not in d or not isinstance(d[k], dict):
            d[k] = {}
        d = d[k]
    d[path[-1]] = value


def load_config():
    cfg.reload()
    return cfg._raw


# ================= 核心：兼容深浅模式的拟物化 CSS =================
# 不再强制写死白色/黑色，完全依赖原生主题变量，只做圆角和阴影的结构化塑形
modern_css = """
/* 隐藏底部不需要的 Footer */
footer { display: none !important; }
/* 强化折叠面板(Accordion)的卡片感 */
.accordion {
    border-radius: 16px !important;
    box-shadow: 0 4px 6px -1px var(--shadow-color, rgba(0,0,0,0.05)) !important;
    border: 1px solid var(--border-color-primary) !important;
    overflow: hidden;
    margin-bottom: 12px !important;
}
/* 输入框圆角与焦点发光 */
input[type="text"], input[type="password"], input[type="number"], textarea {
    border-radius: 10px !important;
    transition: all 0.2s ease !important;
}
input[type="text"]:focus, input[type="password"]:focus, input[type="number"]:focus {
    border-color: var(--color-accent) !important;
    box-shadow: 0 0 0 3px var(--color-accent-subtle) !important;
}
/* 主按钮动效 */
/* 主按钮：果冻粉渐变与动效 */
button.primary {
    border-radius: 14px !important;
    font-weight: 600 !important;
    background: linear-gradient(135deg, var(--primary-400), var(--primary-600)) !important;
    border: none !important;
    color: white !important;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
}
button.primary:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 15px -3px var(--primary-500) !important;
}
button.primary:active { transform: scale(0.97) !important; }
"""


def _make_platform_panel(
    demo,
    raw_config,
    components_map,
    ordered_keys,
    platform_options,
    title,
    platform_key,
    api_key_key,
    url_key_key,
    default_platform,
    platform_reg_name=None,
    api_key_reg_name=None,
    url_reg_name=None,
):
    """创建一个平台配置面板（Accordion），包含平台、Key、URL（条件显示）。"""
    platform_val = raw_config.get("api", {}).get(platform_key, default_platform)
    api_key_val = raw_config.get("api", {}).get(api_key_key, "")
    url_val = raw_config.get("api", {}).get(url_key_key, "")

    # 确保 value 在 choices 中
    dropdown_value = platform_val if platform_val in platform_options else default_platform
    with gr.Accordion(title, open=True, elem_classes="accordion"):
        platform_dd = gr.Dropdown(
            label="平台名称",
            choices=platform_options,
            value=dropdown_value,
        )
        api_key_tb = gr.Textbox(
            label="API Key",
            value=api_key_val,
            type="password",
            max_lines=1,
        )
        url_tb = gr.Textbox(
            label="自定义 API 地址（仅在平台选择 custom 时生效）",
            value=url_val,
            max_lines=1,
        )

    # 注册到映射（使用 _ATTR_MAP 中的字段名，确保保存时能匹配）
    components_map[platform_reg_name or platform_key.upper()] = platform_dd
    components_map[api_key_reg_name or api_key_key.upper()] = api_key_tb
    components_map[url_reg_name or url_key_key.upper()] = url_tb
    ordered_keys.extend([
        platform_reg_name or platform_key.upper(),
        api_key_reg_name or api_key_key.upper(),
        url_reg_name or url_key_key.upper(),
    ])


def build_ui():
    raw_config = load_config()
    components_map = {}
    ordered_keys = []
    platform_options = _get_platform_options()

    # 使用自带的柔和主题，完美支持右上角的 Dark Mode 切换
    theme = gr.themes.Soft(
        primary_hue="pink",  # 主色调：粉色
        secondary_hue="rose",  # 次要色调：玫瑰粉
        neutral_hue="stone",  # 中性底色：偏暖的石灰色（比冷灰色更搭粉色）
        font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"]
    )

    with gr.Blocks(title="Yuki Core Dashboard") as demo:
        gr.Markdown(
            """
            # 🌸 Yuki Core Dashboard
            <span style="color: var(--body-text-color-subdued); font-size: 0.95em;">
            单页配置总览。修改后点击底部保存，主进程将自动完成热重载。
            </span>
            """
        )

        # ================= 基础身份区 =================
        with gr.Accordion("Identity (基础身份)", open=True, elem_classes="accordion"):
            with gr.Row():
                rn = gr.Textbox(
                    label="Robot Name (机器人自称)",
                    value=raw_config.get("robot_name", "Yuki"),
                    max_lines=1,
                    scale=1,
                )
                mn = gr.Textbox(
                    label="Master Name (主人称呼)",
                    value=raw_config.get("master_name", "主人"),
                    max_lines=1,
                    scale=1,
                )
                components_map["robot_name"] = rn
                components_map["master_name"] = mn
                # ================= 瀑布流配置区 =================
                ordered_keys.extend(["robot_name", "master_name"])

        # ================= API 平台配置（三个独立面板） =================
        _make_platform_panel(
            demo, raw_config, components_map, ordered_keys, platform_options,
            title="🤖 首选 LLM 平台",
            platform_key="llm_platform",
            api_key_key="llm_api_key",
            url_key_key="llm_base_url",
            default_platform="deepseek",
        )
        _make_platform_panel(
            demo, raw_config, components_map, ordered_keys, platform_options,
            title="🛡️ 备用 LLM 平台",
            platform_key="backup_platform",
            api_key_key="backup_api_key",
            url_key_key="backup_base_url",
            default_platform="deepseek",
        )
        _make_platform_panel(
            demo, raw_config, components_map, ordered_keys, platform_options,
            title="👁️ 视觉模型平台",
            platform_key="vision_platform",
            api_key_key="image_process_api_key",
            url_key_key="image_process_url",
            default_platform="dashscope",
            url_reg_name="IMAGE_PROCESS_API_URL",
        )

        # ================= 其余配置（自动遍历） =================
        for key, header in _SECTION_HEADERS.items():
            # 先把属于这个 section 的配置项找出来
            current_items = [
                (name, item) for name, item in _ATTR_MAP.items() if item[0][0] == key
            ]
            # 【关键修复】如果列表是空的（比如 robot_name 已经被我们在顶部处理了），直接跳过，不画空壳！
            if not current_items:
                continue

            # api section 已手动处理，跳过
            if key == "api":
                continue

            section_name = header.replace("#", "").replace("=", "").strip()

            with gr.Accordion(f"⚙️ {section_name}", open=True, elem_classes="accordion"):
                for i in range(0, len(current_items), 2):
                    with gr.Row():
                        for j in range(2):
                            if i + j < len(current_items):
                                name, (path, default, comment) = current_items[i + j]
                                val = get_nested(raw_config, path)
                                if val is None:
                                    val = default

                                label = f"{name} {f'({comment})' if comment else ''}"

                                # 根据键名渲染组件
                                if "API_KEY" in name or "TOKEN" in name:
                                    comp = gr.Textbox(
                                        label=label, value=val, type="password", max_lines=1
                                    )
                                elif isinstance(default, bool):
                                    comp = gr.Checkbox(label=label, value=val)
                                elif isinstance(default, int):
                                    comp = gr.Number(label=label, value=val, precision=0)
                                elif isinstance(default, float):
                                    comp = gr.Number(label=label, value=val)
                                else:
                                    comp = gr.Textbox(
                                        label=label,
                                        value=str(val) if val is not None else "",
                                        max_lines=1,
                                    )

                                components_map[name] = comp
                                ordered_keys.append(name)

        # ================= 操作区 =================
        gr.HTML("<br>")
        with gr.Row():
            save_btn = gr.Button(
                "💾 Apply Configuration (保存并热重载)", variant="primary", size="lg"
            )
        status_text = gr.Markdown("")

        # ================= 后台处理逻辑 =================
        def save_config_handler(*args):
            new_config = load_config()
            input_data = dict(zip(ordered_keys, args))

            new_config["robot_name"] = input_data.get("robot_name", "Yuki")
            new_config["master_name"] = input_data.get("master_name", "主人")

            for name, (path, default, _) in _ATTR_MAP.items():
                if name not in input_data: continue
                val = input_data[name]

                if isinstance(default, list) and isinstance(val, str):
                    clean_str = val.strip("[]").replace("'", "").replace('"', "")
                    val = [
                        int(x.strip()) if x.strip().isdigit() else x.strip()
                        for x in clean_str.split(",")
                        if x.strip()
                    ]
                elif isinstance(default, bool):
                    val = bool(val)
                elif isinstance(default, int):
                    val = int(val)
                elif isinstance(default, float):
                    val = float(val)

                set_nested(new_config, path, val)

            # 非 custom 平台自动清空对应的 base_url，避免旧 URL 干扰新平台
            _PLATFORM_URL_MAP = {
                "LLM_PLATFORM": ("LLM_BASE_URL", ("api", "llm_base_url")),
                "BACKUP_PLATFORM": ("BACKUP_BASE_URL", ("api", "backup_base_url")),
                "VISION_PLATFORM": ("IMAGE_PROCESS_API_URL", ("api", "image_process_url")),
            }
            for plat_key, (url_key, url_path) in _PLATFORM_URL_MAP.items():
                plat_val = input_data.get(plat_key, "")
                if plat_val != "custom":
                    set_nested(new_config, url_path, "")

            cfg._raw = new_config
            cfg._save_raw()
            return "### ✨ 写入成功！配置文件已更新，后台热重载已触发。"

        input_components = [components_map[k] for k in ordered_keys]
        save_btn.click(
            fn=save_config_handler, inputs=input_components, outputs=[status_text]
        )

    demo._ui_theme = theme
    demo._ui_css = modern_css
    return demo


if __name__ == "__main__":
    import os

    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
    demo = build_ui()
    # 局域网访问
    demo.launch(
        server_name="127.0.0.1",
        server_port=1314,
        quiet=True,
        theme=demo._ui_theme,
        css=demo._ui_css,
    )
