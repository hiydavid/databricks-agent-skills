# Agentic Design Patterns Catalog

Curated from published literature by Anthropic, OpenAI, and Google. Last updated: 2026-02-13.

## Contents

- [Foundational Concepts](#foundational-concepts) — Workflows vs Agents, Orchestration approaches
- [Pattern Catalog](#pattern-catalog)
  1. Prompt Chaining / Sequential Pipeline
  2. Routing / Coordinator-Dispatcher
  3. Parallelization / Fan-Out Gather
  4. Orchestrator-Workers / Hierarchical Decomposition
  5. Evaluator-Optimizer / Generator-Critic
  6. Autonomous Agent / ReAct
  7. Handoffs / Decentralized Multi-Agent
  8. Swarm / Collaborative Debate
  9. Human-in-the-Loop
- [Cross-Cutting Concerns](#cross-cutting-concerns) — Tool design, Memory, Error handling, Evaluation
- [Source Literature](#source-literature)

---

## Foundational Concepts

### Workflows vs Agents (Anthropic)

- **Workflows**: Systems where LLMs and tools are orchestrated through predefined code paths. Predictable, debuggable, lower cost.
- **Agents**: Systems where LLMs dynamically direct their own processes and tool usage. Flexible, higher cost, requires guardrails.

**Rule of thumb**: Start with workflows. Graduate to agents only when the task requires dynamic decision-making that can't be hardcoded.

### Orchestration Approaches (OpenAI)

- **Code-orchestrated**: Deterministic routing via structured outputs and conditional logic. More predictable.
- **LLM-orchestrated**: The model decides next steps, tool calls, and handoffs. More flexible but less predictable.

---

## Pattern Catalog

### 1. Prompt Chaining / Sequential Pipeline

**Source**: Anthropic, Google ADK

**Description**: Tasks decomposed into sequential steps. Each LLM call processes the prior output. Programmatic gates validate intermediate results.

**When to use**:
- Fixed, well-understood subtasks
- Each step benefits from focused attention
- Intermediate validation is valuable

**Examples**: Document generation (outline → validate → draft → edit), data transformation pipelines, multi-stage content creation

**Trade-offs**: Higher latency for improved accuracy. Only works when decomposition is predictable. Easy to debug.

---

### 2. Routing / Coordinator-Dispatcher

**Source**: Anthropic, Google ADK, OpenAI

**Description**: Classifies input and directs it to specialized downstream processes. A central agent analyzes intent and routes to the best-suited specialist.

**When to use**:
- Multiple distinct input categories requiring different handling
- Specialist agents outperform generalists on their domain
- Cost optimization via model selection (route simple queries to smaller models)

**Examples**: Customer service triage (billing/technical/general), intent-based assistant routing, tiered model selection

**Trade-offs**: Requires accurate classification. Misrouting cascades into wrong specialist. Adds one LLM call of latency.

---

### 3. Parallelization / Fan-Out Gather

**Source**: Anthropic, Google ADK

**Description**: Independent subtasks executed simultaneously, results aggregated. Two variants:

- **Sectioning**: Different subtasks in parallel (e.g., guardrails + main response simultaneously)
- **Voting**: Same task multiple times for consensus (e.g., multiple code reviewers)

**When to use**:
- Subtasks have no dependencies on each other
- Speed is important
- Multiple perspectives improve quality or confidence

**Examples**: Multi-source research, parallel code review, concurrent evaluation dimensions, guardrail screening alongside response generation

**Trade-offs**: Increased cost (N parallel calls). Race conditions possible with shared state. Synthesis of results adds complexity.

---

### 4. Orchestrator-Workers / Hierarchical Decomposition

**Source**: Anthropic, Google ADK

**Description**: Central LLM dynamically breaks down tasks and delegates to worker LLMs. Unlike parallelization, the subtasks aren't predefined — the orchestrator decides at runtime.

**When to use**:
- Subtask count and nature depend on input
- Complex problems requiring multi-level reasoning
- Tasks that exceed a single agent's context window

**Examples**: Multi-file code changes, research across many sources, complex project planning, Anthropic's multi-agent research system (lead agent + 3-10 subagents)

**Anthropic's scaling guidelines**:
- Simple fact-finding: 1 agent, 3-10 tool calls
- Direct comparisons: 2-4 subagents, 10-15 calls each
- Complex research: 10+ subagents with divided responsibilities

**Trade-offs**: Higher complexity and latency from nested decomposition. Requires robust error handling. Vague delegation causes duplication — each subagent needs clear objective, output format, tool guidance, and task boundaries.

---

### 5. Evaluator-Optimizer / Generator-Critic

**Source**: Anthropic, Google ADK

**Description**: Iterative loop where one LLM generates and another evaluates. Two variants:

- **Generator-Critic (pass/fail)**: Critic validates against fixed criteria. Failed outputs loop back for revision.
- **Iterative Refinement (qualitative)**: Progressive quality improvement until plateau or iteration limit.

**When to use**:
- Clear evaluation criteria exist
- Output correctness is critical (code generation, compliance)
- Human-like iterative refinement is beneficial

**Examples**: Code generation with test validation, literary translation refinement, content compliance checking, complex search requiring multiple analysis rounds

**Trade-offs**: Multiple iterations increase latency and cost. Effective only when evaluation criteria are explicit. Risk of diminishing returns on iterations.

---

### 6. Autonomous Agent / ReAct

**Source**: Anthropic, Google

**Description**: LLM dynamically directs its own processes in a loop: reason → act → observe → repeat. The agent maintains control over how it accomplishes tasks, pausing for human input at checkpoints.

**When to use**:
- Open-ended problems with unpredictable step counts
- Cannot hardcode fixed paths
- Trusted environments with human oversight available

**Examples**: GitHub issue resolution (SWE-bench), computer use automation, complex debugging, open-ended research

**Implementation principles** (Anthropic):
1. Maintain simplicity in agent design
2. Prioritize transparency (explicit planning steps)
3. Carefully engineer agent-computer interfaces through tool documentation

**Trade-offs**: Highest cost and latency. Compounding error risk. Requires extensive testing in sandboxed environments. Non-deterministic behavior requires observability.

---

### 7. Handoffs / Decentralized Multi-Agent

**Source**: OpenAI

**Description**: Agents transfer execution control to each other. Unlike orchestrator-workers (centralized), handoffs create a decentralized graph where any agent can hand off to any other.

**When to use**:
- Conversation triage where specialist fully takes over
- Peer-to-peer collaboration without central coordinator
- Scenarios where the "best next agent" depends on conversation state

**Examples**: Customer support escalation chains, multi-step form filling with specialist handoffs, collaborative writing with style/fact/grammar specialists

**Trade-offs**: Harder to reason about control flow. Requires clear handoff protocols. Optional "handoff back" for returning control.

---

### 8. Swarm / Collaborative Debate

**Source**: Google, OpenAI (Swarm framework)

**Description**: All-to-all communication between specialized agents. Agents iteratively refine solutions through debate, critique, and collaborative revision.

**When to use**:
- Complex problems benefiting from multiple expert perspectives
- No single correct approach — need collaborative exploration
- High-stakes decisions where debate improves quality

**Examples**: Multi-expert analysis, policy recommendation, architectural design review

**Trade-offs**: Most complex and costly pattern. Requires sophisticated exit conditions. Coordination overhead scales quadratically with agent count.

---

### 9. Human-in-the-Loop

**Source**: Google ADK, All providers

**Description**: Agents handle routine work but pause for human authorization at predefined checkpoints on high-stakes or irreversible decisions.

**When to use**:
- Financial transactions, production deployments
- Sensitive data access or modification
- Subjective judgment needed
- Regulatory compliance requirements

**Examples**: Approval workflows, content moderation escalation, deployment gates, medical/legal review checkpoints

**Trade-offs**: Introduces latency waiting for approval. Requires robust approval infrastructure and UX. Must define clear escalation criteria.

---

## Cross-Cutting Concerns

### Tool Design (Anthropic)
"Agent-tool interfaces are as critical as human-computer interfaces." Each tool needs:
- Distinct purpose with no overlap
- Clear descriptions and parameter documentation
- Error messages that help the agent recover

### Memory & State Management (Anthropic)
- Save plans to external memory before context windows fill (~200K tokens)
- Use checkpoints for long-running agents to resume on failure
- Compress context intelligently rather than losing it

### Error Handling (Anthropic)
- Minor issues compound in multi-agent systems — design for checkpoint recovery
- Non-determinism requires observability of decision patterns, not just outputs
- Use "rainbow deployments" — gradual traffic shifting to avoid disrupting running agents

### Evaluation (Anthropic)
- Start with ~20 representative queries for early testing
- Use LLM-as-judge rubrics (factual accuracy, completeness, source quality, efficiency)
- Human testing catches hallucinations and edge cases automated methods miss

---

## Source Literature

- Anthropic: [Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)
- Anthropic: [How We Built Our Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system)
- OpenAI: [A Practical Guide to Building Agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/)
- OpenAI: [Orchestrating Agents: Routines and Handoffs](https://developers.openai.com/cookbook/examples/orchestrating_agents)
- Google: [Developer's Guide to Multi-Agent Patterns in ADK](https://developers.googleblog.com/developers-guide-to-multi-agent-patterns-in-adk/)
- Google: [Choose a Design Pattern for Your Agentic AI System](https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system)
