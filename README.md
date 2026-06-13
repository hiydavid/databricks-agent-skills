# Agent Skills for Databricks

Skills that extend Databricks-aware coding agents with Databricks-specific workflows.

This repository has two skill distributions:

- **External-agent skills** under `external-agent/` for coding agents that run outside Databricks and need explicit helper scripts or workspace access instructions.
- **Genie Code-only skills** under `genie-code/` for Databricks Genie Code Agent mode, where the agent already has Databricks workspace context and native execution tools.

## Skills

### External-Agent Skills

| Skill | Description |
|-------|-------------|
| **[external-agent/create-genie-space](./external-agent/create-genie-space/)** | Create a Genie Space config from Unity Catalog datasets with external-agent validation helpers |
| **[external-agent/diagnose-genie-space](./external-agent/diagnose-genie-space/)** | Diagnose failing Genie questions, inspect space context, and produce a concrete tuning plan |
| **[external-agent/optimize-genie-space](./external-agent/optimize-genie-space/)** | Iteratively improve Genie Space quality by versioning configs, validating changes, running benchmark evals, and comparing accuracy |
| **[external-agent/multi-agent-architecture](./external-agent/multi-agent-architecture/)** | Design multi-agent architectures for PoC/hackathon/MVP projects with Mermaid diagrams |
| **[external-agent/parse-documents](./external-agent/parse-documents/)** | Build a Databricks document parsing and chunking pipeline for RAG ingestion |

### Genie Code-Only Skills

| Skill | Description |
|-------|-------------|
| **[genie-code/create-metric-view](./genie-code/create-metric-view/)** | Create governed Unity Catalog Metric Views with expert intake, read-only profiling, YAML/DDL drafting, and validation |
| **[genie-code/create-genie-space](./genie-code/create-genie-space/)** | Create or refine Genie Spaces using Genie Code's native Unity Catalog and workspace context |
| **[genie-code/diagnose-genie-space](./genie-code/diagnose-genie-space/)** | Diagnose Genie Space quality and benchmark health issues inside Databricks without external setup |
| **[genie-code/optimize-genie-space](./genie-code/optimize-genie-space/)** | Tune Genie Space quality with Databricks-native benchmark review, repair, pruning, and iteration |
| **[genie-code/optimize-genie-query](./genie-code/optimize-genie-query/)** | Run approved benchmark-driven Genie query triage using Query History performance insights, Query Profile, table layout, and warehouse evidence |

## Setup

### Claude Code

Use the external-agent skills under `external-agent/`. Copy or symlink the desired skill folders into any project's `.claude/skills/` directory. Skills are auto-triggered by Claude when relevant to the conversation.

```bash
git clone https://github.com/hiydavid/databricks-agent-skills.git
cd databricks-agent-skills

# Add all skills to a project
mkdir -p ~/my-project/.claude/skills
for skill in create-genie-space diagnose-genie-space optimize-genie-space multi-agent-architecture parse-documents; do
  ln -s "$PWD/external-agent/$skill" ~/my-project/.claude/skills/$skill
done

# Add a single skill
ln -s "$PWD/external-agent/diagnose-genie-space" ~/my-project/.claude/skills/diagnose-genie-space
```

If you prefer copying instead of symlinking, use `cp -R external-agent/<skill> ~/my-project/.claude/skills/`.

### Codex

Use the external-agent skills under `external-agent/`. Copy or symlink the desired skill folders into your Codex skills directory:

```bash
git clone https://github.com/hiydavid/databricks-agent-skills.git
cd databricks-agent-skills

# Add all skills
mkdir -p ~/.codex/skills
for skill in create-genie-space diagnose-genie-space optimize-genie-space multi-agent-architecture parse-documents; do
  ln -s "$PWD/external-agent/$skill" ~/.codex/skills/$skill
done

# Add a single skill
ln -s "$PWD/external-agent/diagnose-genie-space" ~/.codex/skills/diagnose-genie-space
```

If you prefer copying instead of symlinking, use `cp -R external-agent/<skill> ~/.codex/skills/`.

### Databricks Genie Code

Use the Databricks-native skills under `genie-code/`. These versions are intentionally less prescriptive because Genie Code Agent mode already has workspace context, Unity Catalog metadata, and native execution tools.

Copy the desired Genie Code-only skill folders into a workspace or user skills directory:

```text
Workspace/.assistant/skills/
└── create-genie-space/
    ├── SKILL.md
    └── references/
```

```text
/Users/{username}/.assistant/skills/
└── optimize-genie-space/
    ├── SKILL.md
    └── references/
```

For example, copy `genie-code/create-metric-view`, `genie-code/create-genie-space`, `genie-code/diagnose-genie-space`, `genie-code/optimize-genie-space`, or `genie-code/optimize-genie-query` into one of those `.assistant/skills/` locations. Genie Code automatically discovers skills in Agent mode. See the [Databricks Genie Code skills docs](https://docs.databricks.com/aws/en/genie-code/skills) for details.

Example prompt for iterative Genie Space optimization:

```text
use @optimize-genie-space skill and optimize my genie space, id: <INSERT_GENIE_ID> . Iterate until you reach or exceeds 90% in benchmark accuracy. Stop when you reach the goal.
```

## Development

### Project structure

```
databricks-agent-skills/
├── external-agent/              # Skills for Codex, Claude Code, and other external agents
│   ├── create-genie-space/
│   ├── diagnose-genie-space/
│   ├── multi-agent-architecture/
│   ├── optimize-genie-space/
│   └── parse-documents/
├── genie-code/                  # Databricks Genie Code-only skill pack
│   ├── create-metric-view/
│   ├── create-genie-space/
│   ├── diagnose-genie-space/
│   ├── optimize-genie-space/
│   └── optimize-genie-query/
├── package.json
└── README.md
```

### Adding a new skill

1. Choose the distribution: `external-agent/` for agents outside Databricks, or `genie-code/` for Databricks Genie Code.
2. Create the skill folder: `mkdir -p external-agent/my-skill` or `mkdir -p genie-code/my-skill`.
3. Add `SKILL.md` with frontmatter (`name`, `description`) and workflow instructions.
4. Add any supporting files under `references/` or `scripts/` when that distribution needs them.
5. Install and test by copying or symlinking the skill folder into the target agent's skills directory.

### Testing skills

1. Add the skill to a test project by copying or symlinking its folder into the target agent's skills directory.
2. Start a new Claude Code session in that project
3. Trigger the skill naturally with a representative user request
4. Edit the skill files, start a new session, and re-test (symlinks pick up changes automatically)

### Contributing

1. Clone the repo and create a branch
2. Follow the "Adding a new skill" steps above
3. Test locally, then open a PR
