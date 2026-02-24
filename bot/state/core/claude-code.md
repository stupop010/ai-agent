## Using Claude Code

You have a `run_claude_code` tool that runs the Claude Code CLI. Use it as your primary tool for anything involving code, files outside your state directory, or research tasks.

### When to use it

- **Code changes**: Any modification to the bot's source code. Always branch, never edit main directly.
- **Obsidian vault**: Reading or updating Stuart's notes. The vault is a GitHub repo — clone it, edit, commit, push.
- **Research**: When Stuart asks you to look something up, investigate a codebase, or gather information. Claude Code has web search, file reading, and bash access.
- **Git operations**: Checking branches, creating PRs, reviewing diffs.

### How to prompt it

Give Claude Code clear, specific prompts. Don't be vague — tell it exactly what to do.

**Code changes:**
```
run_claude_code(prompt="In /repo, create a new branch from main called 'fix/scheduler-bug'. In bot/scheduler.py, fix <describe the bug>. Commit with a clear message and create a PR to main.")
```

**Obsidian read:**
```
run_claude_code(prompt="Clone https://github.com/{OBSIDIAN_REPO} to /tmp/obsidian (use GITHUB_TOKEN for auth). Read the file at Projects/MethodLine.md and return its contents.", cwd="/tmp")
```

**Obsidian write:**
```
run_claude_code(prompt="Clone https://github.com/{OBSIDIAN_REPO} to /tmp/obsidian (use GITHUB_TOKEN for auth). Create or update the file DailyNotes/2025-01-15.md with: <content>. Commit and push.", cwd="/tmp")
```

**Research:**
```
run_claude_code(prompt="Search the web for the latest pricing of Anthropic's Claude API. Summarise the key tiers and costs.")
```

### Rules

- For code changes, always create a branch and PR — never commit to main
- For Obsidian, commit and push directly (no PR needed)
- Keep prompts focused — one task per call
- If a task is complex, break it into multiple calls
- The tool has a 5 min timeout max — keep tasks scoped accordingly
