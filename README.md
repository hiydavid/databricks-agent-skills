# Agent Skills for Databricks

Skills that extend [Databricks Assistant](https://docs.databricks.com/aws/en/assistant/skills) (or other coding agents like Claude Code) with Databricks-specific features or workflows.

## Skills

| Skill | Description |
|-------|-------------|
| **[diagnose-genie-space](./diagnose-genie-space/)** | Diagnose failing Genie questions, inspect space context, and produce a concrete tuning plan |
| **[optimize-genie-space](./optimize-genie-space/)** | Iteratively improve Genie Space quality by versioning configs, validating changes, running benchmark evals, and comparing accuracy |
| **[multi-agent-architecture](./multi-agent-architecture/)** | Design multi-agent architectures for PoC/hackathon/MVP projects with Mermaid diagrams |
| **[parse-documents](./parse-documents/)** | Build a Databricks document parsing and chunking pipeline for RAG ingestion |

## Setup

### Claude Code

Copy or symlink the desired skill folders into any project's `.claude/skills/` directory. Skills are auto-triggered by Claude when relevant to the conversation.

```bash
git clone https://github.com/hiydavid/databricks-agent-skills.git
cd databricks-agent-skills

# Add all skills to a project
mkdir -p ~/my-project/.claude/skills
for skill in diagnose-genie-space optimize-genie-space multi-agent-architecture parse-documents; do
  ln -s "$PWD/$skill" ~/my-project/.claude/skills/$skill
done

# Add a single skill
ln -s "$PWD/diagnose-genie-space" ~/my-project/.claude/skills/diagnose-genie-space
```

If you prefer copying instead of symlinking, use `cp -R <skill> ~/my-project/.claude/skills/`.

### Codex

Copy or symlink the desired skill folders into your Codex skills directory:

```bash
git clone https://github.com/hiydavid/databricks-agent-skills.git
cd databricks-agent-skills

# Add all skills
mkdir -p ~/.codex/skills
for skill in diagnose-genie-space optimize-genie-space multi-agent-architecture parse-documents; do
  ln -s "$PWD/$skill" ~/.codex/skills/$skill
done

# Add a single skill
ln -s "$PWD/diagnose-genie-space" ~/.codex/skills/diagnose-genie-space
```

If you prefer copying instead of symlinking, use `cp -R <skill> ~/.codex/skills/`.

### Databricks Genie Code

Copy the desired skill folder into your workspace skills directory:

```text
/Users/{username}/.assistant/skills/
└── {skill-name}/
    ├── SKILL.md
    ├── scripts/
    └── references/
```

The Assistant automatically discovers skills in agent mode. See the [Databricks docs](https://docs.databricks.com/aws/en/assistant/skills) for details.

## Development

### Project structure

```
databricks-agent-skills/
├── diagnose-genie-space/        # Question-level diagnosis and tuning advice for Genie Spaces
│   ├── SKILL.md
│   ├── scripts/
│   └── references/
├── optimize-genie-space/        # Benchmark-driven iterative optimization
│   ├── SKILL.md
│   ├── scripts/
│   └── references/
├── multi-agent-architecture/
├── parse-documents/
├── scripts/                     # Dev tooling
│   ├── manage-skills.sh
│   └── mermaid-to-excalidraw.mjs
├── test-skills/                 # Test scenarios for validating skills
│   └── equity-analysis.md
├── genai_hackathon_starter_guide.md
├── package.json
└── README.md
```

### Adding a new skill

1. Create the skill folder: `mkdir -p my-skill`
2. Add `my-skill/SKILL.md` with frontmatter (`name`, `description`) and workflow instructions
3. Add any supporting files under `my-skill/references/` or `my-skill/scripts/`
4. Install and test by copying or symlinking `my-skill/` into a project's `.claude/skills/` directory

### Testing skills

1. Add the skill to a test project by copying or symlinking its folder into `.claude/skills/`
2. Start a new Claude Code session in that project
3. Trigger the skill naturally with a representative user request
4. Edit the skill files, start a new session, and re-test (symlinks pick up changes automatically)

### Contributing

1. Clone the repo and create a branch
2. Follow the "Adding a new skill" steps above
3. Test locally, then open a PR
