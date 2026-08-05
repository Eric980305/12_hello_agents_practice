"""Verify the official HelloAgents 0.2.0 memory and RAG configuration.

Run from ``projects/12_hello_agents_framework`` after starting the local
Qdrant and Neo4j services. The default check initializes both tools, writes
and retrieves one memory, and indexes and retrieves one RAG text without
calling the LLM. Pass ``--rerank`` to verify the configured Bailian reranker
and ``--agent`` for an additional real-model tool round trip.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import urlsplit

import requests
from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = Path(__file__).resolve().parents[3]


def configure_environment() -> None:
    """Load secrets first because HelloAgents captures DB config on import."""
    load_dotenv(ROOT_DIR / ".env", override=False)

    defaults = {
        "QDRANT_URL": "http://localhost:6333",
        "QDRANT_COLLECTION": "hello_agents_vectors",
        "QDRANT_VECTOR_SIZE": "384",
        "QDRANT_DISTANCE": "cosine",
        "QDRANT_TIMEOUT": "30",
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USERNAME": "neo4j",
        "NEO4J_DATABASE": "neo4j",
        "EMBED_MODEL_TYPE": "local",
        "EMBED_MODEL_NAME": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    }
    for name, value in defaults.items():
        os.environ.setdefault(name, value)

    if not os.getenv("NEO4J_PASSWORD"):
        raise RuntimeError("NEO4J_PASSWORD is required in the repository root .env")


def require_success(label: str, result: str, expected_text: str | None = None) -> None:
    if result.startswith("❌") or result.startswith("⚠️"):
        raise RuntimeError(f"{label} failed: {result}")
    if expected_text is not None and expected_text not in result:
        raise RuntimeError(f"{label} returned no expected evidence")
    print(f"[OK] {label}")


def _build_rerank_endpoint(base_url: str) -> str:
    """Build the qwen3-rerank endpoint from a workspace-scoped URL."""
    parsed = urlsplit(base_url.strip())
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("RERANK_BASE_URL must be a valid HTTPS URL")
    return f"{parsed.scheme}://{parsed.netloc}/compatible-api/v1/reranks"


def run_rerank_check() -> None:
    """Verify that Bailian reranks a small candidate set correctly."""
    api_key = os.getenv("RERANK_API_KEY")
    base_url = os.getenv("RERANK_BASE_URL")
    model = os.getenv("RERANK_MODEL_NAME", "qwen3-rerank")
    if not api_key or not base_url:
        raise RuntimeError("RERANK_API_KEY and RERANK_BASE_URL are required")
    if model != "qwen3-rerank":
        raise RuntimeError("This check currently supports qwen3-rerank only")

    documents = [
        "张三是一名 Python 开发者。",
        "量子计算利用量子力学原理处理信息。",
        "北京今天适合短途出行。",
    ]
    response = requests.post(
        _build_rerank_endpoint(base_url),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "query": "张三从事什么工作？",
            "documents": documents,
            "top_n": len(documents),
            "instruct": "Given a question, retrieve passages that answer the question.",
        },
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Bailian rerank request failed with HTTP {response.status_code}")

    payload = response.json()
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        raise RuntimeError("Bailian rerank response contains no results")

    ranked = []
    seen_indices = set()
    for result in results:
        index = result.get("index")
        score = result.get("relevance_score")
        if (
            not isinstance(index, int)
            or index < 0
            or index >= len(documents)
            or index in seen_indices
            or not isinstance(score, (int, float))
        ):
            raise RuntimeError("Bailian rerank response has an invalid result")
        seen_indices.add(index)
        ranked.append((index, float(score), documents[index]))

    if ranked[0][0] != 0:
        raise RuntimeError("Bailian rerank did not rank the answer-bearing document first")
    for position, (_, score, document) in enumerate(ranked, 1):
        print(f"[RERANK] {position}. score={score:.4f} document={document}")
    print("[OK] Bailian qwen3-rerank")


def run_quickstart(use_agent: bool = False, use_rerank: bool = False) -> None:
    configure_environment()

    # Import only after environment configuration. The official 0.2.0 package
    # creates its database configuration while these modules are imported.
    from hello_agents import HelloAgentsLLM, SimpleAgent, ToolRegistry
    from hello_agents.tools import MemoryTool, RAGTool

    registry = ToolRegistry()
    memory_tool = MemoryTool(user_id="chapter8_quickstart_user")
    registry.register_tool(memory_tool)

    rag_tool = RAGTool(
        knowledge_base_path=str(PROJECT_DIR / "knowledge_base"),
        collection_name="hello_agents_rag_vectors",
        rag_namespace="chapter8_quickstart",
    )
    registry.register_tool(rag_tool)

    memory_add = memory_tool.run(
        {
            "action": "add",
            "memory_type": "semantic",
            "content": "张三是一名 Python 开发者。",
            "importance": 0.8,
        }
    )
    require_success("semantic memory write", memory_add)

    memory_search = memory_tool.run(
        {
            "action": "search",
            "memory_type": "semantic",
            "query": "张三从事什么工作",
            "limit": 3,
        }
    )
    require_success("semantic memory retrieval", memory_search, "Python")

    rag_add = rag_tool.run(
        {
            "action": "add_text",
            "text": "HelloAgents 将记忆与 RAG 封装为可注册工具。",
            "document_id": "chapter8_quickstart",
            "namespace": "chapter8_quickstart",
        }
    )
    require_success("RAG indexing", rag_add)

    rag_search = rag_tool.run(
        {
            "action": "search",
            "query": "HelloAgents 如何提供记忆和知识检索能力",
            "namespace": "chapter8_quickstart",
            "enable_advanced_search": False,
            "limit": 3,
            "min_score": 0.0,
        }
    )
    require_success("RAG retrieval", rag_search, "可注册工具")

    if use_rerank:
        run_rerank_check()

    if use_agent:
        # Force the generic LLM_* contract. Auto-detection would otherwise
        # select the coexisting DASHSCOPE_API_KEY used only for embeddings.
        llm = HelloAgentsLLM(provider="auto")
        agent = SimpleAgent(
            name="MemoryRAGAssistant",
            llm=llm,
            system_prompt="你是一个有记忆和知识检索能力的中文助手。需要事实时必须使用已注册工具。",
            tool_registry=registry,
        )
        if "memory" not in registry.list_tools():
            raise RuntimeError("Agent memory tool registration failed")

        agent_response = agent.run(
            "memory 工具已经注册。请先且仅输出 "
            "[TOOL_CALL:memory:action=search,query=张三从事什么工作,memory_type=semantic]；"
            "收到工具结果后，再用一句中文回答。",
            temperature=0,
        )
        print(agent_response)
        require_success("Agent memory tool round trip", agent_response, "Python")

    print("[OK] Official HelloAgents memory and RAG quickstart completed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rerank",
        action="store_true",
        help="also verify the configured Bailian qwen3-rerank endpoint",
    )
    parser.add_argument(
        "--agent",
        action="store_true",
        help="also run a real LLM tool-calling demonstration",
    )
    args = parser.parse_args()
    run_quickstart(use_agent=args.agent, use_rerank=args.rerank)


if __name__ == "__main__":
    main()
