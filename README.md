# ibby-plugins

Ibrahim's personal plugin marketplace for Claude Code and Cursor.

## Add the marketplace

### Cursor Team Marketplace

Import this repository as a Cursor Team Marketplace:

1. Go to **Dashboard → Plugins → Import from Repo**
2. Enter the repository URL or local path
3. Install plugins from the team marketplace:
   - `printful-automation` — Agent Plugins v1.0.0 format, portable across clients
   - `design-school` — Claude Code legacy format

### Claude Code

Once, from any project:

```bash
claude
/plugin marketplace add ~/Developer/plugins
```

Then install whichever plugins you want:

```bash
/plugin install design-school@ibby-plugins
/plugin install printful-automation@ibby-plugins
```

After editing a plugin, `/plugin marketplace update ibby-plugins` picks up the
change; components reload on the next session.

## Plugins

| Plugin | What it does |
|---|---|
| [design-school](./design-school) | Turns a design video into a verified, agent-readable lesson page in Notion — transcript via `yt-dlp`, rules extracted and adversarially verified by a 12-agent workflow, supporting frames via `ffmpeg`. |
| [printful-automation](./printful-automation) | Runs a Printful print-on-demand store through its REST API: catalog, mockups, products, design files, orders and reports. Follows the [Agent Plugins](https://agent-plugins.org/specification) v1.0.0 standard. |

## Adding a new plugin

New plugins follow the [Agent Plugins v1.0.0](https://agent-plugins.org/specification)
standard so that clients other than Claude Code can load them too.
`printful-automation` is the reference. (`design-school` still uses the older
Claude Code-only layout shown under *Legacy layout* below.)

1. Create the directory at the repo root:

   ```
   my-plugin/
   ├── plugin.json            # required, at the plugin root (see below)
   ├── skills/                # optional: one dir per skill, each with SKILL.md
   ├── mcp.json               # optional: MCP servers, Agent Plugins format
   └── README.md
   ```

   `plugin.json`:

   ```json
   {
     "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
     "name": "my-plugin",
     "version": "0.1.0",
     "description": "..."
   }
   ```

2. Register it in `.claude-plugin/marketplace.json` and include `description`,
   `version`, `author` and `keywords`. Claude Code reads these from the
   marketplace entry because the plugin has no `.claude-plugin/plugin.json`.

3. `/plugin marketplace update ibby-plugins`, then
   `/plugin install my-plugin@ibby-plugins`.

### Agent Plugins rules worth remembering

- The manifest schema is **closed**. Only `$schema`, `name`, `version`,
  `description`, `author`, `homepage`, `repository`, `license`, `keywords` and
  `extensions` are allowed. Never put `commands`, `hooks`, `agents` or
  `mcpServers` in it.
- Components are found only in fixed locations: `skills/<name>/SKILL.md`
  (one level deep, no nesting) and root `mcp.json`.
- Skill frontmatter follows [agentskills.io](https://agentskills.io/specification):
  `name` must match the directory name (lowercase, hyphens, max 64 chars) and
  `description` must be 1024 characters or fewer. `metadata` values must be
  strings.
- Reference bundled files by paths relative to the skill directory
  (`scripts/x.sh`, `../other-skill/scripts/x.sh`), not `${CLAUDE_PLUGIN_ROOT}`.
  Every path must stay inside the plugin root.
- Client-specific files (hooks, agents, commands) are not portable. They go in a
  reverse-domain directory owned and documented by that client, or they stay
  in a legacy-layout plugin.

### Legacy layout (Claude Code only)

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

### Legacy layout rules

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
