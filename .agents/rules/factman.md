## Factman

Factman embeds **structured semantic metadata** into source code as comments, giving AI agents (Claude Code, opencode, aider, Cursor, etc.) two-speed access: scan keys → read values → follow links → read code. No LSP, no embeddings, no external tooling required.

---

## Tag Schema (4 tags, always all 4)

```
<factman>
<fm-key>symbol_name_or_intent</fm-key>
<fm-value>What it does, why it exists, what it connects to. 1-3 sentences.</fm-value>
<fm-scope>file | module | class | function | section</fm-scope>
<fm-links>symbol1, symbol2, Module.method</fm-links>
</factman>
```

### Tag Rules

**`<fm-key>`** — Short, snake_case, unique, anchored to symbol name. The grep surface.
- Good: `normalize_invoice_totals`, `auth_token_refresh`
- Bad: `helper`, `utils`, `process`

**`<fm-value>`** — Full semantic description. Answer: what/why/preconditions/connections.
Include domain vocabulary. Write for a senior engineer who's never seen this codebase.

**`<fm-scope>`** — One of: `file` (whole file, goes first), `module` (package init),
`class` (class/struct), `function` (function/method/closure), `section` (logical block, use sparingly)

**`<fm-links>`** — Comma-separated symbols this unit calls/depends-on/is-called-by.
Use fully qualified names where ambiguous. Omit only if truly no cross-references.

---

## Comment Syntax by Language

| Language | Style |
|---|---|
| Python, Ruby, Shell, R, Elixir | `# <factman>` ... `# </factman>` |
| JS, TS, Java, C/C++, C#, Go, Rust, Swift, Kotlin | `// <factman>` ... `// </factman>` |
| HTML, XML, Markdown, Vue template | `<!-- <factman> -->` ... `<!-- </factman> -->` |
| SQL, Lua, Haskell | `-- <factman>` ... `-- </factman>` |
| CSS, SCSS | `/* <factman> */` ... `/* </factman> */` |
| MATLAB | `% <factman>` ... `% </factman>` |

Prefer `//` over `/* */` when both exist.

---

## Placement

| Scope | Position |
|---|---|
| `file` | First line of file (after copyright headers if any) |
| `module` | First line of `__init__.py`, `index.ts`, `mod.rs`, etc. |
| `class` | Immediately above class declaration |
| `function` | Immediately above function signature |
| `section` | Immediately above the section, inside containing function |

---

## What to Annotate

**Always:** Public API functions/methods · entry points (main, route handlers, CLI commands)
· classes/structs with domain roles · non-obvious utility functions >20 lines · every file ·
every module init

**Never:** Trivial getters/setters · self-explanatory one-liners · auto-generated code ·
simple test helpers <10 lines
