# ibby-plugins

Ibrahim's personal Claude Code plugin marketplace.

## Add the marketplace

Once, from any project:

```bash
claude
/plugin marketplace add ~/Developer/plugins
```

Then install whichever plugins you want:

```bash
/plugin install design-school@ibby-plugins
```

After editing a plugin, `/plugin marketplace update ibby-plugins` picks up the
change; components reload on the next session.

## Plugins

| Plugin | What it does |
|---|---|
| [design-school](./design-school) | Turns a design video into a verified, agent-readable lesson page in Notion — transcript via `yt-dlp`, rules extracted and adversarially verified by a 12-agent workflow, supporting frames via `ffmpeg`. |

## Adding a new plugin

1. Create the directory at the repo root:

   ```
   my-plugin/
   ├── .claude-plugin/
   │   └── plugin.json        # required: { "name": "my-plugin", ... }
   ├── commands/              # optional: slash commands (.md)
   ├── agents/                # optional: subagents (.md)
   ├── skills/                # optional: one dir per skill, each with SKILL.md
   ├── hooks/hooks.json       # optional
   └── README.md
   ```

2. Register it in `.claude-plugin/marketplace.json`:

   ```json
   { "name": "my-plugin", "source": "./my-plugin", "category": "productivity" }
   ```

3. `/plugin marketplace update ibby-plugins`, then
   `/plugin install my-plugin@ibby-plugins`.

### Rules worth remembering

- `plugin.json` **must** live in `.claude-plugin/`; every component directory
  (`commands/`, `skills/`, `agents/`, `hooks/`) must sit at the plugin root,
  **not** inside `.claude-plugin/`.
- A skill's invocable id is its **directory name**, not its frontmatter `name`.
  Keep them identical and kebab-case, and reference siblings as
  `plugin-name:skill-name`.
- Reference bundled files as `${CLAUDE_PLUGIN_ROOT}/...` — never hardcode an
  absolute path, and never a path relative to the working directory.
- Skills are chosen by their `description`. Write it in the third person and
  name the phrases a user would actually say.

`/plugin-dev` (from the bundled `claude-code-plugins` marketplace) has the full
reference if you need more than this.

## License

MIT
