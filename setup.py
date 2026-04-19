import os
import shutil
import subprocess
import sys
from dotenv import load_dotenv, set_key

# uv 环境提示：如果检测到 uv 但未在虚拟环境中运行，给出友好提示
if shutil.which("uv") and sys.prefix == sys.base_prefix:
    venv_python = os.path.join(".venv", "Scripts", "python.exe") if sys.platform == "win32" else os.path.join(".venv", "bin", "python")
    if os.path.exists(venv_python):
        print("💡 检测到 uv 虚拟环境存在，但未激活。")
        print("   请使用以下命令运行 setup.py：")
        print(f"   uv run python setup.py")
        print("   或先激活虚拟环境后再运行。\n")

def ensure_dirs():
    """确保必要的文件夹存在"""
    dirs = ["./models", "./data", "./yuki_memory", "./logs"]
    for d in dirs:
        if not os.path.exists(d):
            os.makedirs(d)
            print(f"已创建文件夹: {d}")

def ensure_files():
    """确保必要的文件存在并有初始内容"""
    # 1. 自动生成初始黑名单
    if not os.path.exists("blacklist.txt"):
        with open("blacklist.txt", "w", encoding="utf-8") as f:
            # 写入你之前文件里提到的默认过滤词
            f.write("yuki\n主人\n哥哥\n池宇健\n人家")
        print("已生成初始 blacklist.txt")
    else:
        print("📝 已存在 blacklist.txt，跳过")

    # 2. 自动生成 .gitignore 防止误传密钥
    if not os.path.exists(".gitignore"):
        with open(".gitignore", "w", encoding="utf-8") as f:
            f.write(".env\n__pycache__/\n*.log\nmodels/\n/yuki_memory/\n.vscode/")
        print("🛡️ 已生成 .gitignore（保护你的 API Key）")
    else:
        print("已存在 blacklist.txt，跳过")

def install_requirements():
    """自动安装依赖（优先使用 uv，回退到 pip）"""
    if input("\n是否现在安装/更新依赖插件? (y/n): ").lower() != 'y':
        return

    has_uv = shutil.which("uv") is not None
    try:
        if has_uv:
            print("🚀 检测到 uv，使用 uv 安装依赖...")
            subprocess.check_call(["uv", "sync"])
            print("✅ 依赖安装完成（via uv）")
        else:
            print("📦 未检测到 uv，使用 pip 安装依赖...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
            print("✅ 依赖安装完成（via pip）")
    except Exception as e:
        print(f"❌ 依赖安装失败\n错误: {e}")
        print("💡 建议手动执行: uv sync  或  pip install -r requirements.txt")

def config_env_key(mode):
    env_path = ".env"
    if not os.path.exists(env_path):
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("# Yuki-Chan Configuration\n")

    keys_to_configure = [
        ("LLM_API_KEY", "请输入首选 LLM API Key: ", ""),
        ("BACKUP_API_KEY", "请输入备选 LLM API Key: （未选择的话可以继续用上面的）", ""),
        ("IMAGE_PROCESS_API_KEY", "请输入 图像处理 API Key: ", ""),
        ("NAPCAT_WS_URL", "请输入 NapCat WebSocket 地址 (默认: ws://127.0.0.1:3001): ", "ws://127.0.0.1:3001")
    ]

    for key, prompt, default in keys_to_configure:
        load_dotenv()
        if mode == 1 or not os.getenv(key):
            value = input(prompt).strip()
            save_value = value if value else default
            if save_value:
                set_key(env_path, key, save_value)
                print(f"{key} 已保存: {save_value}")
        else:
            print(f"{key} 已存在，跳过(模式: 刷新)")


def config_bot_settings(mode):
    """配置机器人身份及目标对话对象"""
    env_path = ".env"
    settings = [
        ("ROBOT_NAME", "给BOT起个名字吧："),
        ("MASTER_NAME", "希望BOT称呼你的名字："),
        ("TARGET_QQ", "请输入私聊用 QQ 号: "),
        ("TARGET_GROUPS", "请输入目标群聊 QQ 号 (多个用逗号隔开): ")
    ]

    for key, prompt in settings:
        load_dotenv()
        # 修改点：同上
        if mode == 1 or not os.getenv(key):
            value = input(prompt).strip()
            if value:
                set_key(env_path, key, value)
                print(f"{key} 已设置")
        else:
            print(f"{key} 已存在，跳过")

def quick_setup(mode):
    print("\n>>> 步骤 1: 建立文件夹结构")
    ensure_dirs()
    ensure_files()
    # 建立黑名单等必要文件
    if not os.path.exists("blacklist.txt"):
        with open("blacklist.txt", "w", encoding="utf-8") as f: f.write("")

    print("\n>>> 步骤 2: 安装依赖文件")
    install_requirements()

    print("\n>>> 步骤 3: 配置 API 密钥")
    config_env_key(mode)

    print("\n>>> 步骤 4: 配置机器人 QQ 号")
    config_bot_settings(mode)

    # 2. 配置 RAG 嵌入模型
    print("\n>>> 步骤 5: 下载 RAG 嵌入模型")
    try:
        from utils.download_model import download_model
        download_model()
    except ImportError as e:
        print(f"⚠️ 依赖未安装，跳过模型下载: {e}")
        print("   请确保已运行 'uv sync' 或 'pip install -r requirements.txt'")
    except Exception as e:
        print(f"模型下载环节出现问题: {e}")


if __name__ == "__main__":
    print("开始配置必要参数和环境")
    try:
        user_input = input("输入配置方式（刷新（跳过已存在）和写入（全部覆盖））[默认 0]: ").strip()
        current_mode = int(user_input) if user_input else 0
    except ValueError:
        current_mode = 0

    quick_setup(current_mode)

    print("向导结束，请到config.py文件中手动修改使用模型名称和请求地址！")