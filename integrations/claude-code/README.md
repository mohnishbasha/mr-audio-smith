# mr-audio-smith for Claude Code

## Add the MCP server

    claude mcp add mr-audio-smith -- mr-audio-smith mcp --transport stdio

For a project-scoped setup that teammates share, add `--scope project` (writes `.mcp.json`).
To use a remote GPU box instead of local synthesis, run `mr-audio-smith serve` there and give
Claude Code the CLI's remote mode through the skill below (`run --server URL --token ...`).

## Add the skill

Copy `skill/SKILL.md` to `~/.claude/skills/narrate-page/SKILL.md` (personal) or
`.claude/skills/narrate-page/SKILL.md` (project). It teaches Claude Code when to call the tools,
the consent rule, how to review a script before rendering, and how to inject into a static site.

## Repository context

This repository's `CLAUDE.md` imports `AGENTS.md`, so Claude Code working on mr-audio-smith itself
picks up the commands, structure, and rules automatically.
