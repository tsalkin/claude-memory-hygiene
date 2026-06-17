# My AI Agent Started Forgetting — And That Was a Design Problem, Not a Bug

For months, my AI coding agent had been quietly taking notes. Every session it would jot down decisions, gotchas, and "remember this for next time" facts into a little second brain on disk. It was great — I'd ask it something three weeks later and it would already know the answer.

Then it started forgetting.

Not dramatically. Just... softly. It would re-ask a question it had clearly settled earlier. It would re-derive a fact it had already written down. The notes were still there — I could open the files myself and read them — but the agent acted like they didn't exist. The most unsettling part: nothing had crashed. No error. It was confidently working from a partial picture and didn't know it.

## The reveal

Here's the mechanism. Claude Code gives each project a file-based memory: a pile of small Markdown topic files plus one index file, `MEMORY.md`, that points at them. The harness loads that index into context **every single session** — the topic files get pulled in on demand, by relevance, but the index is always there. It's the table of contents the agent reads to know what it knows.

And an always-loaded file has a hard size budget. When `MEMORY.md` blew past it (a warning literally fires: *"index entries are too long"*), the harness did the only thing it could: it loaded **part** of the index and dropped the rest.

That's the whole bug. The agent went blind to a chunk of its own memory while every note still sat safely on disk. Silent knowledge loss — not because anything was deleted, but because the *pointer* to it fell off the edge of the always-loaded page.

Two things had bloated the index. First, every per-day "session state" note added a **permanent** line to it — a ledger that only ever grows. Second, the lines themselves had crept from one-line hooks into full paragraphs. A memory that only accumulates is on a countdown to this exact failure.

## The insight: storage is not memory

The thing I kept circling back to: **storage is not memory.**

Disk is storage. It's cheap, it's vast, it never needs to forget. But the always-loaded index isn't storage — it's *working memory*. It's the hot cache the agent reads on every turn, and like any cache it has a budget. Treating it as infinite is the mistake.

Put bluntly: a memory that never forgets isn't a feature. It's a leak. And a leak in working memory doesn't crash the program — it quietly blinds it.

Brains solved this a long time ago, and not by remembering everything. They solved it with **decay and tiers**: keep the hot stuff close, let the cold stuff fade out of the front of your mind. Crucially, "fade from working memory" is not the same as "destroy." The cold memory still exists — it's just not occupying the always-on channel.

That reframes the whole problem. I didn't need to delete knowledge. I needed to shrink the **index**, losslessly. Because the facts live in the topic files — `MEMORY.md` only points at them — there are three honest moves:

- **Shorten the hooks.** An index line is a one-line gist, not a summary. The detail stays in the file.
- **Archive the cold state notes.** Old per-day state files get *moved out of the index* — not deleted.
- **Pin the durable rules.** The hard-won lessons (the "always do X" / "never do Y" notes) never get touched.

Stop proliferating, keep the hot stuff, archive the cold, never delete.

## The resolution

So I wrote a tiny tool for exactly this one artifact: `claude-memory-hygiene`. One Python file, zero dependencies, stdlib only. It does three things.

```bash
# read-only: size vs budget, over-long lines, archivable count
python memory_hygiene.py report

# find index lines that have grown into paragraphs
python memory_hygiene.py lint --max-chars 220

# move OLD per-day state notes to archive/, drop their index lines
python memory_hygiene.py archive --keep 3          # dry-run first
python memory_hygiene.py archive --keep 3 --apply  # actually do it
```

Run it from inside any project and it finds that project's memory dir for you. `report` tells you how much headroom is left and how many stale state files could come out of the index. `lint` flags the lines that have ballooned. `archive` is the workhorse — and it's deliberately paranoid about not eating real memory:

- It only treats **volatile** files as candidates — session/daily/dated state notes. A `--pin` guard (durable `feedback_`/`reference_`/`user_` notes by default) is *never* archived, even if it somehow slips the filter.
- It **archives, never deletes.** Files move to `archive/` — still on disk, still greppable. The harness just stops auto-loading them, which is the entire point.
- It's **dry-run by default.** Nothing moves until you pass `--apply`.
- Dates come from the filename or mtime, so there's no "empty date → archive everything" footgun.

The result: the index drops back under budget, the agent can see all of its own pointers again, and not one fact was lost. Working memory got smaller; total knowledge stayed exactly the same.

## An honest credit

The "memory that forgets" philosophy isn't mine. It comes from the open-source projects **[agent-second-brain](https://github.com/smixs/agent-second-brain)** and **[autograph](https://github.com/smixs/autograph)** by GitHub user **[smixs](https://github.com/smixs)** (MIT) — the heavyweight version, with per-domain decay math, tiers, maps-of-content, and a knowledge graph. `claude-memory-hygiene` is an independent, much smaller tool inspired by that idea — *not* a fork. Where autograph is the full engine, this is the pragmatic ~200-line subset pointed at one artifact: the always-loaded index. Worth a look if this resonates:

- **agent-second-brain / autograph** by smixs — the decay-and-tiers philosophy
- **claude-memory-hygiene** — the tiny index-only tool (MIT, open-source)

**The takeaway:** an always-loaded index is working memory, and working memory needs a budget — give it one, or it will quietly blind the very agent it was built to help.
