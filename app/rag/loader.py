"""
Day 1: 统一文档加载器
支持 PDF / Word / TXT → 返回纯文本
"""
from pathlib import Path
from app.common.logger import logger


def load_pdf(file_path: str) -> str:
    """PDF → Markdown → 纯文本"""
    from langchain_mineru import MinerULoader
    loader = MinerULoader(source=file_path, mode="flash")
    docs = loader.load()
    return "\n\n".join(d.page_content for d in docs)


def load_docx(file_path: str) -> str:
    """.docx → 纯文本"""
    from docx import Document
    doc = Document(file_path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def load_doc(file_path: str) -> str:
    """.doc (旧版二进制) → 纯文本"""
    import olefile
    ole = olefile.OleFileIO(file_path)
    # .doc 的文字存在 WordDocument 流中
    if ole.exists("WordDocument"):
        stream = ole.openstream("WordDocument")
        raw = stream.read()
        # 提取可打印字符（跳过二进制包头）
        text = "".join(chr(b) for b in raw if 31 < b < 127 or b in (10, 13))
        # 过滤太短的片段，保留文字内容
        lines = [l.strip() for l in text.split("\n") if len(l.strip()) > 2]
        ole.close()
        return "\n".join(lines)
    ole.close()
    # 备用：读摘要信息
    return ""


def load_txt(file_path: str) -> str:
    """TXT → 文本（自动检测编码 GBK/UTF-8）"""
    for encoding in ["utf-8", "gbk", "gb2312"]:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise ValueError(f"无法识别文件编码: {file_path}")


def load_document(file_path: str) -> str:
    """统一入口：自动识别格式 → 返回文本"""
    ext = Path(file_path).suffix.lower()
    logger.info(f"Loading document: {file_path} ({ext})")

    if ext == ".pdf":
        return load_pdf(file_path)
    elif ext == ".docx":
        return load_docx(file_path)
    elif ext == ".doc":
        return load_doc(file_path)
    elif ext == ".txt":
        return load_txt(file_path)
    else:
        raise ValueError(f"不支持的文件格式: {ext}")
