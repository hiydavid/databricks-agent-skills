# Agent Skills for Databricks

Skills that extend [Databricks Assistant](https://docs.databricks.com/aws/en/assistant/skills) (or other coding agents like Claude Code) with Databricks-specific features or workflows.

## Skills

| Skill | Slash Command | Description |
|-------|---------------|-------------|
| **[improve-genie-space](./improve-genie-space/)** | `/improve-genie-space` | Analyze and optimize Genie Space (AI/BI Dashboard) configurations against best practices |
| **[multi-agent-architecture](./multi-agent-architecture/)** | `/multi-agent-architecture` | Design multi-agent architectures for PoC/hackathon/MVP projects with Excalidraw diagrams |
| **[parse-documents](./parse-documents/)** | — | Parse and chunk documents for ingestion |
| **[create-update-vector-search-index](./create-update-vector-search-index/)** | — | Create or update Databricks Vector Search indexes |
| **[build-and-deploy-agent](./build-and-deploy-agent/)** | — | *(WIP)* Build and deploy Databricks agents |

## Setup

### Claude Code

Use `manage-skills.sh` to symlink skills into any project's `.claude/skills/` directory. Skills are auto-triggered by Claude when relevant to the conversation.

```bash
git clone https://github.com/hiydavid/databricks-agent-skills.git
cd databricks-agent-skills

# List available skills
./scripts/manage-skills.sh list

# Add all skills to a project
./scripts/manage-skills.sh add --all --to ~/my-project

# Add a single skill
./scripts/manage-skills.sh add multi-agent-architecture --to ~/my-project

# Check what's installed
./scripts/manage-skills.sh status --in ~/my-project

# Remove a skill
./scripts/manage-skills.sh remove multi-agent-architecture --from ~/my-project
```

If `--to`/`--from`/`--in` is omitted, it defaults to the current working directory.

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

## Development

### Project structure

```
databricks-agent-skills/
├── commands/                    # Skill definitions (symlinked into projects as slash commands)
│   ├── improve-genie-space.md
│   └── multi-agent-architecture.md
├── improve-genie-space/         # Skill resources (each folder with SKILL.md)
│   ├── SKILL.md
│   ├── scripts/
│   └── references/
├── multi-agent-architecture/
├── parse-documents/
├── create-update-vector-search-index/
├── build-and-deploy-agent/
├── scripts/                     # Dev tooling
│   ├── manage-skills.sh
│   └── mermaid-to-excalidraw.mjs
├── test-skills/                 # Test scenarios for validating skills
│   └── equity-analysis.md
└── README.md
```

### Adding a new skill

1. Create the skill folder: `mkdir -p my-skill`
2. Add `my-skill/SKILL.md` with instructions and references
3. Add a slash command: create `commands/my-skill.md` with frontmatter (`description`, `argument-hint`) that loads the SKILL.md
4. Install and test: `./scripts/manage-skills.sh add my-skill --to ~/my-project`

### Testing skills

1. Add skills to a test project: `./scripts/manage-skills.sh add --all --to ~/my-project`
2. Start a new Claude Code session in that project
3. Invoke via slash command (e.g., `/multi-agent-architecture`) or trigger naturally
4. Edit the skill files, start a new session, and re-test (symlinks pick up changes automatically)

### Contributing

1. Clone the repo and create a branch
2. Follow the "Adding a new skill" steps above
3. Test locally, then open a PR
