# Agent Skills for Databricks

Skills that extend Databricks-aware coding agents with Databricks-specific workflows.

This repository contains one active skill, plus two deprecated archives:

- **External-agent skills** under `external-agent/` for coding agents that run outside Databricks.
- **Deprecated external-agent skills** under `external-agent/deprecated/`, replaced by official [Databricks Agent Skills](https://github.com/databricks/databricks-agent-skills).
- **Deprecated Genie Code-only skills** under `genie-code/deprecated/`, retained for historical reference only.

The official [Databricks Agent Skills](https://github.com/databricks/databricks-agent-skills) repo now provides canonical skills for Genie Agent creation and management (`databricks-genie-agents`), document parsing and RAG (`databricks-ai-functions` + `databricks-vector-search`), and many other Databricks workflows. The skills moved to `external-agent/deprecated/` have been superseded by these official skills.

## Skills

### External-Agent Skills

| Skill | Description |
|-------|-------------|
| **[external-agent/multi-agent-architecture](./external-agent/multi-agent-architecture/)** | Design multi-agent architectures for PoC/hackathon/MVP projects with Mermaid diagrams |

### Deprecated External-Agent Skills

These skills have been superseded by official [Databricks Agent Skills](https://github.com/databricks/databricks-agent-skills) and should not be installed for new workflows.

| Archived skill | Replacement |
|----------------|-------------|
| **[external-agent/deprecated/create-genie-space](./external-agent/deprecated/create-genie-space/)** | Use [`databricks-genie-agents`](https://github.com/databricks/databricks-agent-skills/tree/main/skills/databricks-genie-agents) for Genie Agent creation and management |
| **[external-agent/deprecated/diagnose-genie-space](./external-agent/deprecated/diagnose-genie-space/)** | Use [`databricks-genie-agents`](https://github.com/databricks/databricks-agent-skills/tree/main/skills/databricks-genie-agents) for Genie Agent diagnosis and improvement |
| **[external-agent/deprecated/optimize-genie-space](./external-agent/deprecated/optimize-genie-space/)** | Use [`databricks-genie-agents`](https://github.com/databricks/databricks-agent-skills/tree/main/skills/databricks-genie-agents) for Genie Agent optimization |
| **[external-agent/deprecated/parse-documents](./external-agent/deprecated/parse-documents/)** | Use [`databricks-ai-functions`](https://github.com/databricks/databricks-agent-skills/tree/main/skills/databricks-ai-functions) + [`databricks-vector-search`](https://github.com/databricks/databricks-agent-skills/tree/main/skills/databricks-vector-search) for document parsing and RAG pipelines |

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

Use the active skill under `external-agent/`. Copy or symlink the skill folder into any project's `.claude/skills/` directory. Skills are auto-triggered by Claude when relevant to the conversation.

```bash
git clone https://github.com/hiydavid/databricks-agent-skills.git
cd databricks-agent-skills

# Add the multi-agent architecture skill
mkdir -p ~/my-project/.claude/skills
ln -s "$PWD/external-agent/multi-agent-architecture" ~/my-project/.claude/skills/multi-agent-architecture
```

If you prefer copying instead of symlinking, use `cp -R external-agent/multi-agent-architecture ~/my-project/.claude/skills/`.

For Genie Agent and document parsing workflows, use the official [Databricks Agent Skills](https://github.com/databricks/databricks-agent-skills) instead.

### Codex

Use the active skill under `external-agent/`. Copy or symlink the skill folder into your Codex skills directory:

```bash
git clone https://github.com/hiydavid/databricks-agent-skills.git
cd databricks-agent-skills

# Add the multi-agent architecture skill
mkdir -p ~/.codex/skills
ln -s "$PWD/external-agent/multi-agent-architecture" ~/.codex/skills/multi-agent-architecture
```

If you prefer copying instead of symlinking, use `cp -R external-agent/multi-agent-architecture ~/.codex/skills/`.

For Genie Agent and document parsing workflows, use the official [Databricks Agent Skills](https://github.com/databricks/databricks-agent-skills) instead.

### Databricks Genie Code

Use Genie Code's native skills for these workflows. This repository no longer provides active Genie Code-only skills; the versions under `genie-code/deprecated/` are historical references and should not be installed for new workflows. See the [Databricks Genie Code skills docs](https://docs.databricks.com/aws/en/genie-code/skills) for details.

## Development

### Project structure

```
databricks-agent-skills/
├── external-agent/                  # Skills for Codex, Claude Code, and other external agents
│   ├── multi-agent-architecture/    # Active: general multi-agent architecture design
│   └── deprecated/                  # Superseded by official Databricks Agent Skills
│       ├── create-genie-space/
│       ├── diagnose-genie-space/
│       ├── optimize-genie-space/
│       └── parse-documents/
├── genie-code/
│   └── deprecated/                  # Superseded by native Genie Code skills
│       ├── create-metric-view/
│       ├── create-genie-space/
│       ├── diagnose-genie-space/
│       ├── optimize-genie-query/
│       ├── optimize-genie-space/
│       └── skill-update-guide.md
└── README.md
```

### Adding a new skill

1. Choose the distribution: `external-agent/` for agents outside Databricks. Only add skills that do not overlap with the official [Databricks Agent Skills](https://github.com/databricks/databricks-agent-skills) repo. The `genie-code/` directory is now a deprecated archive only.
2. Create the skill folder: `mkdir -p external-agent/my-skill`.
3. Add `SKILL.md` with frontmatter (`name`, `description`) and workflow instructions. The `name` must match the skill folder name, and the `description` should disambiguate the skill from its siblings so agents trigger the right one.
4. Add any supporting files under `references/` or `scripts/` when that distribution needs them. Reference scripts with skill-relative paths (`<skill-dir>/scripts/...`), not checkout-layout paths.
5. Install and test by copying or symlinking the skill folder into the target agent's skills directory.

### Testing skills

1. Add the skill to a test project by copying or symlinking its folder into the target agent's skills directory.
2. Start a new Claude Code session in that project
3. Trigger the skill naturally with a representative user request
4. Edit the skill files, start a new session, and re-test (symlinks pick up changes automatically)

Skills with helper scripts may also carry unit tests. For example, the deprecated create-genie-space validator tests can still be run with:

```bash
python3 -m unittest discover -s external-agent/deprecated/create-genie-space/tests
```

### Contributing

1. Clone the repo and create a branch
2. Follow the "Adding a new skill" steps above
3. Test locally, then open a PR
