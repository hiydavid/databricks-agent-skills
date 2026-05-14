# Pattern Selection Decision Framework

Use this framework to systematically evaluate which agentic pattern(s) best fit a given use case.

## Decision Tree

```
START: Can the task be solved with a single LLM call + good prompt?
├─ YES → Use a single prompt. Stop here.
└─ NO → Is the workflow fixed and predictable?
   ├─ YES → Are the steps sequential with dependencies?
   │  ├─ YES → **Sequential Pipeline / Prompt Chaining**
   │  └─ NO → Can steps run independently?
   │     ├─ YES → **Parallelization / Fan-Out Gather**
   │     └─ NO → Mix of both → **Sequential + Parallel composite**
   └─ NO → Does input need classification/routing first?
      ├─ YES → **Routing / Coordinator-Dispatcher**
      │  └─ Then apply this tree to each route's downstream
      └─ NO → Is the task decomposition known at design time?
         ├─ YES but varies by input → **Orchestrator-Workers**
         └─ NO, fully dynamic → Does it need iterative refinement?
            ├─ YES → Is there a clear pass/fail criteria?
            │  ├─ YES → **Generator-Critic**
            │  └─ NO → **Iterative Refinement / Evaluator-Optimizer**
            └─ NO → Is it open-ended with unpredictable steps?
               ├─ YES → **Autonomous Agent / ReAct**
               └─ NO → Does it need multiple expert perspectives?
                  ├─ YES → **Swarm / Debate**
                  └─ NO → **Orchestrator-Workers** (default for complex tasks)
```

## Overlay: Cross-Cutting Pattern Selection

After selecting a primary pattern, evaluate these overlays:

| Question | If YES, add... |
|----------|----------------|
| Are there high-stakes or irreversible decisions? | **Human-in-the-Loop** at decision points |
| Do agents need to fully transfer control to specialists? | **Handoffs** between agents |
| Does output quality need guaranteed minimum bar? | **Generator-Critic** loop on outputs |
| Are there independent evaluation dimensions? | **Parallelization** for evaluation |
| Is the system customer-facing with varied intents? | **Routing** as entry layer |

## Complexity Ladder

Always start at the lowest level that meets requirements. Move up only when demonstrably needed.

```
Level 0: Single prompt with good instructions
Level 1: Prompt chaining (2-3 sequential calls)
Level 2: Routing + specialized prompts
Level 3: Parallelization for speed/quality
Level 4: Orchestrator-workers for dynamic decomposition
Level 5: Autonomous agents with tool use
Level 6: Multi-agent systems with handoffs/debate
```

## Evaluation Criteria Matrix

Rate each criterion 1-5 for the use case, then match to patterns:

| Criterion | Low (1-2) | High (4-5) |
|-----------|-----------|------------|
| **Task predictability** | Autonomous Agent, Swarm | Sequential Pipeline, Routing |
| **Latency sensitivity** | Evaluator-Optimizer, Swarm | Parallelization, Single Agent |
| **Correctness criticality** | Single prompt, Pipeline | Generator-Critic, Human-in-Loop |
| **Cost sensitivity** | Parallelization, Swarm expensive | Sequential, Routing (model tiering) |
| **Scale of decomposition** | Single Agent, Chaining | Orchestrator-Workers, Hierarchical |
| **Human oversight need** | Autonomous Agent | Human-in-the-Loop |
| **Input variability** | Sequential Pipeline | Routing, Coordinator-Dispatcher |

## Common Composite Patterns

Most production systems combine patterns. Common compositions:

1. **Routing → Specialist Pipelines**: Classify input, then run domain-specific sequential workflows
2. **Orchestrator → Parallel Workers → Critic**: Decompose task, run subtasks in parallel, validate aggregated output
3. **Pipeline with Human Gates**: Sequential steps with human approval at critical transitions
4. **Research System** (Anthropic pattern): Orchestrator → parallel subagents → iterative refinement → synthesis
5. **Customer Support Stack**: Router → specialist agents with handoffs → escalation to human

## Red Flags: When NOT to Use Multi-Agent

- The task can be solved with a well-crafted single prompt
- You're adding agents for "architecture" rather than measurable improvement
- Latency budget is < 2 seconds and the task is simple
- You don't have evaluation metrics to prove multi-agent outperforms single-agent
- The team cannot maintain/debug the added complexity
- Data volume is low enough that batch processing with a single agent suffices
