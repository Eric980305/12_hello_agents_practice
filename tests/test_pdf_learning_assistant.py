import gc
import socket
import tempfile
import unittest
import warnings
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import gradio as gr

from apps.pdf_learning_assistant import (
    ALL_KNOWLEDGE_BASES,
    APP_CSS,
    APP_HEAD,
    APP_JS,
    AssistantSessions,
    PENDING_ANSWER,
    PDFLearningAssistant,
    create_gradio_app,
    document_table_height,
    ensure_server_port_available,
    finish_chat_message,
    format_document_load_result,
    format_initialization_error,
    main,
    normalize_primary_view,
    primary_view_visibility,
    stage_chat_message,
)
from apps.user_store import UserAccountStore
from hello_agents_framework import MemoryItem, RAGSearchResult, SQLiteKnowledgeStore


class FakeMemoryTool:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.items: list[MemoryItem] = []
        self.manager = self

    def list_memories(self, *, user_id: str, memory_type: str):
        return [
            item
            for item in self.items
            if item.user_id == user_id and item.memory_type == memory_type
        ]

    def execute(self, action: str, **kwargs):
        self.calls.append((action, kwargs))
        if action == "summary":
            return "记忆摘要：2 条"
        if action == "search":
            return "找到学习记录"
        if action == "add":
            self.items.append(
                MemoryItem(
                    user_id="user-1",
                    content=kwargs["content"],
                    memory_type=kwargs["memory_type"],
                    importance=kwargs["importance"],
                    metadata=kwargs["metadata"],
                )
            )
        return "ok"


class FakeRAGTool:
    def __init__(self, *, namespace: str = "pdf_test", path: Path | None = None) -> None:
        self.execute_calls: list[tuple[str, dict]] = []
        self.retrieve_calls: list[dict] = []
        self.document_ids: set[str] = set()
        self.documents: dict[str, dict[str, object]] = {}
        self.results = [
            RAGSearchResult(
                content="Transformer uses self-attention.",
                score=0.91,
                document_id="doc-1",
                chunk_id="chunk-1",
                chunk_index=2,
                namespace=namespace,
                metadata={"source_name": "guide.pdf"},
            )
        ]
        self.pipeline = SimpleNamespace(namespace=namespace)
        self.knowledge_base_path = path
        if path is not None:
            path.mkdir(parents=True, exist_ok=True)

    def execute(self, action: str, **kwargs) -> str:
        self.execute_calls.append((action, kwargs))
        if action == "add_document":
            document_id = kwargs["document_id"]
            self.document_ids.add(document_id)
            metadata = dict(kwargs.get("metadata") or {})
            if self.knowledge_base_path is not None:
                metadata["source_path"] = str(
                    self.knowledge_base_path / kwargs["file_path"]
                )
            self.documents[document_id] = {
                "document_id": document_id,
                "name": metadata.get("original_name", document_id),
                "source_type": Path(kwargs["file_path"]).suffix.lstrip("."),
                "chunk_count": 1,
                "created_at": "2026-08-04T00:00:00+00:00",
                "metadata": metadata,
            }
        return "indexed"

    def has_document(self, document_id: str) -> bool:
        return document_id in self.document_ids

    def retrieve(self, **kwargs):
        self.retrieve_calls.append(kwargs)
        return list(self.results)

    def list_documents(self) -> list[dict[str, object]]:
        return list(self.documents.values())

    def delete_document(self, document_id: str) -> dict[str, object] | None:
        self.document_ids.discard(document_id)
        return self.documents.pop(document_id, None)

    def stats(self) -> dict[str, int | str]:
        return {
            "namespace": "pdf_test",
            "documents": len(self.documents),
            "chunks": len(self.documents),
        }


class FakeLLM:
    def __init__(self) -> None:
        self.calls: list[tuple[list[dict[str, str]], dict]] = []

    def invoke(self, messages: list[dict[str, str]], **kwargs) -> str:
        self.calls.append((messages, kwargs))
        return "Transformer 使用自注意力机制。[S1]"


class ChatInteractionTest(unittest.TestCase):
    def test_document_table_height_tracks_backend_rows_and_caps_viewport(self) -> None:
        self.assertEqual(document_table_height(0), 96)
        self.assertEqual(document_table_height(1), 96)
        self.assertEqual(document_table_height(2), 140)
        self.assertEqual(document_table_height(7), 360)
        self.assertEqual(document_table_height(8), 360)

    def test_primary_view_state_is_normalized_for_refresh_restore(self) -> None:
        self.assertEqual(normalize_primary_view("library"), "library")
        self.assertEqual(normalize_primary_view("stats"), "stats")
        self.assertEqual(normalize_primary_view("unknown"), "chat")
        self.assertEqual(primary_view_visibility("library"), (True, False, False))
        self.assertEqual(primary_view_visibility("chat"), (False, True, False))

    def test_submission_clears_input_and_renders_pending_answer(self) -> None:
        question, history, pending = stage_chat_message(" 什么是 LLM？ ", [])

        self.assertEqual(question, "")
        self.assertEqual(pending, "什么是 LLM？")
        self.assertEqual(
            history,
            [
                {"role": "user", "content": "什么是 LLM？"},
                {"role": "assistant", "content": PENDING_ANSWER},
            ],
        )

    def test_completed_answer_replaces_loading_bubble(self) -> None:
        _, history, _ = stage_chat_message("什么是 LLM？", [])

        completed = finish_chat_message(history, "LLM 是大语言模型。")

        self.assertEqual(completed[-1], {"role": "assistant", "content": "LLM 是大语言模型。"})
        self.assertNotIn(PENDING_ANSWER, [item["content"] for item in completed])


class PDFLearningAssistantTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.memory = FakeMemoryTool()
        self.rag = FakeRAGTool(path=root / "knowledge")
        self.llm = FakeLLM()
        self.assistant = PDFLearningAssistant(
            user_id="user-1",
            session_id="session-test",
            memory_tool=self.memory,
            rag_tool=self.rag,
            llm=self.llm,
            knowledge_base_path=root / "knowledge",
            reports_path=root / "reports",
        )
        self.pdf_path = root / "Happy LLM.pdf"
        self.pdf_path.write_bytes(b"%PDF-1.4\npractice")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_loads_pdf_inside_user_root_and_records_episodic_event(self) -> None:
        result = self.assistant.load_document(self.pdf_path)

        self.assertTrue(result["success"])
        self.assertEqual(self.assistant.current_document, "Happy LLM.pdf")
        self.assertEqual(len(list(self.assistant.knowledge_base_path.glob("*.pdf"))), 1)
        action, parameters = self.rag.execute_calls[0]
        self.assertEqual(action, "add_document")
        self.assertFalse(Path(parameters["file_path"]).is_absolute())
        self.assertEqual(parameters["document_id"], result["document_id"])
        self.assertEqual(self.memory.calls[-1][1]["memory_type"], "episodic")
        self.assertEqual(
            self.memory.calls[-1][1]["metadata"]["event_type"],
            "document_loaded",
        )

    def test_accepts_text_and_rejects_unsupported_executable(self) -> None:
        text_file = self.pdf_path.with_suffix(".txt")
        text_file.write_text("searchable text", encoding="utf-8")

        accepted = self.assistant.load_document(text_file)
        executable = self.pdf_path.with_suffix(".exe")
        executable.write_bytes(b"MZ")
        rejected = self.assistant.load_document(executable)

        self.assertTrue(accepted["success"])
        self.assertFalse(rejected["success"])
        self.assertIn("不支持 .exe 文件", rejected["message"])
        self.assertEqual(len(self.rag.execute_calls), 1)
        with self.assertRaises(ValueError):
            self.assistant.ask("x" * 4_001)

    def test_creates_selects_and_queries_persistent_knowledge_base(self) -> None:
        root = Path(self.temporary_directory.name)
        store = SQLiteKnowledgeStore(root / "catalog.db")

        def factory(knowledge_base_id: str) -> FakeRAGTool:
            tool = FakeRAGTool(
                namespace=f"kb_user_{knowledge_base_id}",
                path=root / "bases" / knowledge_base_id,
            )
            tool.results[0] = tool.results[0].model_copy(
                update={
                    "metadata": {
                        "source_name": "guide.pdf",
                        "knowledge_base_id": knowledge_base_id,
                    }
                }
            )
            return tool

        assistant = PDFLearningAssistant(
            user_id="user-1",
            memory_tool=self.memory,
            rag_tool=FakeRAGTool(path=root / "default"),
            rag_tool_factory=factory,
            knowledge_store=store,
            llm=self.llm,
            knowledge_base_path=root / "default",
            reports_path=root / "reports-2",
        )

        created = assistant.create_knowledge_base("法律法规")
        selected = assistant.select_knowledge_base(created["id"])
        answer = assistant.ask("合同有哪些约定？")
        persisted = store.list_knowledge_bases(user_id="user-1")

        self.assertEqual(selected, "法律法规")
        self.assertIn("Transformer 使用自注意力机制", answer)
        self.assertEqual(persisted[0]["name"], "法律法规")

    def test_rejects_duplicate_names_and_deletes_only_owned_private_base(self) -> None:
        root = Path(self.temporary_directory.name)
        store = SQLiteKnowledgeStore(root / "catalog-delete.db")
        tools: dict[str, FakeRAGTool] = {}

        def factory(knowledge_base_id: str) -> FakeRAGTool:
            return tools.setdefault(
                knowledge_base_id,
                FakeRAGTool(
                    namespace=f"kb_user_{knowledge_base_id}",
                    path=root / "bases" / knowledge_base_id,
                ),
            )

        assistant = PDFLearningAssistant(
            user_id="user-1",
            memory_tool=self.memory,
            rag_tool=FakeRAGTool(path=root / "shared"),
            rag_tool_factory=factory,
            knowledge_store=store,
            llm=self.llm,
            knowledge_base_path=root / "shared",
            reports_path=root / "reports-delete",
        )
        created = assistant.create_knowledge_base("法律法规")
        document = root / "contract.txt"
        document.write_text("contract terms", encoding="utf-8")
        loaded = assistant.load_document(document, knowledge_base_id=created["id"])

        with self.assertRaisesRegex(ValueError, "名称已存在"):
            assistant.create_knowledge_base("  法律法规  ")
        with self.assertRaisesRegex(ValueError, "确认"):
            assistant.delete_knowledge_base(created["id"])
        with self.assertRaisesRegex(ValueError, "共享知识库不能删除"):
            assistant.delete_knowledge_base("default", confirmed=True)

        removed = assistant.delete_knowledge_base(created["id"], confirmed=True)

        self.assertEqual(removed["documents_deleted"], 1)
        self.assertEqual(assistant.current_knowledge_base_id, "default")
        self.assertNotIn(
            created["id"],
            {item["id"] for item in assistant.list_knowledge_bases()},
        )
        self.assertNotIn(loaded["document_id"], tools[created["id"]].document_ids)

    def test_reuses_existing_index_without_reprocessing_or_duplicate_memory(self) -> None:
        first = self.assistant.load_document(self.pdf_path)
        first_memory_count = len(self.memory.calls)

        second = self.assistant.load_document(self.pdf_path)

        self.assertTrue(first["success"])
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["success"])
        self.assertTrue(second["duplicate"])
        self.assertIn("文档已存在", second["message"])
        self.assertEqual(len(self.rag.execute_calls), 1)
        self.assertEqual(len(self.memory.calls), first_memory_count)
        self.assertEqual(self.assistant.documents_loaded, 1)
        self.assertEqual(len(list(self.assistant.knowledge_base_path.glob("*.pdf"))), 1)

    def test_answers_from_typed_sources_and_records_memory(self) -> None:
        self.assertTrue(self.assistant.load_document(self.pdf_path)["success"])

        answer = self.assistant.ask("Transformer 是什么？", use_advanced_search=True)

        self.assertIn("Transformer 使用自注意力机制", answer)
        self.assertIn("[S1] guide.pdf", answer)
        self.assertTrue(self.rag.retrieve_calls[0]["enable_mqe"])
        self.assertTrue(self.rag.retrieve_calls[0]["enable_hyde"])
        prompt = self.llm.calls[0][0][1]["content"]
        self.assertIn("Transformer uses self-attention", prompt)
        memory_types = [call[1].get("memory_type") for call in self.memory.calls]
        self.assertIn("working", memory_types)
        self.assertGreaterEqual(memory_types.count("episodic"), 2)

    def test_note_recall_stats_and_report_use_real_stage_memory_types(self) -> None:
        self.assistant.add_note("Attention connects tokens.", "attention")
        self.assistant.ask("Attention 如何连接 token？")
        recalled = self.assistant.recall("attention")
        report = self.assistant.generate_report()

        note_call = self.memory.calls[0]
        self.assertEqual(note_call[1]["memory_type"], "episodic")
        self.assertEqual(note_call[1]["metadata"]["event_type"], "learning_note")
        self.assertEqual(note_call[1]["metadata"]["knowledge_base_id"], "default")
        self.assertEqual(
            note_call[1]["metadata"]["knowledge_base_name"],
            "共享知识库",
        )
        self.assertIn("Attention connects tokens", recalled)
        self.assertEqual(report["learning_metrics"]["notes_added"], 1)
        self.assertEqual(report["learning_metrics"]["questions_asked"], 1)
        self.assertEqual(report["knowledge_base"]["name"], "共享知识库")
        self.assertTrue(report["learning_summary"])
        report_path = Path(report["report_file"])
        self.assertTrue(report_path.is_file())
        self.assertTrue(report_path.is_relative_to(self.assistant.reports_path))

    def test_report_groups_current_session_real_qa_by_knowledge_base(self) -> None:
        second_rag = FakeRAGTool(namespace="kb_user_legal")
        self.assistant.knowledge_bases["legal"] = "法律资料"
        self.assistant.rag_tools["legal"] = second_rag
        self.assistant.ask("共享资料讲了什么？", knowledge_base_id="default")
        self.assistant.ask("法律资料讲了什么？", knowledge_base_id="legal")

        report = self.assistant.generate_report(save_to_file=False)

        self.assertEqual(report["learning_metrics"]["questions_asked"], 2)
        self.assertEqual(report["learning_metrics"]["knowledge_bases_used"], 2)
        self.assertNotIn("knowledge_base", report)
        self.assertEqual(
            [item["knowledge_base"]["name"] for item in report["knowledge_base_summaries"]],
            ["共享知识库", "法律资料"],
        )
        self.assertIn("## 来源知识库：共享知识库", report["learning_summary"])
        self.assertIn("## 来源知识库：法律资料", report["learning_summary"])
        report_prompts = [call[0][1]["content"] for call in self.llm.calls[-2:]]
        self.assertIn("来源知识库：共享知识库", report_prompts[0])
        self.assertIn("来源知识库：法律资料", report_prompts[1])

    def test_lists_and_confirmedly_deletes_one_knowledge_base_document(self) -> None:
        loaded = self.assistant.load_document(self.pdf_path)

        documents = self.assistant.list_documents()
        with self.assertRaisesRegex(ValueError, "明确确认"):
            self.assistant.delete_document(loaded["document_id"])
        removed = self.assistant.delete_document(
            loaded["document_id"],
            confirmed=True,
        )

        self.assertEqual(documents[0]["name"], "Happy LLM.pdf")
        self.assertEqual(removed["document_id"], loaded["document_id"])
        self.assertEqual(self.assistant.list_documents(), [])
        self.assertEqual(list(self.assistant.knowledge_base_path.glob("*.pdf")), [])

    def test_document_and_note_filters_are_scoped_and_time_sorted(self) -> None:
        self.assistant.load_document(self.pdf_path)
        text_path = self.pdf_path.with_name("finance.txt")
        text_path.write_text("annual report", encoding="utf-8")
        self.assistant.load_document(text_path)
        self.assistant.add_note("First note", "legal")
        self.assistant.add_note("Second note", "finance")

        documents = self.assistant.list_documents(query="finance", source_type="txt")
        notes = self.assistant.list_notes(query="note", concept="finance")

        self.assertEqual([item["name"] for item in documents], ["finance.txt"])
        self.assertEqual([item["content"] for item in notes], ["Second note"])
        self.assertIn("created_at", notes[0])

    def test_explicit_knowledge_base_prevents_shared_selection_leakage(self) -> None:
        root = Path(self.temporary_directory.name)
        store = SQLiteKnowledgeStore(root / "catalog-isolation.db")
        tools: dict[str, FakeRAGTool] = {}

        def factory(knowledge_base_id: str) -> FakeRAGTool:
            tool = FakeRAGTool(
                namespace=f"kb_user_{knowledge_base_id}",
                path=root / "bases" / knowledge_base_id,
            )
            tools[knowledge_base_id] = tool
            return tool

        assistant = PDFLearningAssistant(
            user_id="user-1",
            memory_tool=self.memory,
            rag_tool=FakeRAGTool(namespace="pdf_default", path=root / "default"),
            rag_tool_factory=factory,
            knowledge_store=store,
            llm=self.llm,
            knowledge_base_path=root / "default",
            reports_path=root / "reports-isolation",
        )
        legal = assistant.create_knowledge_base("法律")
        finance = assistant.create_knowledge_base("财务")
        legal_tool = tools[legal["id"]]
        legal_tool.results[0] = legal_tool.results[0].model_copy(
            update={"metadata": {"source_name": "law.pdf", "knowledge_base_id": legal["id"]}}
        )
        tools[finance["id"]].results[0] = tools[finance["id"]].results[0].model_copy(
            update={"metadata": {"source_name": "finance.pdf", "knowledge_base_id": finance["id"]}}
        )
        tools[legal["id"]].execute(
            "add_document",
            file_path="law.pdf",
            document_id="law-document",
            metadata={"original_name": "law.pdf"},
        )
        tools[finance["id"]].execute(
            "add_document",
            file_path="finance.pdf",
            document_id="finance-document",
            metadata={"original_name": "finance.pdf"},
        )

        assistant.add_note("法律合同笔记", knowledge_base_id=legal["id"])
        assistant.add_note("财务报告笔记", knowledge_base_id=finance["id"])
        all_documents = assistant.list_documents(query="pdf", include_all=True)
        all_notes = assistant.list_notes(query="笔记", include_all=True)
        legal_notes = assistant.list_notes(legal["id"], query="合同")

        assistant.select_knowledge_base(finance["id"])
        answer = assistant.ask("合同？", knowledge_base_id=legal["id"])

        self.assertEqual(
            {item["knowledge_base_name"] for item in all_notes},
            {"法律", "财务"},
        )
        self.assertEqual(
            {item["knowledge_base_name"] for item in all_documents},
            {"法律", "财务"},
        )
        self.assertEqual([item["content"] for item in legal_notes], ["法律合同笔记"])
        self.assertIn("law.pdf", answer)
        self.assertEqual(len(legal_tool.retrieve_calls), 1)
        self.assertEqual(len(tools[finance["id"]].retrieve_calls), 0)

    def test_shared_library_is_global_and_private_libraries_are_owner_scoped(self) -> None:
        root = Path(self.temporary_directory.name)
        store = SQLiteKnowledgeStore(root / "two-users.db")
        store.ensure_knowledge_base(
            user_id="__shared__",
            knowledge_base_id="default",
            name="共享知识库",
            namespace="pdf_shared_default",
        )
        shared_tool = FakeRAGTool(
            namespace="pdf_shared_default",
            path=root / "shared",
        )
        private_tools: dict[tuple[str, str], FakeRAGTool] = {}

        def build_assistant(user_id: str) -> PDFLearningAssistant:
            user_scope = user_id.replace("-", "_")

            def factory(knowledge_base_id: str) -> FakeRAGTool:
                key = (user_id, knowledge_base_id)
                return private_tools.setdefault(
                    key,
                    FakeRAGTool(
                        namespace=f"kb_{user_scope}_{knowledge_base_id}",
                        path=root / user_scope / knowledge_base_id,
                    ),
                )

            accessible = {
                item["id"]: item["name"]
                for item in store.list_accessible_knowledge_bases(
                    user_id=user_id,
                    shared_owner_id="__shared__",
                )
            }
            return PDFLearningAssistant(
                user_id=user_id,
                memory_tool=FakeMemoryTool(),
                rag_tool=shared_tool,
                rag_tool_factory=factory,
                knowledge_store=store,
                knowledge_bases=accessible,
                llm=FakeLLM(),
                knowledge_base_path=root / user_scope,
                reports_path=root / "reports" / user_scope,
            )

        stale_alice = build_assistant("alice")
        alice = build_assistant("alice")
        alice_private = alice.create_knowledge_base("Alice 私有库")
        bob = build_assistant("bob")
        bob_private = bob.create_knowledge_base("Bob 私有库")
        alice = build_assistant("alice")
        bob = build_assistant("bob")

        shared_alice = root / "shared-alice.txt"
        shared_alice.write_text("shared by alice", encoding="utf-8")
        shared_bob = root / "shared-bob.txt"
        shared_bob.write_text("shared by bob", encoding="utf-8")
        private_alice = root / "private-alice.txt"
        private_alice.write_text("alice only", encoding="utf-8")
        private_bob = root / "private-bob.txt"
        private_bob.write_text("bob only", encoding="utf-8")

        alice.load_document(shared_alice, knowledge_base_id="default")
        bob.load_document(shared_bob, knowledge_base_id="default")
        alice.load_document(private_alice, knowledge_base_id=alice_private["id"])
        bob.load_document(private_bob, knowledge_base_id=bob_private["id"])

        self.assertEqual(
            {item["name"] for item in stale_alice.list_knowledge_bases()},
            {"共享知识库", "Alice 私有库"},
        )
        self.assertEqual(
            {item["name"] for item in stale_alice.list_documents(include_all=True)},
            {"shared-alice.txt", "shared-bob.txt", "private-alice.txt"},
        )

        self.assertEqual(
            {item["name"] for item in alice.list_knowledge_bases()},
            {"共享知识库", "Alice 私有库"},
        )
        self.assertEqual(
            {item["name"] for item in bob.list_knowledge_bases()},
            {"共享知识库", "Bob 私有库"},
        )
        self.assertEqual(
            {item["name"] for item in alice.list_documents("default")},
            {"shared-alice.txt", "shared-bob.txt"},
        )
        self.assertEqual(
            {item["name"] for item in bob.list_documents("default")},
            {"shared-alice.txt", "shared-bob.txt"},
        )
        self.assertEqual(
            {item["name"] for item in alice.list_documents(include_all=True)},
            {"shared-alice.txt", "shared-bob.txt", "private-alice.txt"},
        )
        self.assertEqual(
            {item["name"] for item in bob.list_documents(include_all=True)},
            {"shared-alice.txt", "shared-bob.txt", "private-bob.txt"},
        )

        expected_alice_scopes = {
            "default": {"shared-alice.txt", "shared-bob.txt"},
            alice_private["id"]: {"private-alice.txt"},
        }
        for knowledge_base_id in (
            "default",
            alice_private["id"],
            "default",
            alice_private["id"],
        ):
            self.assertEqual(
                {
                    item["name"]
                    for item in alice.list_documents(knowledge_base_id)
                },
                expected_alice_scopes[knowledge_base_id],
            )
        self.assertEqual(
            {item["name"] for item in alice.list_documents(include_all=True)},
            {"shared-alice.txt", "shared-bob.txt", "private-alice.txt"},
        )

        shared_duplicate = alice.load_document(
            shared_alice,
            knowledge_base_id="default",
        )
        private_copy = alice.load_document(
            shared_alice,
            knowledge_base_id=alice_private["id"],
        )
        self.assertTrue(shared_duplicate["duplicate"])
        self.assertFalse(private_copy["duplicate"])


class AssistantSessionsTest(unittest.TestCase):
    def test_port_conflict_is_detected_before_startup(self) -> None:
        with socket.create_server(("127.0.0.1", 0)) as server:
            port = server.getsockname()[1]
            with self.assertRaisesRegex(OSError, f"端口 127.0.0.1:{port} 已被占用"):
                ensure_server_port_available("127.0.0.1", port)

    def test_document_status_distinguishes_duplicate_and_failure_reasons(self) -> None:
        duplicate = format_document_load_result(
            {
                "success": True,
                "duplicate": True,
                "document": "guide.pdf",
                "message": "文档已存在，未重复处理。",
            }
        )
        failure = format_document_load_result(
            {"success": False, "message": "仅支持 PDF 文件。"}
        )

        self.assertIn("文件已加载过：guide.pdf", duplicate)
        self.assertIn("未重复处理", duplicate)
        self.assertEqual(failure, "❌ 上传失败：仅支持 PDF 文件。")

    def test_initialization_error_identifies_qdrant_without_exposing_response(self) -> None:
        error_type = type("UnexpectedResponse", (Exception,), {})

        message = format_initialization_error(error_type("secret response body"))

        self.assertIn("Qdrant 初始化失败", message)
        self.assertNotIn("secret response body", message)

    def test_isolates_assistants_by_browser_session_token(self) -> None:
        created: list[str] = []

        def factory(user_id: str):
            created.append(user_id)
            return object()

        sessions = AssistantSessions(factory)
        first_token, first = sessions.create("alice")
        second_token, second = sessions.create("bob")

        self.assertIs(sessions.get(first_token), first)
        self.assertIs(sessions.get(second_token), second)
        self.assertIsNot(first, second)
        self.assertEqual(created, ["alice", "bob"])

    def test_gradio_app_builds_without_creating_external_resources(self) -> None:
        calls = []

        def factory(user_id: str):
            calls.append(user_id)
            return object()

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            with tempfile.TemporaryDirectory() as account_root:
                account_store = UserAccountStore(Path(account_root) / "accounts.db")
                app = create_gradio_app(factory, user_store=account_store)
            try:
                self.assertIsInstance(app, gr.Blocks)
                self.assertEqual(calls, [])
                components = app.get_config_file()["components"]
                tabs = {
                    component.get("props", {}).get("label")
                    for component in components
                    if component["type"] == "tabitem"
                }
                self.assertEqual(
                    tabs,
                    {"文档", "笔记"},
                )
                component_types = {component["type"] for component in components}
                self.assertIn("checkbox", component_types)
                self.assertIn("radio", component_types)
                primary_navigation = next(
                    component.get("props", {})
                    for component in components
                    if component["type"] == "radio"
                    and "primary-navigation"
                    in component.get("props", {}).get("elem_classes", [])
                )
                self.assertEqual(primary_navigation.get("value"), "chat")
                browser_states = {
                    component.get("props", {}).get("storage_key"):
                    component.get("props", {}).get("default_value")
                    for component in components
                    if component["type"] == "browserstate"
                }
                self.assertEqual(
                    browser_states.get("hello_agents_practice_primary_view"),
                    "chat",
                )
                dependencies = app.get_config_file()["dependencies"]
                events_by_component: dict[int, set[str]] = {}
                for dependency in dependencies:
                    for component_id, event_name in dependency.get("targets", []):
                        events_by_component.setdefault(component_id, set()).add(event_name)

                library_selector = next(
                    component
                    for component in components
                    if component["type"] == "dropdown"
                    and component.get("props", {}).get("label") == "选择知识库"
                    and component.get("props", {}).get("value") == ALL_KNOWLEDGE_BASES
                )
                text_filters = [
                    component
                    for component in components
                    if component.get("props", {}).get("label")
                    in {"搜索文档", "搜索笔记"}
                ]
                for component in [library_selector]:
                    events = events_by_component.get(component["id"], set())
                    self.assertTrue(events)
                    self.assertNotIn("select", events)
                    self.assertNotIn("change", events)
                for component in text_filters:
                    events = events_by_component.get(component["id"], set())
                    self.assertTrue(events.intersection({"input", "submit"}))
                    self.assertNotIn("change", events)
                button_values = {
                    component.get("props", {}).get("value")
                    for component in components
                    if component["type"] == "button"
                }
                self.assertNotIn("初始化助手", button_values)
                self.assertNotIn("加载文档", button_values)
                self.assertIn("管理知识库", button_values)
                self.assertIn("新建知识库", button_values)
                document_search_props = next(
                    component.get("props", {})
                    for component in components
                    if component["type"] == "textbox"
                    and component.get("props", {}).get("label") == "搜索文档"
                )
                self.assertEqual(document_search_props.get("submit_btn"), "搜索")
                self.assertIn("关闭", button_values)
                self.assertIn("确认删除", button_values)
                self.assertIn("↕", button_values)
                self.assertIn("登录", button_values)
                self.assertIn("创建账号", button_values)
                self.assertIn("退出登录", button_values)
                self.assertIn("dataframe", component_types)
                dataframe_headers = {
                    tuple(component.get("props", {}).get("headers") or [])
                    for component in components
                    if component["type"] == "dataframe"
                }
                self.assertIn(
                    ("文件名", "所属知识库", "操作"),
                    dataframe_headers,
                )
                self.assertIn(
                    ("笔记", "所属知识库", "创建时间"),
                    dataframe_headers,
                )
                self.assertIn(
                    ("知识库", "操作"),
                    dataframe_headers,
                )
                self.assertNotIn(
                    ("文件名", "类型", "分块数", "添加时间"),
                    dataframe_headers,
                )
                # A virtualized Dataframe only renders the rows visible in its
                # current viewport. CSS must not infer the full result count
                # from those DOM rows or a one-row library can permanently
                # crop later aggregate results.
                self.assertNotIn(".document-table .virtual-body:has", APP_CSS)
                self.assertNotIn(".document-table .virtual-body:not(:has", APP_CSS)
                checkboxes = [
                    component.get("props", {})
                    for component in components
                    if component["type"] == "checkbox"
                ]
                advanced = next(
                    item for item in checkboxes
                    if "高级检索" in str(item.get("label"))
                )
                self.assertFalse(advanced.get("value"))
                component_classes = {
                    class_name
                    for component in components
                    for class_name in component.get("props", {}).get("elem_classes", [])
                }
                self.assertIn("knowledge-picker-card", component_classes)
                self.assertIn("chat-controls", component_classes)
                self.assertIn("chat-input-row", component_classes)
                self.assertIn("chat-question", component_classes)
                chatbots = [
                    component.get("props", {})
                    for component in components
                    if component["type"] == "chatbot"
                ]
                self.assertEqual(len(chatbots), 1)
                self.assertEqual(
                    chatbots[0].get("placeholder"),
                    "今天有什么想询问知识库的吗？",
                )
                all_scope_fields = [
                    component.get("props", {})
                    for component in components
                    if component["type"] == "dropdown"
                    and ("所有知识库", "__all__")
                    in component.get("props", {}).get("choices", [])
                ]
                self.assertEqual(len(all_scope_fields), 1)
                self.assertEqual(all_scope_fields[0].get("label"), "选择知识库")
                finite_dropdowns = [
                    component.get("props", {})
                    for component in components
                    if component["type"] == "dropdown"
                    and component.get("props", {}).get("label")
                    in {"选择知识库", "知识库"}
                ]
                self.assertTrue(finite_dropdowns)
                dynamic_dropdowns = [
                    item
                    for item in finite_dropdowns
                    if item.get("label") == "选择知识库"
                ]
                self.assertTrue(dynamic_dropdowns)
                self.assertTrue(
                    all(item.get("allow_custom_value") is True for item in dynamic_dropdowns)
                )
                self.assertFalse(
                    any(
                        component.get("props", {}).get("label") == "文件类型"
                        for component in components
                    )
                )
                self.assertIn("event.composedPath()", APP_JS)
                self.assertIn("findInPath('.wrap')", APP_JS)
                self.assertIn("findInPath('[role=\"combobox\"]')", APP_JS)
                self.assertIn("findInPath('[role=\"option\"]')", APP_JS)
                self.assertIn("composed: true", APP_JS)
                self.assertIn(".primary-navigation .wrap", APP_CSS)
                self.assertIn("grid-template-columns: repeat(3", APP_CSS)
                self.assertIn("--auth-field-background: #ffffff", APP_CSS)
                self.assertIn("--auth-field-background: #0f172a", APP_CSS)
                self.assertIn("background: var(--auth-field-background)", APP_CSS)
                self.assertIn("min-height: 100dvh", APP_CSS)
                self.assertIn("background: var(--auth-mobile-surface)", APP_CSS)
                self.assertIn("--auth-mobile-surface: var(--body-background-fill)", APP_CSS)
                self.assertIn("max-width: none !important", APP_CSS)
                self.assertIn("background: var(--body-background-fill)", APP_CSS)
                self.assertNotIn("max-width: 1180px", APP_CSS)
                self.assertIn("gradio-app", APP_HEAD)
                knowledge_base_name_fields = [
                    component.get("props", {})
                    for component in components
                    if component["type"] == "textbox"
                    and component.get("props", {}).get("label") == "知识库名称"
                ]
                self.assertEqual(len(knowledge_base_name_fields), 1)
                dependencies = app.get_config_file()["dependencies"]
                source_file_id = next(
                    component["id"]
                    for component in components
                    if component["type"] == "file"
                    and component.get("props", {}).get("label")
                    == "上传文件"
                )
                upload_dependency = next(
                    dependency
                    for dependency in dependencies
                    if any(
                        event_name == "upload"
                        for _, event_name in dependency.get("targets", [])
                    )
                )
                self.assertIn(source_file_id, upload_dependency.get("outputs", []))
                self.assertTrue(
                    any(
                        any(event_name == "load" for _, event_name in dependency.get("targets", []))
                        for dependency in dependencies
                    )
                )
                self.assertTrue(
                    any(component["type"] == "browserstate" for component in components)
                )
            finally:
                app.close()
                del app
                gc.collect()

    @patch("apps.pdf_learning_assistant.stop_chapter8_infrastructure")
    @patch("apps.pdf_learning_assistant.start_chapter8_infrastructure")
    @patch("apps.pdf_learning_assistant.ensure_server_port_available")
    @patch("apps.pdf_learning_assistant.create_gradio_app")
    @patch("apps.pdf_learning_assistant.parse_args")
    @patch("apps.pdf_learning_assistant.load_dotenv")
    def test_main_stops_infrastructure_when_the_app_exits(
        self,
        load_dotenv: Mock,
        parse_args: Mock,
        create_app: Mock,
        ensure_port: Mock,
        start_infrastructure: Mock,
        stop_infrastructure: Mock,
    ) -> None:
        parse_args.return_value = Namespace(host="127.0.0.1", port=7860)
        create_app.return_value.launch.side_effect = KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            main()

        ensure_port.assert_called_once_with("127.0.0.1", 7860)
        start_infrastructure.assert_called_once_with()
        stop_infrastructure.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
