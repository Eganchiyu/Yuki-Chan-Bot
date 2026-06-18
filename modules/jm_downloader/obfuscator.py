"""文件混淆器 — 将 PDF 混淆为不可识别的二进制文件

算法：魔术头替换 + XOR + 相邻字节交换
解密器：GitHub Pages 静态网页 (decoder.html)

用法：
    from modules.jm_downloader.obfuscator import obfuscate_file, deobfuscate_file
    key = obfuscate_file("input.pdf", "output.dat")
    deobfuscate_file("output.dat", "restored.pdf", key)
"""
import os
import random
import string
import logging

logger = logging.getLogger("jm_cli.obfuscator")

# PDF 魔术头 %PDF
_PDF_MAGIC = b"%PDF"

def _generate_key(length: int = 8) -> str:
    """生成随机 key（字母数字）"""
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


def _key_to_bytes(key: str) -> bytes:
    """key 字符串转字节序列（循环使用）"""
    return key.encode("utf-8")


def obfuscate_file(input_path: str, output_path: str, key: str = None) -> str:
    """混淆文件，返回使用的 key
    
    算法步骤：
    1. 读取原始字节
    2. 替换前4字节魔术头（%PDF → 随机字节）
    3. XOR 每个字节（循环使用 key）
    4. 相邻字节两两交换
    5. 写出混淆文件
    """
    if key is None:
        key = _generate_key()

    with open(input_path, "rb") as f:
        data = bytearray(f.read())

    key_bytes = _key_to_bytes(key)
    key_len = len(key_bytes)

    # Step 1: 替换魔术头（前4字节）
    magic_mask = bytes([random.randint(1, 255) for _ in range(4)])
    for i in range(min(4, len(data))):
        data[i] ^= magic_mask[i]

    # Step 2: XOR 每个字节
    for i in range(len(data)):
        data[i] ^= key_bytes[i % key_len]

    # Step 3: 相邻字节两两交换
    for i in range(0, len(data) - 1, 2):
        data[i], data[i + 1] = data[i + 1], data[i]

    # 写出：8字节头部 = 4字节 magic_mask + 4字节原始文件大小的低4位校验
    with open(output_path, "wb") as f:
        f.write(magic_mask)
        f.write(len(data).to_bytes(4, "little"))
        f.write(data)

    logger.info(f"🔒 混淆完成: {os.path.getsize(input_path)} → {os.path.getsize(output_path)} bytes, key={key}")
    return key


def deobfuscate_file(input_path: str, output_path: str, key: str) -> bool:
    """反混淆，恢复原始文件"""
    with open(input_path, "rb") as f:
        magic_mask = f.read(4)
        size_bytes = f.read(4)
        data = bytearray(f.read())

    key_bytes = _key_to_bytes(key)
    key_len = len(key_bytes)

    # 逆步骤 3: 再次两两交换（自逆操作）
    for i in range(0, len(data) - 1, 2):
        data[i], data[i + 1] = data[i + 1], data[i]

    # 逆步骤 2: XOR
    for i in range(len(data)):
        data[i] ^= key_bytes[i % key_len]

    # 逆步骤 1: 恢复魔术头
    for i in range(min(4, len(data))):
        data[i] ^= magic_mask[i]

    with open(output_path, "wb") as f:
        f.write(data)

    logger.info(f"🔓 反混淆完成: {os.path.getsize(input_path)} → {os.path.getsize(output_path)} bytes")
    return True
