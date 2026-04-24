import gradio as gr
import yaml
import os
from config import cfg, _ATTR_MAP, _SECTION_HEADERS

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
    # Force reload to get the latest from file
    cfg.reload()
    return cfg._raw

def get_preset(preset_name):
    if preset_name == "Momo（安静）":
        return "Momo", "主人"
    elif preset_name == "Yuki（活泼）":
        return "Yuki", "哥哥大人"
    return cfg.ROBOT_NAME, cfg.MASTER_NAME

def build_ui():
    raw_config = load_config()
    components = {}

    with gr.Blocks(title="Yuki 配置面板") as demo:
        gr.Markdown("## 🤖 智能体配置面板 (实时热重载)")

        with gr.Row():
            btn_momo = gr.Button("🌸 切换为 Momo（安静）")
            btn_yuki = gr.Button("❄️ 切换为 Yuki（活泼）")

        with gr.Tab("核心人设"):
            robot_name = gr.Textbox(label="机器人名字", value=raw_config.get("robot_name", "Yuki"))
            master_name = gr.Textbox(label="主人称呼", value=raw_config.get("master_name", "主人"))
            components["robot_name"] = robot_name
            components["master_name"] = master_name

        btn_momo.click(fn=lambda: get_preset("Momo（安静）"), outputs=[robot_name, master_name])
        btn_yuki.click(fn=lambda: get_preset("Yuki（活泼）"), outputs=[robot_name, master_name])

        sections = {}
        for key, header in _SECTION_HEADERS.items():
            section_name = header.strip("# = ")
            with gr.Tab(section_name):
                for name, (path, default, comment) in _ATTR_MAP.items():
                    if path[0] == key:
                        val = get_nested(raw_config, path)
                        if val is None:
                            val = default

                        label = f"{name} ({comment})" if comment else name

                        # Add specific annotations or password fields
                        if name == "DIARY_IDLE_SECONDS":
                            label += " (秒)"

                        if name in ["LLM_API_KEY", "IMAGE_PROCESS_API_KEY"]:
                            components[name] = gr.Textbox(label=label, value=val, type="password")
                        elif isinstance(default, bool):
                            components[name] = gr.Checkbox(label=label, value=val)
                        elif isinstance(default, int):
                            components[name] = gr.Number(label=label, value=val, precision=0)
                        elif isinstance(default, float):
                            components[name] = gr.Number(label=label, value=val)
                        else:
                            components[name] = gr.Textbox(label=label, value=str(val) if val is not None else "")

        save_btn = gr.Button("💾 保存并热重载配置", variant="primary")
        status_text = gr.Markdown("")

        def save_config_handler(robot, master, *args):
            new_config = load_config()
            new_config["robot_name"] = robot
            new_config["master_name"] = master

            idx = 0
            # Validate API keys before saving
            for name, (path, default, comment) in _ATTR_MAP.items():
                if name in components and name not in ["robot_name", "master_name"]:
                    val = args[idx]

                    # Basic API Key validation
                    if name == "LLM_API_KEY" and val:
                        # Common LLM keys often start with sk- (like DeepSeek, OpenAI)
                        if "dashscope.aliyuncs.com" not in new_config.get("api", {}).get("llm_base_url", "") and "sk-" not in val and len(val) > 10:
                             if not val.startswith("sk-") and not val.startswith("Bearer"):
                                 # We just do a weak check, but let's ensure it's not a URL
                                 if val.startswith("http"):
                                     return f"❌ 保存失败: LLM_API_KEY 格式似乎不正确 (看起来像是一个URL)。请检查是否填串位了。"

                    if name == "IMAGE_PROCESS_API_KEY" and val:
                        if val.startswith("http"):
                            return f"❌ 保存失败: IMAGE_PROCESS_API_KEY 格式似乎不正确 (看起来像是一个URL)。请检查是否填串位了。"

                    # Type conversion
                    if isinstance(default, list):
                        if isinstance(val, str):
                            val = [x.strip() for x in val.strip("[]").replace("'", "").replace("\"", "").split(",") if x.strip()]
                    elif isinstance(default, int):
                        val = int(val)
                    elif isinstance(default, float):
                        val = float(val)

                    set_nested(new_config, path, val)
                    idx += 1

            cfg._raw = new_config
            cfg._save_raw()
            return "✅ 配置已保存，主进程将自动检测并重载！"

        # The inputs must match the order of *args processing
        input_components = [components["robot_name"], components["master_name"]]
        for name in _ATTR_MAP.keys():
            if name in components and name not in ["robot_name", "master_name"]:
                input_components.append(components[name])

        save_btn.click(fn=save_config_handler, inputs=input_components, outputs=[status_text])

    return demo

if __name__ == "__main__":
    demo = build_ui()
    demo.launch(server_name="0.0.0.0", server_port=1314)
