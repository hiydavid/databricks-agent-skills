# Agent Skills for Databricks

Skills that extend Databricks-aware coding agents with Databricks-specific workflows.

This repository contains one active skill distribution and one archive:

- **External-agent skills** under `external-agent/` for coding agents that run outside Databricks and need explicit helper scripts or workspace access instructions.
- **Deprecated Genie Code-only skills** under `genie-code/deprecated/`, retained for historical reference only.

Databricks Genie Code now provides native skills for all former Genie Code workflows in this repository, including creating Metric Views, optimizing Genie queries, and creating, diagnosing, and improving Genie agents and spaces.

## Skills

### External-Agent Skills

| Skill | Description |
|-------|-------------|
| **[external-agent/create-genie-space](./external-agent/create-genie-space/)** | Create a Genie Space config from Unity Catalog datasets with evidence-gated readiness profiling and local JSON validation |
| **[external-agent/diagnose-genie-space](./external-agent/diagnose-genie-space/)** | Diagnose failing Genie questions, Monitor feedback trends, and response latency; produce a concrete tuning plan |
| **[external-agent/optimize-genie-space](./external-agent/optimize-genie-space/)** | Iteratively improve Genie Space quality with versioned configs, mandatory rollback snapshots, Chat-mode benchmark evals, and accuracy comparison |
| **[external-agent/multi-agent-architecture](./external-agent/multi-agent-architecture/)** | Design multi-agent architectures for PoC/hackathon/MVP projects with Mermaid diagrams |
| **[external-agent/parse-documents](./external-agent/parse-documents/)** | Build a Databricks document parsing and chunking pipeline for RAG ingestion |

### Deprecated Genie Code Skills

These skills have been superseded by Genie Code's native skills and should not be installed for new workflows.

The associated [skill update guide](./genie-code/deprecated/skill-update-guide.md), originally distilled from work on `diagnose-genie-space`, is also archived with this bundle.

| Archived skill | Replacement |
|----------------|-------------|
| **[genie-code/deprecated/create-metric-view](./genie-code/deprecated/create-metric-view/)** | Use Genie Code's native skill for creating Metric Views |
| **[genie-code/deprecated/create-genie-space](./genie-code/deprecated/create-genie-space/)** | Use Genie Code's native skill for creating Genie agents and spaces |
| **[genie-code/deprecated/diagnose-genie-space](./genie-code/deprecated/diagnose-genie-space/)** | Use Genie Code's native skill for diagnosing Genie agents and spaces |
| **[genie-code/deprecated/optimize-genie-query](./genie-code/deprecated/optimize-genie-query/)** | Use Genie Code's native skill for optimizing Genie queries |
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

Use Genie Code's native skills for these workflows. This repository no longer provides active Genie Code-only skills; the versions under `genie-code/deprecated/` are historical references and should not be installed for new workflows. See the [Databricks Genie Code skills docs](https://docs.databricks.com/aws/en/genie-code/skills) for details.

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
├── genie-code/
│   └── deprecated/              # Superseded by native Genie Code skills
│       ├── create-metric-view/
│       ├── create-genie-space/
│       ├── diagnose-genie-space/
│       ├── optimize-genie-query/
│       ├── optimize-genie-space/
│       └── skill-update-guide.md
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
