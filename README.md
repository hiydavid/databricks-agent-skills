# Agent Skills for Databricks

Skills that extend [Databricks Assistant](https://docs.databricks.com/aws/en/assistant/skills) (or other coding agents like Claude Code) with Databricks-specific features or workflows.

## Skills

* **[improve-genie-space](./databricks-skills/improve-genie-space/)** — Analyze and optimize Genie Space (AI/BI Dashboard) configurations against best practices

## Setup

### Databricks Assistant

Copy the desired skill folder from `databricks-skills/` into your workspace skills directory:

```
/Users/{username}/.assistant/skills/
└── {skill-name}/
    ├── SKILL.md
    ├── scripts/
    └── references/
```

The Assistant automatically discovers skills in agent mode. See the [Databricks docs](https://docs.databricks.com/aws/en/assistant/skills) for details.

### Claude Code

Add the skill path to your `CLAUDE.md` or use `--skill` when invoking Claude Code:

```bash
claude --skill ./databricks-skills/{skill-name}
```
