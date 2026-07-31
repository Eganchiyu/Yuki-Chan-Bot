import os
import sys
import json
import hashlib
import asyncio
from pathlib import Path

import gradio as gr

# 确保从脚本目录运行时也能导入项目根目录模块
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.stickers.manager import StickerManager
from utils.llm_client import close_global_session

# 初始化 Manager（复用现有的视觉 API 请求逻辑）
manager = StickerManager()


# ================= 1. 重命名核心逻辑 =================
def rename_and_get_files(folder_path):
    if not os.path.exists(folder_path):
        return [], "❌ 文件夹不存在，请检查路径！"

    valid_exts = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
    renamed_files = []

    for filename in os.listdir(folder_path):
        ext = os.path.splitext(filename)[1].lower()
        if ext not in valid_exts:
            continue

        old_path = os.path.join(folder_path, filename)

        # 计算 MD5 哈希值以保证文件名绝对唯一
        with open(old_path, 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        new_name = f"{file_hash}{ext}"
        new_path = os.path.join(folder_path, new_name)

        # 执行重命名
        if not os.path.exists(new_path):
            os.rename(old_path, new_path)

        # 保存绝对路径，避免后续路径解析混乱
        renamed_files.append(os.path.abspath(new_path))

    return renamed_files, f"✅ 成功读取并利用 MD5 重命名了 {len(renamed_files)} 张图片。"


# ================= 2. 桥接 AI 自动打标 =================
async def get_ai_labels(image_path):
    try:
        # 复用 manager.py 中的大模型分析逻辑
        analysis = await manager.structured_analysis(image_path)
        if analysis.get("description") == "识别失败":
            print(f"视觉识别失败，请查看上方日志和 configs/config.yaml 中的视觉模型配置: {image_path}")
        return (
            analysis.get("description", ""),
            analysis.get("emotion", "中性"),
            ", ".join(analysis.get("usage_scenarios", [])),
            ", ".join(analysis.get("tags", []))
        )
    except Exception as e:
        print(f"视觉识别异常: {e}")
        return f"识别失败: {e}", "中性", "", ""
    finally:
        await close_global_session()


def run_ai_sync(image_path):
    if not image_path:
        return "", "中性", "", ""
    return asyncio.run(get_ai_labels(image_path))


# ================= 3. UI 交互逻辑 =================
def load_folder(folder_path):
    img_list, msg = rename_and_get_files(folder_path)
    if not img_list:
        return img_list, 0, [], None, "", "中性", "", "", msg, "进度: 0/0"

    # 加载第一张图并请求 AI
    first_img = img_list[0]
    desc, emo, sce, tags = run_ai_sync(first_img)

    return img_list, 0, [], first_img, desc, emo, sce, tags, msg, f"进度: 1/{len(img_list)}"


def save_and_next(img_list, idx, json_data, desc, emo, sce, tags):
    if not img_list or idx >= len(img_list):
        return idx, json_data, None, "", "中性", "", "", "全部完成"

    # 1. 保存当前用户的修正结果
    item = {
        "image_path": img_list[idx],
        "description": desc,
        "emotion": emo,
        "usage_scenarios": [s.strip() for s in sce.split(",") if s.strip()],
        "tags": [t.strip() for t in tags.split(",") if t.strip()]
    }
    json_data.append(item)

    # 2. 步进到下一张
    next_idx = idx + 1
    if next_idx >= len(img_list):
        return next_idx, json_data, None, "", "中性", "", "", "🎉 图片已到底！请点击下方导出 JSON。"

    # 3. 自动请求 AI 识别下一张图
    next_img = img_list[next_idx]
    n_desc, n_emo, n_sce, n_tags = run_ai_sync(next_img)

    return next_idx, json_data, next_img, n_desc, n_emo, n_sce, n_tags, f"进度: {next_idx + 1}/{len(img_list)}"


def export_to_json(json_data):
    if not json_data:
        return "⚠️ 没有可导出的数据！"
    save_path = os.path.abspath("manual_stickers.json")
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    return f"💾 成功导出 {len(json_data)} 条打标数据到：\n{save_path}"


# ================= 4. Gradio 界面组装 =================
with gr.Blocks(title="Yuki 表情包可视化打标工厂", theme=gr.themes.Soft()) as demo:
    gr.Markdown("## 📦 Yuki 表情包可视化打标工厂")

    # 隐藏的状态存储
    state_img_list = gr.State([])
    state_current_idx = gr.State(0)
    state_json_data = gr.State([])

    with gr.Row():
        folder_input = gr.Textbox(label="输入装有野生表情包的文件夹路径", placeholder="例如: ./raw_images", scale=4)
        load_btn = gr.Button("1. 重命名并加载", variant="primary", scale=1)

    status_box = gr.Textbox(label="系统日志", interactive=False)

    with gr.Row():
        # 左侧：看图区
        with gr.Column(scale=1):
            img_display = gr.Image(type="filepath", label="当前表情", interactive=False)
            progress_text = gr.Markdown("进度: 0/0")

        # 右侧：打标区
        with gr.Column(scale=1):
            desc_input = gr.Textbox(label="核心描述 (description)", lines=2)
            emo_dropdown = gr.Dropdown(
                choices=["撒娇", "吐槽", "无语", "生气", "开心", "委屈", "调情", "震惊", "摸鱼", "高冷", "抽象",
                         "群内梗", "中性"],
                label="主要情绪 (emotion)"
            )
            scenarios_input = gr.Textbox(label="使用场景 (usage_scenarios) - 逗号分隔",
                                         placeholder="例如: 群友发癫, 代码报错")
            tags_input = gr.Textbox(label="标签 (tags) - 逗号分隔", placeholder="例如: 猫, 拍桌子, 愤怒")

            with gr.Row():
                ai_btn = gr.Button("🤖 让大模型重新猜一下")
                next_btn = gr.Button("✅ 保存修改，并进入下一张", variant="primary")

    gr.Markdown("---")
    export_btn = gr.Button("💾 2. 导出所有数据为 manual_stickers.json", size="lg")

    # 绑定事件
    load_btn.click(
        fn=load_folder,
        inputs=[folder_input],
        outputs=[state_img_list, state_current_idx, state_json_data, img_display, desc_input, emo_dropdown,
                 scenarios_input, tags_input, status_box, progress_text]
    )

    ai_btn.click(
        fn=run_ai_sync,
        inputs=[img_display],
        outputs=[desc_input, emo_dropdown, scenarios_input, tags_input]
    )

    next_btn.click(
        fn=save_and_next,
        inputs=[state_img_list, state_current_idx, state_json_data, desc_input, emo_dropdown, scenarios_input,
                tags_input],
        outputs=[state_current_idx, state_json_data, img_display, desc_input, emo_dropdown, scenarios_input, tags_input,
                 progress_text]
    )

    export_btn.click(fn=export_to_json, inputs=[state_json_data], outputs=[status_box])

if __name__ == "__main__":
    import os

    print("正在启动打标 UI 工具...")

    # 获取项目根目录，或者直接硬编码你的绝对路径
    demo.launch(
        inbrowser=True,
        allowed_paths=[
            "D:/Projects/YukiV6",  # 放行整个项目根目录
            "D:/Projects/YukiV6/data/stickers"  # 精准放行表情包目录
        ]
    )