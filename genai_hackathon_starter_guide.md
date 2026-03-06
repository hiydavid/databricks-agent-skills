# Steps to use this Agent Skill as part of Hackathon

Note: this assumes you are using local IDE for development

1. Go to [Agent on Apps starter guide](https://docs.databricks.com/aws/en/generative-ai/agent-framework/author-agent) and complete step #1 where you clone the app repo into your local development environment. Make sure you have databricks CLI setup already. After cloning, your app repo should look something like [this](https://github.com/databricks/app-templates/tree/main/agent-openai-agents-sdk) (depending on which template you choose).

2. You will also see some [preloaded Agent Skills](https://github.com/databricks/app-templates/tree/main/agent-openai-agents-sdk/.claude/skills). At this point, copy the Agent Skills in this repo (i.e. `multi-agent-architecture`, `improve-genie-sapce`, and `parse-documents`) into that `skills` directory. Furthermore, feel free to install additional useful Agent Skills from the [Databricks AI Dev Kit repo](https://github.com/databricks-solutions/ai-dev-kit/tree/main/databricks-skills).

3. Start your Coding Agent (e.g. Claude Code, Codex, Cursor, or Genie Code on Databricks), and start with the `multi-agent-architecture` skill.

