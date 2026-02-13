# Agent Skills for Databricks

Skills that extend [Databricks Assistant](https://docs.databricks.com/aws/en/assistant/skills) (or other coding agents like Claude Code) with Databricks-specific features or workflows.

## Skills

* **[improve-genie-space](./improve-genie-space/)** — Analyze and optimize Genie Space (AI/BI Dashboard) configurations against best practices
* **[parse-documents](./parse-documents/)** — WIP
* **[create-update-vector-search-index](./create-update-vector-search-index/)** — WIP
* **[draw-architecture-diagram]()** — WIP

## Setup

### Databricks Assistant

Copy the desired skill folder into your workspace skills directory:

```text
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
claude --skill ./{skill-name}
```
