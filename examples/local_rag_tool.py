"""Run practice RAG retrieval against Bailian and local Qdrant."""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from hello_agents_practice import (
    LLMQueryExpander,
    RAGTool,
    ToolRegistry,
)
from hello_agents_practice.core.llm import create_llm_client_from_env


PROJECT_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = Path(__file__).resolve().parents[3]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--advanced",
        action="store_true",
        help="Enable MQE and HyDE; this consumes two chat-model calls.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv(ROOT_DIR / ".env", override=False)
    registry = ToolRegistry()
    rag_tool = RAGTool(
        knowledge_base_path=str(PROJECT_DIR / "knowledge_base"),
        collection_name=os.getenv("PRACTICE_RAG_QDRANT_COLLECTION"),
        rag_namespace="chapter8_rag_demo",
        database_path=PROJECT_DIR / "memory_data" / "practice_memory.db",
        query_expander=(
            LLMQueryExpander(create_llm_client_from_env())
            if args.advanced
            else None
        ),
    )
    registry.register_tool(rag_tool)

    sources = {
        "python_intro": "Python 是一种高级编程语言，由 Guido van Rossum 于 1991 年首次发布。",
        "ml_basics": "机器学习通过算法从数据中学习模式，包括监督学习、无监督学习和强化学习。",
        "rag_concept": "RAG 是结合信息检索和文本生成的技术，通过相关知识增强大语言模型。",
    }
    for document_id, text in sources.items():
        print(
            registry.execute_tool(
                "rag",
                {
                    "action": "add_text",
                    "text": text,
                    "document_id": document_id,
                    "metadata": {"source_type": "demo"},
                },
            )
        )

    print("\n=== Search Knowledge ===")
    print(
        registry.execute_tool(
            "rag",
            {
                "action": "search",
                "query": "Python 编程语言的历史",
                "limit": 3,
                "min_score": 0.1,
                "enable_mqe": args.advanced,
                "enable_hyde": args.advanced,
            },
        )
    )
    print("\n=== Knowledge Base Stats ===")
    print(registry.execute_tool("rag", {"action": "stats"}))
    print(f"Knowledge base: {rag_tool.knowledge_base_path}")
    print(f"SQLite: {rag_tool.pipeline.document_store.database_path}")
    print(f"Qdrant collection: {rag_tool.pipeline.vector_store.collection_name}")


if __name__ == "__main__":
    main()
