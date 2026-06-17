# claude-memory-hygiene

**Keep a Claude Code agent's always-loaded `MEMORY.md` index under budget — without losing knowledge.**

A single-file, zero-dependency (Python stdlib only), MIT-licensed CLI. ~230 lines, no install step, runs from inside any project.

> **Storage is not memory.** An always-loaded index is *working memory* and needs a budget like any cache. A memory that never forgets isn't a feature — it's a leak that eventually blinds the agent.

---

## The problem

Claude Code gives every project a file-based "second memory" at `~/.claude/projects/<slug>/memory/`: many small `*.md` topic files plus one `MEMORY.md` index. The harness loads `MEMORY.md` into context **every session** (topic files are recalled on demand by relevance), so the index has a hard size budget (~24.4 KB — past it you get the *"index entries too long"* warning). Two failure modes accumulate forever: (a) per-session/per-day state files each add a *permanent* index line that never stops growing, and (b) index lines balloon from one-line hooks into paragraphs. Once `MEMORY.md` is over budget the harness loads only **part** of it — the agent goes blind to some of its own memory. The knowledge still exists on disk; it just stops being discoverable at recall time. Silent knowledge loss.

## The fix in one idea

**Index cleanliness ≠ deleting knowledge.** Facts live in the topic files; `MEMORY.md` only *points* at them. So the index can be shrunk **losslessly**: shorten the hooks (detail stays in the file), archive old state files (move, don't delete), pin durable memories, and stop proliferating per-day files. You shrink the pointer, not the page.

## Install

It's one stdlib script — clone and run, no dependencies:

```bash
git clone https://github.com/maxi-mts/claude-memory-hygiene.git
cd claude-memory-hygiene
python memory_hygiene.py report
```

Optional global alias (run from anywhere):

```bash
alias memhy='python /path/to/claude-memory-hygiene/memory_hygiene.py'
```

## Usage

By default the tool finds the **current project's** memory dir from your CWD — it applies Claude Code's own rule (memory lives at `~/.claude/projects/<slug>/memory`, where `<slug>` is the absolute project path with `/` replaced by `-`). So just `cd` into a project and run it.

| Command | What it does | Writes? |
|---|---|---|
| `report` *(default)* | Size vs budget, index-pointer count, over-long lines, archivable count | no (read-only) |
| `lint` | List index lines longer than `--max-chars`, worst first | no |
| `archive` | Move OLD volatile state files to `archive/` and drop their index lines | only with `--apply` |

**Key flags**

| Flag | Default | Meaning |
|---|---|---|
| `--project PATH` | CWD | Derive the memory dir from a project path |
| `--dir PATH` | — | Explicit memory dir (overrides `--project`/CWD) |
| `--keep N` | `3` | How many newest volatile files to keep in the index |
| `--max-chars N` | `220` | Index-line length limit for `report`/`lint` |
| `--volatile REGEX` | session/daily/dated notes | Filenames that are archival candidates |
| `--pin REGEX` | `^(feedback\|reference\|user)_` | Filenames NEVER archived (durable) |
| `--apply` | off | `archive`: actually move files (otherwise dry-run) |

**Examples**

```bash
# CWD auto-detect — operate on the current project's memory:
python memory_hygiene.py report
python memory_hygiene.py lint --max-chars 220

# see what archive WOULD do (dry-run is the default), then commit:
python memory_hygiene.py archive --keep 3
python memory_hygiene.py archive --keep 3 --apply

# any project / an explicit memory dir:
python memory_hygiene.py report --project /path/to/some/repo
python memory_hygiene.py report --dir ~/.claude/projects/<slug>/memory
```

## How it decides what to archive

- **Volatile vs durable.** A file is an archival *candidate* only if its name matches `--volatile` (default: `session_state` / `session_log` / `daily_*` / any `YYYY-MM-DD` dated note). Everything else is left alone.
- **Pin guard.** A second filter, `--pin` (default: `feedback_` / `reference_` / `user_` prefixes), excludes durable notes even if they slipped past the volatile pattern. Pinned never moves.
- **Keep N newest.** Candidates are sorted newest-first (by date-in-filename, then mtime); the newest `--keep` stay in the index, only the rest are archived.
- **Archive, not delete.** Files move to `archive/` — still on disk, still greppable. The harness only auto-loads `MEMORY.md`, so archived files simply leave the always-loaded index; their matching index lines are dropped.
- **Dates from filename/mtime.** No frontmatter stamping required — so there's no *"empty date → archive everything"* footgun.

## Safety

- **Dry-run by default.** `archive` only previews; nothing moves until you add `--apply`.
- **Never deletes.** Worst case is a `shutil.move` into `archive/` in the same memory dir.
- **Durable memory is protected twice** — by the `--volatile` candidate filter and the `--pin` guard.
- **`report` and `lint` are read-only** — they never touch a file.

## Why

The index is the one artifact loaded into context **every single session**, so it behaves like a cache, not an archive — and a cache without an eviction policy eventually evicts itself by overflowing. This tool gives that always-loaded index a budget and a lossless way back under it, so the agent keeps seeing all of its memory instead of a silently truncated slice.

## Credit

The "memory that forgets" decay/tier philosophy comes from **[agent-second-brain](https://github.com/smixs/agent-second-brain)** and **[autograph](https://github.com/smixs/autograph)** by [smixs](https://github.com/smixs) (MIT). `claude-memory-hygiene` is an **independent, much smaller tool inspired by that philosophy — not a fork.** `autograph` is the heavyweight (per-domain decay math, tiers, MOC, knowledge graph); this is the pragmatic ~200-line subset aimed at exactly one artifact: the always-loaded `MEMORY.md` index.

## License

MIT.
