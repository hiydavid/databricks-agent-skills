---
name: multi-agent-architecture
description: 'Design multi-agent system architectures for PoC, hackathon, or MVP projects. Analyze use cases, recommend agentic patterns from Anthropic/OpenAI/Google literature, and produce a buildable architecture document with a clean Mermaid diagram. Output is designed to be handed off to agent SDK skills (Claude Agent SDK, LangGraph, OpenAI Agents SDK) for implementation. Use when users want to: (1) design a multi-agent or agentic system for a PoC/hackathon, (2) choose between agentic patterns for a use case, (3) get architecture recommendations for an AI agent project, (4) evaluate single-agent vs multi-agent approaches, or (5) document an agent system design. Triggers on: "design agent architecture", "multi-agent architecture", "agentic design", "agent system design", "which agent pattern", "architecture recommendation", "agent architecture document".'
---

# Multi-Agent Architecture Design

Design buildable multi-agent architectures for PoC / hackathon / MVP projects, grounded in published agentic design patterns from Anthropic, OpenAI, and Google.

**Scope**: The output targets a working prototype — enough structure to build with an agent SDK, not a production system design. Production concerns (observability, scaling, cost optimization) are noted as future considerations, not core requirements.

The workflow:
1. Gather use case requirements
2. Analyze requirements against pattern catalog
3. Formulate architecture recommendation
4. Write architecture document to `agent-architecture-{use-case-slug}.md`
5. Review and refine with user

## Step 1: Gather Use Case Requirements

If the user hasn't provided enough context, ask targeted clarifying questions. Only ask what's missing — skip questions the user already answered.

| Dimension | Question |
|-----------|----------|
| Business goal | What problem does the system solve? Who are the users? |
| Input/Output | What goes in, what comes out? |
| Task complexity | Fixed/predictable workflow or open-ended/dynamic? |
| Data sources | What tools, APIs, databases, or platforms to integrate? |
| Quality bar | How important is correctness? Any hard constraints? |

Keep it lightweight — skip questions about scale, latency SLAs, and compliance unless the user raises them. This is a PoC.

## Step 2: Analyze Requirements Against Pattern Catalog

Read `references/agentic-patterns.md` — the curated catalog of 9 patterns from Anthropic, OpenAI, and Google with trade-offs and examples.

Read `references/decision-framework.md` — decision tree, complexity ladder, evaluation criteria matrix, and composite pattern guidance.

Match the use case to patterns using the decision tree. Favor the **simplest pattern that demonstrates the concept**. For a PoC, a single well-chosen pattern is better than a composite.

## Step 3: Formulate Architecture Recommendation

Recommend:
1. **Primary pattern** — main orchestration strategy
2. **Supporting patterns** — only if essential to the demo (not "nice to have")
3. **What to skip for now** — patterns that add value in production but aren't needed for PoC
4. **Complexity check** — actively question whether a simpler approach works. Default to fewer agents.

Core principle: *"Start with the simplest solution that could work. Add complexity only when it demonstrably improves outcomes."* (Anthropic)

For PoC/hackathon: bias toward **fewer agents with more tools** over **many specialized agents**. Each agent adds coordination complexity that slows prototyping.

## Step 4: Write Architecture Document and Generate Diagram

Read `references/output-template.md` for the document structure and Mermaid diagram conventions.

Write to: `agent-architecture-{use-case-slug}.md` where the slug is a short kebab-case identifier (e.g., `customer-support-triage`, `research-assistant`).

The document should be **directly actionable** — someone should be able to read it and start building with an agent SDK (Claude Agent SDK, LangGraph, OpenAI Agents SDK) immediately.

### Generate Architecture Diagram

After writing the document, generate an Excalidraw diagram from the embedded Mermaid:

```bash
node scripts/mermaid-to-excalidraw.mjs agent-architecture-{slug}.md
```

This extracts the Mermaid block, converts it to `.excalidraw` JSON via headless browser, and writes `agent-architecture-{slug}.excalidraw`. Add `--open` to launch the native Excalidraw app for annotation.

Also generate a static PNG for embedding in docs or presentations:

```bash
npx @mermaid-js/mermaid-cli -i <(node -e "..." ) -o agent-architecture-{slug}.png -b white --scale 2
```

Or extract the `.mmd` first with `uv run excalidraw-diagram/scripts/extract_mermaid.py` and render with `npx mmdc`.

## Step 5: Review and Refine

Present the document and ask:
1. Does this feel buildable in a hackathon/sprint?
2. Are there agents that could be merged or simplified?
3. Which agent SDK do you plan to use? (so follow-up skills can take over)

## Updating References

Refresh the pattern catalog with latest literature:

```bash
uv run scripts/fetch_references.py
```

This searches for latest blog posts from Anthropic, OpenAI, and Google on agentic patterns and writes discovered sources to `references/latest-sources.md` for manual curation into the main catalog.
