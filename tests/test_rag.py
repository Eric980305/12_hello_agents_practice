import json
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from qdrant_client import QdrantClient

from hello_agents_practice import (
    LLMQueryExpander,
    QdrantVectorStore,
    RAGPipeline,
    RAGTool,
    SQLiteKnowledgeStore,
    ToolRegistry,
)
from hello_agents_practice.memory.rag import Document, DocumentProcessor


class FakeEmbedder:
    dimension = 3

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.batch_calls: list[list[str]] = []

    def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        normalized = text.casefold()
        vector = [
            float("python" in normalized),
            float("机器学习" in normalized),
            float("rag" in normalized or "检索" in normalized),
        ]
        length = math.sqrt(sum(value * value for value in vector))
        return [value / length for value in vector] if length else [0.0, 0.0, 0.0]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        self.batch_calls.append(list(texts))
        return [self.embed(text) for text in texts]


class FakeQueryExpander:
    def __init__(self) -> None:
        self.mqe_calls: list[tuple[str, int]] = []
        self.hyde_calls: list[str] = []

    def expand(self, query: str, count: int) -> list[str]:
        self.mqe_calls.append((query, count))
        return ["Python 入门教程", "python 入门教程"]

    def hypothetical_document(self, query: str) -> str:
        self.hyde_calls.append(query)
        return "Python 是一种适合入门学习的编程语言。"


class FakeLLM:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)

    def invoke(self, messages: list[dict[str, str]]) -> str:
        return self.responses.pop(0)


class RAGPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "knowledge.db"
        self.documents = SQLiteKnowledgeStore(self.database_path)
        self.vectors = QdrantVectorStore(
            collection_name="rag_test",
            vector_size=3,
            client=QdrantClient(":memory:"),
        )
        self.embedder = FakeEmbedder()
        self.pipeline = RAGPipeline(
            namespace="test",
            document_store=self.documents,
            vector_store=self.vectors,
            embedder=self.embedder,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_indexes_retrieves_sources_and_persists_stats(self) -> None:
        self.pipeline.add_text(
            text="Python 由 Guido van Rossum 于 1991 年首次发布。",
            document_id="python_intro",
            metadata={"source": "textbook"},
        )
        self.pipeline.add_text(
            text="机器学习包括监督学习、无监督学习和强化学习。",
            document_id="ml_basics",
        )
        self.pipeline.add_text(
            text="RAG 通过检索外部知识增强生成。",
            document_id="rag_concept",
        )

        results = self.pipeline.search(
            query="Python 编程语言历史",
            limit=3,
            min_score=0.1,
        )
        reloaded_stats = SQLiteKnowledgeStore(self.database_path).stats(
            namespace="test"
        )

        self.assertEqual(results[0].document_id, "python_intro")
        self.assertEqual(results[0].metadata["source"], "textbook")
        self.assertEqual(results[0].metadata["start"], 0)
        self.assertGreater(results[0].metadata["end"], 0)
        self.assertEqual(reloaded_stats, {"documents": 3, "chunks": 3})

    def test_persists_user_scoped_knowledge_base_catalog(self) -> None:
        self.documents.ensure_knowledge_base(
            user_id="alice",
            knowledge_base_id="legal",
            name="法律法规",
            namespace="kb_alice_legal",
        )
        self.documents.ensure_knowledge_base(
            user_id="alice",
            knowledge_base_id="legal",
            name="法律法规",
            namespace="kb_alice_legal",
        )

        alice = self.documents.list_knowledge_bases(user_id="alice")
        bob = self.documents.list_knowledge_bases(user_id="bob")

        self.assertEqual(alice, [{
            "id": "legal",
            "name": "法律法规",
            "namespace": "kb_alice_legal",
        }])
        self.assertEqual(bob, [])

    def test_replacement_is_idempotent_and_namespaces_are_isolated(self) -> None:
        self.assertFalse(self.pipeline.has_document("intro"))
        self.pipeline.add_text(text="Python old", document_id="intro")
        self.assertTrue(self.pipeline.has_document("intro"))
        self.pipeline.add_text(text="Python updated", document_id="intro")
        other = RAGPipeline(
            namespace="other",
            document_store=self.documents,
            vector_store=self.vectors,
            embedder=FakeEmbedder(),
        )
        other.add_text(text="Python private namespace", document_id="private")

        results = self.pipeline.search(query="Python", limit=5)

        self.assertEqual(self.pipeline.stats()["documents"], 1)
        self.assertEqual(len(results), 1)
        self.assertIn("updated", results[0].content)
        self.assertNotIn("private", results[0].content)

    def test_lists_and_deletes_authoritative_document_and_vectors(self) -> None:
        self.pipeline.add_text(
            text="Python knowledge",
            document_id="python",
            metadata={"original_name": "python.md", "source_type": "md"},
        )
        chunk_id = self.documents.get_chunk_ids(
            namespace="test",
            document_id="python",
        )[0]

        listed = self.pipeline.list_documents()
        removed = self.pipeline.delete_document("python")

        self.assertEqual(listed[0]["name"], "python.md")
        self.assertEqual(listed[0]["source_type"], "md")
        self.assertEqual(listed[0]["chunk_count"], 1)
        self.assertEqual(removed["document_id"], "python")
        self.assertFalse(self.pipeline.has_document("python"))
        self.assertEqual(self.pipeline.stats()["documents"], 0)
        self.assertEqual(
            self.vectors.client.retrieve(
                collection_name=self.vectors.collection_name,
                ids=[chunk_id],
            ),
            [],
        )

    def test_tool_uses_registry_path_and_reports_sources(self) -> None:
        registry = ToolRegistry()
        tool = RAGTool(
            knowledge_base_path=self.temporary_directory.name,
            rag_namespace="test",
            pipeline=self.pipeline,
        )
        registry.register_tool(tool)

        added = registry.execute_tool(
            "rag",
            {
                "action": "add_text",
                "text": "RAG combines retrieval and generation.",
                "document_id": "rag_en",
            },
        )
        searched = tool.execute("search", query="RAG retrieval", min_score="0.1")
        stats = json.loads(tool.execute("stats"))

        self.assertIn("chunks=1", added)
        self.assertIn("source=rag_en", searched)
        self.assertEqual(stats["documents"], 1)
        with self.assertRaises(ValueError):
            tool.execute("missing")

    def test_knowledge_base_path_ingests_files_and_blocks_traversal(self) -> None:
        knowledge_base = Path(self.temporary_directory.name) / "knowledge_base"
        knowledge_base.mkdir()
        source = knowledge_base / "python.md"
        source.write_text("Python first appeared in 1991.", encoding="utf-8")
        html_source = knowledge_base / "rag.html"
        html_source.write_text(
            "<html><body><h1>RAG</h1><p>Retrieval augments generation.</p></body></html>",
            encoding="utf-8",
        )
        tool = RAGTool(
            knowledge_base_path=str(knowledge_base),
            rag_namespace="test",
            pipeline=self.pipeline,
        )

        added = tool.execute("add_document", file_path="python.md")
        converted = tool.execute("add_document", file_path="rag.html")
        searched = tool.execute("search", query="Python history")
        stats = json.loads(tool.execute("stats"))

        self.assertIn("source=python.md", added)
        self.assertIn("source=rag.html", converted)
        self.assertIn("source=python.md", searched)
        self.assertEqual(stats["documents"], 2)
        self.assertEqual(stats["knowledge_base_path"], str(knowledge_base.resolve()))
        with self.assertRaises(PermissionError):
            tool.execute("add_document", file_path="../outside.md")

    def test_basic_search_does_not_use_configured_query_expander(self) -> None:
        expander = FakeQueryExpander()
        self.pipeline.query_expander = expander
        self.pipeline.add_text(text="Python basics", document_id="python")

        self.pipeline.search(query="Python", min_score=0.1)

        self.assertEqual(expander.mqe_calls, [])
        self.assertEqual(expander.hyde_calls, [])

    def test_indexes_all_document_chunks_through_one_batch_boundary(self) -> None:
        pipeline = RAGPipeline(
            namespace="batch",
            document_store=self.documents,
            vector_store=self.vectors,
            embedder=self.embedder,
            processor=DocumentProcessor(chunk_size=4, chunk_overlap=0),
        )

        result = pipeline.add_text(
            text="\n\n".join(f"Python paragraph {index}" for index in range(20)),
            document_id="batch-doc",
        )

        self.assertGreater(result["chunks_indexed"], 1)
        self.assertEqual(len(self.embedder.batch_calls), 1)
        self.assertEqual(len(self.embedder.batch_calls[0]), result["chunks_indexed"])

    def test_mqe_and_hyde_expand_merge_and_deduplicate_candidates(self) -> None:
        expander = FakeQueryExpander()
        self.pipeline.query_expander = expander
        self.pipeline.add_text(text="Python basics", document_id="python")
        self.embedder.calls.clear()

        results = self.pipeline.search(
            query="如何开始编程",
            limit=3,
            min_score=0.1,
            enable_mqe=True,
            mqe_expansions=2,
            enable_hyde=True,
        )

        self.assertEqual([result.document_id for result in results], ["python"])
        self.assertEqual(expander.mqe_calls, [("如何开始编程", 2)])
        self.assertEqual(expander.hyde_calls, ["如何开始编程"])
        self.assertEqual(
            self.embedder.calls,
            [
                "如何开始编程",
                "Python 入门教程",
                "Python 是一种适合入门学习的编程语言。",
            ],
        )

    def test_advanced_search_requires_an_expander(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "query expander"):
            self.pipeline.search(query="Python", enable_mqe=True)

    def test_tool_forwards_advanced_search_options(self) -> None:
        self.pipeline.query_expander = FakeQueryExpander()
        tool = RAGTool(
            knowledge_base_path=self.temporary_directory.name,
            rag_namespace="test",
            pipeline=self.pipeline,
        )
        tool.execute("add_text", text="Python basics", document_id="python")

        result = tool.execute(
            "search",
            query="如何开始编程",
            min_score=0.1,
            enable_mqe=True,
            enable_hyde=True,
        )

        self.assertIn("source=python", result)


class LLMQueryExpanderTest(unittest.TestCase):
    def test_parses_mqe_lines_and_returns_hypothetical_document(self) -> None:
        expander = LLMQueryExpander(
            FakeLLM([
                "1. Python 入门教程\n- Python 学习路线\n额外内容",
                "  Python 是一种通用编程语言。  ",
            ])
        )

        queries = expander.expand("如何学习 Python", 2)
        hypothetical = expander.hypothetical_document("如何学习 Python")

        self.assertEqual(queries, ["Python 入门教程", "Python 学习路线"])
        self.assertEqual(hypothetical, "Python 是一种通用编程语言。")


class DocumentProcessorTest(unittest.TestCase):
    def test_image_uses_installed_tesseract_ocr_boundary(self) -> None:
        processor = DocumentProcessor()
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "scan.png"
            path.write_bytes(b"PNG")
            with (
                patch(
                    "hello_agents_practice.memory.rag.document.shutil.which",
                    return_value="/opt/homebrew/bin/tesseract",
                ),
                patch(
                    "hello_agents_practice.memory.rag.document.subprocess.run",
                    side_effect=[
                        SimpleNamespace(stdout="eng\nchi_sim\n"),
                        SimpleNamespace(stdout="识别出的 合同 条款"),
                    ],
                ) as run,
            ):
                document = processor.load_file(
                    path,
                    namespace="test",
                    document_id="scan",
                )

        self.assertEqual(document.content, "识别出的合同条款")
        self.assertIn("chi_sim", run.call_args_list[1].args[0])
        self.assertIn("--psm", run.call_args_list[1].args[0])

    def test_image_requires_simplified_chinese_ocr_language_data(self) -> None:
        processor = DocumentProcessor()
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "scan.png"
            path.write_bytes(b"PNG")
            with (
                patch(
                    "hello_agents_practice.memory.rag.document.shutil.which",
                    return_value="/opt/homebrew/bin/tesseract",
                ),
                patch(
                    "hello_agents_practice.memory.rag.document.subprocess.run",
                    return_value=SimpleNamespace(stdout="eng\n"),
                ) as run,
            ):
                with self.assertRaisesRegex(ValueError, "chi_sim"):
                    processor.load_file(
                        path,
                        namespace="test",
                        document_id="scan",
                    )

        self.assertEqual(run.call_count, 1)

    def test_pdf_uses_pypdf_without_markitdown_pdf_extras(self) -> None:
        processor = DocumentProcessor()
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "guide.pdf"
            path.write_bytes(b"%PDF-1.4")
            page = Mock()
            page.extract_text.return_value = "Searchable PDF content."
            with patch(
                "pypdf.PdfReader",
                return_value=SimpleNamespace(pages=[page]),
            ):
                document = processor.load_file(
                    path,
                    namespace="test",
                    document_id="guide",
                )

        self.assertEqual(document.content, "## Page 1\n\nSearchable PDF content.")
        self.assertEqual(document.metadata["source_type"], "pdf")

    def test_uses_stable_overlapping_paragraph_chunks(self) -> None:
        processor = DocumentProcessor(chunk_size=4, chunk_overlap=2)
        document = Document(
            id="doc",
            namespace="test",
            content="one two\n\nthree four\n\nfive six",
        )

        first = processor.split(document)
        second = processor.split(document)

        self.assertEqual([chunk.id for chunk in first], [chunk.id for chunk in second])
        self.assertEqual(
            [chunk.content for chunk in first],
            ["one two\n\nthree four", "three four\n\nfive six"],
        )

    def test_preserves_markdown_heading_context_for_embedding(self) -> None:
        processor = DocumentProcessor(chunk_size=20, chunk_overlap=0)
        document = Document(
            id="guide",
            namespace="test",
            content=(
                "# Python\n\nReleased in 1991.\n\n"
                "## Packaging\n\nUse a virtual environment."
            ),
        )

        chunks = processor.split(document)

        self.assertEqual([chunk.metadata["heading_path"] for chunk in chunks], [
            "Python",
            "Python > Packaging",
        ])
        self.assertEqual(
            processor.text_for_embedding(chunks[1]),
            "Python > Packaging\n\nUse a virtual environment.",
        )


if __name__ == "__main__":
    unittest.main()
