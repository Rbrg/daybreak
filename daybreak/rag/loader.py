"""文档加载：把 knowledge/ 目录下的 .md / .txt / .pdf 读成纯文本。

每个文档返回 (来源标识, 文本)。来源标识用相对路径，最终会作为引用
信息回传给模型，所以保持稳定、可读。
"""

from __future__ import annotations

from pathlib import Path

SUPPORTED_SUFFIXES = {".md", ".txt", ".pdf"}


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_pdf(path: Path) -> str:
    """按页抽取 PDF 文本，页与页之间空行分隔。"""
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(str(path))
    except PdfReadError as exc:
        raise ValueError(f"PDF 解析失败: {exc}") from exc

    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")  # 单页失败不拖垮整篇
    return "\n\n".join(pages)


def load_documents(root: Path) -> list[tuple[str, str]]:
    """递归加载目录下所有支持的文档，返回 [(相对路径, 文本)]。

    目录不存在或没有支持的文档时返回空列表。单个文件读取失败只跳过该文件，
    并在返回前通过调用方无需感知——坏文件不应让整个知识库不可用。
    """
    if not root.is_dir():
        return []

    documents: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        source = path.relative_to(root).as_posix()
        try:
            if path.suffix.lower() == ".pdf":
                text = _read_pdf(path)
            else:
                text = _read_text_file(path)
        except Exception:
            continue
        if text.strip():
            documents.append((source, text))
    return documents
