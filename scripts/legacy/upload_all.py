"""Python 批量上传文档（UTF-8 正确编码）"""
import os
import requests

API = "http://localhost:8001/api/v1"
DOC_DIR = "documents"

files = sorted([f for f in os.listdir(DOC_DIR) if f.endswith(('.txt','.pdf','.docx','.doc'))])
total = len(files)
print(f"共 {total} 个文件\n")

for i, fname in enumerate(files, 1):
    path = os.path.join(DOC_DIR, fname)
    try:
        with open(path, "rb") as f:
            resp = requests.post(f"{API}/upload", files={"file": (fname, f)})
        data = resp.json()
        msg = data.get("message", "")
        print(f"[{i:3d}/{total}] {fname[:70]}  {msg}")
    except Exception as e:
        print(f"[{i:3d}/{total}] {fname[:70]}  FAIL: {e}")

print(f"\nDone! {total} files")
