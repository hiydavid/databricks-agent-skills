# Agent Skills for Databricks

Skills that extend Databricks-aware coding agents with Databricks-specific workflows.

This repository has two skill distributions:

- **External-agent skills** under `external-agent/` for coding agents that run outside Databricks and need explicit helper scripts or workspace access instructions.
- **Genie Code-only skills** under `genie-code/` for specialized workflows that are not already built into Databricks Genie Code.

Databricks Genie Code now provides native skills for creating, diagnosing, and improving Genie agents and spaces. The older repository-provided versions of those workflows are deprecated and retained under `genie-code/deprecated/` for historical reference only.

## Skills

### External-Agent Skills

| Skill | Description |
|-------|-------------|
| **[external-agent/create-genie-space](./external-agent/create-genie-space/)** | Create a Genie Space config from Unity Catalog datasets with evidence-gated readiness profiling and local JSON validation |
| **[external-agent/diagnose-genie-space](./external-agent/diagnose-genie-space/)** | Diagnose failing Genie questions, Monitor feedback trends, and response latency; produce a concrete tuning plan |
| **[external-agent/optimize-genie-space](./external-agent/optimize-genie-space/)** | Iteratively improve Genie Space quality with versioned configs, mandatory rollback snapshots, Chat-mode benchmark evals, and accuracy comparison |
| **[external-agent/multi-agent-architecture](./external-agent/multi-agent-architecture/)** | Design multi-agent architectures for PoC/hackathon/MVP projects with Mermaid diagrams |
| **[external-agent/parse-documents](./external-agent/parse-documents/)** | Build a Databricks document parsing and chunking pipeline for RAG ingestion |

### Genie Code-Only Skills

| Skill | Description |
|-------|-------------|
| **[genie-code/create-metric-view](./genie-code/create-metric-view/)** | Create governed Unity Catalog Metric Views with expert intake, read-only profiling, YAML/DDL drafting, and validation |
| **[genie-code/optimize-genie-query](./genie-code/optimize-genie-query/)** | Run approved benchmark-driven Genie query triage using Query History performance insights, Query Profile, table layout, and warehouse evidence |

### Deprecated Genie Code Skills

These skills have been superseded by Genie Code's native skills and should not be installed for new workflows.

| Archived skill | Replacement |
|----------------|-------------|
| **[genie-code/deprecated/create-genie-space](./genie-code/deprecated/create-genie-space/)** | Use Genie Code's native skill for creating Genie agents and spaces |
| **[genie-code/deprecated/diagnose-genie-space](./genie-code/deprecated/diagnose-genie-space/)** | Use Genie Code's native skill for diagnosing Genie agents and spaces |
| **[genie-code/deprecated/optimize-genie-space](./genie-code/deprecated/optimize-genie-space/)** | Use Genie Code's native skill for improving Genie agents and spaces |

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

Use Genie Code's native skills to create, diagnose, or improve Genie agents and spaces. Do not install the archived replacements under `genie-code/deprecated/` for new workflows.

For specialized workflows not covered by those native skills, copy an active skill under `genie-code/` into a workspace or user skills directory:

```text
Workspace/.assistant/skills/
└── create-metric-view/
    ├── SKILL.md
    └── references/
```

```text
/Users/{username}/.assistant/skills/
└── optimize-genie-query/
    ├── SKILL.md
    └── references/
```

The active repository-provided Genie Code skills are `genie-code/create-metric-view` and `genie-code/optimize-genie-query`. Genie Code automatically discovers installed skills in Agent mode. See the [Databricks Genie Code skills docs](https://docs.databricks.com/aws/en/genie-code/skills) for details.

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
├── genie-code/                  # Specialized Databricks Genie Code skills
│   ├── create-metric-view/
│   ├── optimize-genie-query/
│   └── deprecated/              # Superseded by native Genie Code skills
│       ├── create-genie-space/
│       ├── diagnose-genie-space/
│       └── optimize-genie-space/
└── README.md
```

### Adding a new skill

1. Choose the distribution: `external-agent/` for agents outside Databricks, or `genie-code/` for a specialized workflow not already provided natively by Databricks Genie Code.
2. Create the skill folder: `mkdir -p external-agent/my-skill` or `mkdir -p genie-code/my-skill`.
3. Add `SKILL.md` with frontmatter (`name`, `description`) and workflow instructions. The `name` must match the skill folder name, and the `description` should disambiguate the skill from its siblings so agents trigger the right one.
4. Add any supporting files under `references/` or `scripts/` when that distribution needs them. Reference scripts with skill-relative paths (`<skill-dir>/scripts/...`), not checkout-layout paths.
5. Install and test by copying or symlinking the skill folder into the target agent's skills directory.

### Testing skills

1. Add the skill to a test project by copying or symlinking its folder into the target agent's skills directory.
2. Start a new Claude Code session in that project
3. Trigger the skill naturally with a representative user request
4. Edit the skill files, start a new session, and re-test (symlinks pick up changes automatically)

Skills with helper scripts may also carry unit tests. For example, run the create-genie-space validator tests with:

```bash
python3 -m unittest discover -s external-agent/create-genie-space/tests
```

### Contributing

1. Clone the repo and create a branch
2. Follow the "Adding a new skill" steps above
3. Test locally, then open a PR
