# scripts/clear_stickers.py
import chromadb
from config import VECTOR_DB_PATH

client = chromadb.PersistentClient(path=VECTOR_DB_PATH)
client.delete_collection("stickers")
print("stickers collection 已完全清空")