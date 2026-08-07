import argparse

from dotenv import load_dotenv

from examples.local_simple_agent import ROOT_DIR
from hello_agents_framework import SearchTool, ToolRegistry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one real multi-provider search integration check."
    )
    parser.add_argument("query", help="Focused query sent to the search provider.")
    parser.add_argument(
        "--backend",
        choices=("hybrid", "tavily", "serpapi"),
        default="hybrid",
        help="Search backend selection policy.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv(ROOT_DIR / ".env", override=False)

    registry = ToolRegistry()
    search_tool = SearchTool(backend=args.backend)
    registry.register_tool(search_tool)

    print(f"Available backends: {search_tool.available_backends}")
    result = registry.execute_tool("search", {"query": args.query})
    print(result)


if __name__ == "__main__":
    main()
