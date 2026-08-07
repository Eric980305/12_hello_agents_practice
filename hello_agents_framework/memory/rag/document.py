"""Validated source-document contracts and deterministic text splitting."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..base import utc_now


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    namespace: str = Field(min_length=1)
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("id", "namespace", "content")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class DocumentChunk(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    namespace: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    index: int = Field(ge=0)
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentProcessor:
    """Split normalized Markdown/text on headings, paragraphs, and token budgets."""

    def __init__(self, *, chunk_size: int = 800, chunk_overlap: int = 100) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive.")
        if not 0 <= chunk_overlap < chunk_size:
            raise ValueError("chunk_overlap must be between 0 and chunk_size - 1.")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split(self, document: Document) -> list[DocumentChunk]:
        text = "\n".join(
            line.rstrip() for line in document.content.replace("\r\n", "\n").split("\n")
        ).strip()
        if not text:
            return []
        paragraphs = self._split_paragraphs_with_headings(text)
        grouped = self._chunk_paragraphs(paragraphs)
        return [
            DocumentChunk(
                id=str(
                    uuid5(
                        NAMESPACE_URL,
                        f"{document.namespace}:{document.id}:{index}",
                    )
                ),
                namespace=document.namespace,
                document_id=document.id,
                index=index,
                content=chunk["content"],
                metadata={
                    **document.metadata,
                    "heading_path": chunk["heading_path"],
                    "start": chunk["start"],
                    "end": chunk["end"],
                },
            )
            for index, chunk in enumerate(grouped)
        ]

    @staticmethod
    def text_for_embedding(chunk: DocumentChunk) -> str:
        """Include structural context in vectors without altering source excerpts."""
        heading_path = chunk.metadata.get("heading_path")
        if isinstance(heading_path, str) and heading_path:
            return f"{heading_path}\n\n{chunk.content}"
        return chunk.content

    def _split_paragraphs_with_headings(self, text: str) -> list[dict[str, Any]]:
        paragraphs: list[dict[str, Any]] = []
        heading_stack: list[str] = []
        buffer: list[str] = []
        buffer_start = 0
        buffer_heading: str | None = None
        position = 0

        def flush(end: int) -> None:
            nonlocal buffer
            content = "\n".join(buffer).strip()
            if content:
                paragraphs.append(
                    {
                        "content": content,
                        "heading_path": buffer_heading,
                        "start": buffer_start,
                        "end": end,
                    }
                )
            buffer = []

        for line in text.splitlines(keepends=True):
            raw = line.rstrip("\r\n")
            heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", raw.strip())
            if heading:
                flush(position)
                level = len(heading.group(1))
                heading_stack = heading_stack[: level - 1]
                heading_stack.append(heading.group(2))
            elif not raw.strip():
                flush(position)
            else:
                if not buffer:
                    buffer_start = position
                    buffer_heading = " > ".join(heading_stack) or None
                buffer.append(raw)
            position += len(line)
        flush(len(text))
        return paragraphs or [
            {
                "content": text,
                "heading_path": None,
                "start": 0,
                "end": len(text),
            }
        ]

    def _chunk_paragraphs(
        self,
        paragraphs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        current: list[dict[str, Any]] = []
        current_tokens = 0

        def append_current() -> None:
            if not current:
                return
            chunks.append(
                {
                    "content": "\n\n".join(part["content"] for part in current),
                    "heading_path": current[-1]["heading_path"],
                    "start": current[0]["start"],
                    "end": current[-1]["end"],
                }
            )

        for paragraph in paragraphs:
            paragraph_tokens = self._approx_token_len(paragraph["content"])
            heading_changed = bool(
                current
                and paragraph["heading_path"] != current[-1]["heading_path"]
            )
            budget_exceeded = bool(
                current and current_tokens + paragraph_tokens > self.chunk_size
            )
            if heading_changed or budget_exceeded:
                append_current()
                overlap = [] if heading_changed else self._overlap_tail(current)
                current = overlap
                current_tokens = sum(
                    self._approx_token_len(part["content"]) for part in current
                )
                if current and current_tokens + paragraph_tokens > self.chunk_size:
                    current = []
                    current_tokens = 0
            current.append(paragraph)
            current_tokens += paragraph_tokens
        append_current()
        return chunks

    def _overlap_tail(
        self,
        paragraphs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if self.chunk_overlap == 0:
            return []
        kept: list[dict[str, Any]] = []
        kept_tokens = 0
        for paragraph in reversed(paragraphs):
            tokens = self._approx_token_len(paragraph["content"])
            if kept_tokens + tokens > self.chunk_overlap:
                break
            kept.append(paragraph)
            kept_tokens += tokens
        return list(reversed(kept))

    @classmethod
    def _approx_token_len(cls, text: str) -> int:
        cjk_count = sum(1 for character in text if cls._is_cjk(character))
        non_cjk = "".join(
            " " if cls._is_cjk(character) else character for character in text
        )
        other_tokens = len(re.findall(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_]", non_cjk))
        return max(1, cjk_count + other_tokens)

    @staticmethod
    def _is_cjk(character: str) -> bool:
        code = ord(character)
        return (
            0x3400 <= code <= 0x4DBF
            or 0x4E00 <= code <= 0x9FFF
            or 0xF900 <= code <= 0xFAFF
            or 0x20000 <= code <= 0x2CEAF
        )

    def load_file(
        self,
        file_path: str | Path,
        *,
        namespace: str,
        document_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> Document:
        """Convert one knowledge-base file to Markdown/text for chunking."""
        path = Path(file_path)
        suffix = path.suffix.casefold()
        if suffix == ".pdf":
            content = self._read_pdf(path)
        elif suffix in {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}:
            content = self._ocr_image(path)
        elif suffix in {".txt", ".md", ".markdown"}:
            content = path.read_text(encoding="utf-8")
        else:
            try:
                from markitdown import MarkItDown
            except ImportError as error:
                raise RuntimeError(
                    "MarkItDown is required for non-text knowledge files."
                ) from error
            try:
                result = MarkItDown().convert(str(path))
            except Exception as error:
                raise ValueError(
                    f"无法解析 {suffix or '未知'} 文件；文件可能损坏或转换依赖不可用。"
                ) from error
            content = getattr(result, "text_content", None)
            if not isinstance(content, str) or not content.strip():
                raise ValueError(f"no text could be extracted from '{path.name}'.")
        source_metadata = dict(metadata or {})
        source_metadata.update(
            {
                "source_path": str(path),
                "source_name": path.name,
                "source_type": suffix.lstrip(".") or "unknown",
            }
        )
        return Document(
            id=document_id,
            namespace=namespace,
            content=content,
            metadata=source_metadata,
        )

    @staticmethod
    def _read_pdf(path: Path) -> str:
        """Extract searchable PDF text with the project's installed PDF reader."""
        from pypdf import PdfReader

        sections: list[str] = []
        for page_number, page in enumerate(PdfReader(path).pages, start=1):
            text = page.extract_text()
            if isinstance(text, str) and text.strip():
                sections.append(f"## Page {page_number}\n\n{text.strip()}")
        if not sections:
            return DocumentProcessor._ocr_pdf(path)
        return "\n\n".join(sections)

    @staticmethod
    def _ocr_pdf(path: Path) -> str:
        if shutil.which("pdftoppm") is None:
            raise ValueError("扫描版 PDF OCR 需要本机安装 Poppler（pdftoppm）。")
        with tempfile.TemporaryDirectory(prefix="hello-agents-ocr-") as directory:
            prefix = Path(directory) / "page"
            try:
                subprocess.run(
                    ["pdftoppm", "-png", "-r", "150", str(path), str(prefix)],
                    check=True,
                    capture_output=True,
                    timeout=300,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                raise ValueError("扫描版 PDF 转换为 OCR 图像失败。") from error
            sections = []
            for page_number, image_path in enumerate(
                sorted(Path(directory).glob("page-*.png")),
                start=1,
            ):
                text = DocumentProcessor._ocr_image(image_path)
                if text.strip():
                    sections.append(f"## Page {page_number}\n\n{text.strip()}")
        if not sections:
            raise ValueError("扫描版 PDF 已执行 OCR，但没有识别到可搜索文字。")
        return "\n\n".join(sections)

    @staticmethod
    def _ocr_image(path: Path) -> str:
        if shutil.which("tesseract") is None:
            raise ValueError("图片文字识别需要本机安装 Tesseract OCR。")
        try:
            languages = subprocess.run(
                ["tesseract", "--list-langs"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.splitlines()
            if "chi_sim" not in languages:
                raise ValueError(
                    "中文 OCR 需要安装 Tesseract 简体中文语言包 chi_sim。"
                )
            result = subprocess.run(
                [
                    "tesseract",
                    str(path),
                    "stdout",
                    "-l",
                    "chi_sim",
                    "--psm",
                    "6",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            raise ValueError("图片 OCR 执行失败。") from error
        if not result.stdout.strip():
            raise ValueError("图片已执行 OCR，但没有识别到可搜索文字。")
        return re.sub(
            r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])",
            "",
            result.stdout.strip(),
        )


__all__ = ["Document", "DocumentChunk", "DocumentProcessor"]
