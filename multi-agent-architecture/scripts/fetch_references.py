"""Fetch latest agentic design pattern references from Anthropic, OpenAI, and Google.

Searches the web for the latest published literature on multi-agent patterns
and updates the references/agentic-patterns.md source list with new findings.

Usage:
    uv run scripts/fetch_references.py
    uv run scripts/fetch_references.py --output references/latest-sources.md
"""

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path

SEARCH_QUERIES = [
    # Anthropic
    "Anthropic building effective agents multi-agent patterns",
    "Anthropic multi-agent system architecture blog",
    "Anthropic agentic design patterns orchestration",
    # OpenAI
    "OpenAI practical guide building agents patterns",
    "OpenAI agents SDK multi-agent orchestration handoffs",
    "OpenAI swarm multi-agent framework patterns",
    # Google
    "Google ADK multi-agent design patterns",
    "Google Cloud agentic AI system design patterns",
    "Google DeepMind multi-agent architecture scaling",
    # General / Academic
    "multi-agent LLM system architecture patterns survey 2025 2026",
    "agentic AI design patterns production best practices",
]

KNOWN_SOURCES = {
    "Anthropic: Building Effective Agents": "https://www.anthropic.com/engineering/building-effective-agents",
    "Anthropic: Multi-Agent Research System": "https://www.anthropic.com/engineering/multi-agent-research-system",
    "OpenAI: A Practical Guide to Building Agents": "https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/",
    "OpenAI: Orchestrating Agents - Routines and Handoffs": "https://developers.openai.com/cookbook/examples/orchestrating_agents",
    "OpenAI: Agents SDK Multi-Agent Docs": "https://openai.github.io/openai-agents-python/multi_agent/",
    "Google: Multi-Agent Patterns in ADK": "https://developers.googleblog.com/developers-guide-to-multi-agent-patterns-in-adk/",
    "Google: Choose a Design Pattern for Agentic AI": "https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system",
    "Google: Multi-Agent AI System Architecture": "https://docs.cloud.google.com/architecture/multiagent-ai-system",
}

# Domains likely to contain high-quality agentic pattern content
PRIORITY_DOMAINS = [
    "anthropic.com",
    "openai.com",
    "developers.openai.com",
    "openai.github.io",
    "cloud.google.com",
    "docs.google.com",
    "developers.googleblog.com",
    "research.google",
    "arxiv.org",
    "langchain.com",
    "docs.llamaindex.ai",
    "microsoft.com",
    "crewai.com",
]


def search_web(query: str) -> list[dict]:
    """Search using ddgs (duckduckgo-search) CLI or fallback to curl."""
    results = []

    # Try using ddgs CLI (pip install duckduckgo-search)
    try:
        proc = subprocess.run(
            ["ddgs", "text", "--keywords", query, "--max_results", "5", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            parsed = json.loads(proc.stdout)
            for item in parsed:
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("href", item.get("link", "")),
                        "snippet": item.get("body", item.get("snippet", "")),
                    }
                )
            return results
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass

    # Fallback: use ddgs Python API directly
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=5):
                results.append(
                    {
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", ""),
                    }
                )
        return results
    except ImportError:
        pass

    print(f"  [WARN] No search backend available for: {query}")
    print("  Install duckduckgo-search: uv add duckduckgo-search")
    return results


def is_priority_domain(url: str) -> bool:
    for domain in PRIORITY_DOMAINS:
        if domain in url:
            return True
    return False


def deduplicate_by_url(sources: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for s in sources:
        url = s["url"].rstrip("/")
        if url not in seen:
            seen.add(url)
            unique.append(s)
    return unique


def categorize_source(url: str) -> str:
    if "anthropic.com" in url:
        return "Anthropic"
    if "openai" in url:
        return "OpenAI"
    if "google" in url or "googleblog" in url:
        return "Google"
    if "arxiv.org" in url:
        return "Academic"
    if "langchain" in url or "llamaindex" in url or "crewai" in url:
        return "Framework"
    return "Other"


def generate_report(all_sources: list[dict], output_path: Path) -> None:
    """Generate a markdown report of discovered sources."""
    categorized: dict[str, list[dict]] = {}
    for s in all_sources:
        cat = categorize_source(s["url"])
        categorized.setdefault(cat, []).append(s)

    lines = [
        "# Latest Agentic Pattern References",
        "",
        f"> Auto-generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Known Canonical Sources",
        "",
    ]

    for title, url in KNOWN_SOURCES.items():
        lines.append(f"- [{title}]({url})")

    lines.extend(["", "## Discovered Sources", ""])

    for category in ["Anthropic", "OpenAI", "Google", "Academic", "Framework", "Other"]:
        sources = categorized.get(category, [])
        if not sources:
            continue
        lines.append(f"### {category}")
        lines.append("")
        for s in sources:
            priority = " ⭐" if is_priority_domain(s["url"]) else ""
            lines.append(f"- [{s['title']}]({s['url']}){priority}")
            if s.get("snippet"):
                snippet = s["snippet"][:200].replace("\n", " ")
                lines.append(f"  > {snippet}")
            lines.append("")

    lines.extend(
        [
            "---",
            "",
            "## How to Use",
            "",
            "Review the discovered sources above. To update the main pattern catalog:",
            "",
            "1. Read each new source for novel patterns or updated guidance",
            "2. Add new patterns to `references/agentic-patterns.md`",
            "3. Update the source literature section with new links",
            "4. Update the `Last updated` date at the top of the file",
        ]
    )

    output_path.write_text("\n".join(lines))
    print(f"\nReport written to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Fetch latest agentic pattern references")
    parser.add_argument(
        "--output",
        default="references/latest-sources.md",
        help="Output file path (default: references/latest-sources.md)",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).parent.parent
    output_path = script_dir / args.output

    print("Searching for latest agentic design pattern references...\n")

    all_sources = []
    for i, query in enumerate(SEARCH_QUERIES, 1):
        print(f"[{i}/{len(SEARCH_QUERIES)}] Searching: {query}")
        results = search_web(query)
        all_sources.extend(results)
        print(f"  Found {len(results)} results")

    all_sources = deduplicate_by_url(all_sources)

    # Sort: priority domains first, then alphabetically
    all_sources.sort(key=lambda s: (not is_priority_domain(s["url"]), s.get("title", "")))

    print(f"\nTotal unique sources found: {len(all_sources)}")

    generate_report(all_sources, output_path)


if __name__ == "__main__":
    main()
