# scripts/clear_stickers.py
import chromadb
from config import cfg

client = chromadb.PersistentClient(path=cfg.VECTOR_DB_PATH)
client.delete_collection("stickers")
print("stickers collection 已完全清空")