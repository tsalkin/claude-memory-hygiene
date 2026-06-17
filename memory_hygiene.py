#!/usr/bin/env python3
"""memory_hygiene.py — keep a Claude Code agent's file-based memory index under
budget WITHOUT losing knowledge. Project-agnostic, zero dependencies (stdlib only).

THE PROBLEM
-----------
Claude Code keeps a file-based "second memory" per project at
``~/.claude/projects/<slug>/memory/`` — many small ``*.md`` topic files plus one
``MEMORY.md`` index. The harness loads ``MEMORY.md`` into context EVERY session,
so it has a hard size budget (~24.4 KB). Two things blow that budget over time:

  (a) per-session/per-day state files (``project_session_state_2025-06-17.md`` …)
      each add a *permanent* line to the index — they accumulate forever;
  (b) index lines grow too long (the hook should be one line, not a paragraph).

When the index exceeds budget the harness loads only PART of it — the agent goes
blind to some of its own memory. The knowledge still exists on disk; it just
stops being discoverable at recall time.

THE FIX (this tool)
-------------------
Cleanliness of the INDEX is not the same as deleting knowledge. The facts live in
the topic files; ``MEMORY.md`` only points at them. So we can shrink the index
losslessly:

  report   size vs budget, over-long lines, archivable state files   (read-only; default)
  lint     list index lines over the char limit (shorten the hook, keep the file)
  archive  move OLD volatile state files to ``archive/`` + drop their index lines
           (dry-run by default; pass --apply). NEVER touches durable memory.

Safety model (vs a naive decay engine):
  * Only files matching ``--volatile`` (default: session/daily/dated state notes)
    are archival candidates. Durable notes (feedback/reference/user/goals) are
    never candidates.
  * A second guard ``--pin`` excludes anything matching it even if it slipped the
    volatile filter (default pins ``feedback_``/``reference_``/``user_`` prefixes).
  * Archive, never delete — files move to ``archive/`` (still on disk, still
    greppable). The harness only auto-loads ``MEMORY.md``, so archived files just
    leave the always-loaded index.
  * Dates come from the filename / mtime — no frontmatter stamping required, so
    there is no "empty date -> archive everything" footgun.

USAGE
-----
  # operates on the CURRENT project's memory by default (derived from CWD):
  python memory_hygiene.py report
  python memory_hygiene.py lint --max-chars 220
  python memory_hygiene.py archive --keep 3            # dry-run
  python memory_hygiene.py archive --keep 3 --apply

  # any project / explicit dir:
  python memory_hygiene.py report --project /path/to/some/repo
  python memory_hygiene.py report --dir ~/.claude/projects/<slug>/memory

Make it global (run from anywhere):
  alias memhy='python /path/to/claude-memory-hygiene/memory_hygiene.py'

License: MIT.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

BUDGET = 24_400          # harness hard budget for MEMORY.md, in bytes
MAX_LINE = 220           # recommended max length of a single index line, in chars
DEFAULT_VOLATILE = r"(?i)session[_-]?state|session[_-]?log|^daily[_-]|\d{4}-\d{2}-\d{2}"
DEFAULT_PIN = r"^(feedback|reference|user)_"
LINK_RE = re.compile(r"\]\(([^)]+\.md)\)")
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


# ── memory-dir resolution ─────────────────────────────────────────────────────

def slug_for(project_path: Path) -> str:
    """Claude Code names a project's memory dir by its absolute path with '/'→'-'."""
    return str(project_path.resolve()).replace("/", "-")


def memory_dir_for(project_path: Path) -> Path:
    return Path.home() / ".claude" / "projects" / slug_for(project_path) / "memory"


def resolve_dir(args) -> Path:
    if args.dir:
        return args.dir
    if args.project:
        return memory_dir_for(args.project)
    return memory_dir_for(Path.cwd())


# ── helpers ───────────────────────────────────────────────────────────────────

def index_file(d: Path) -> Path:
    return d / "MEMORY.md"


def index_lines(d: Path) -> list[str]:
    return index_file(d).read_text(encoding="utf-8").splitlines()


def volatile_files(d: Path, volatile_re: re.Pattern, pin_re: re.Pattern) -> list[Path]:
    """Archival candidates, newest first (by date-in-name then mtime).

    A file is a candidate iff its NAME matches `volatile_re` and does NOT match
    `pin_re`. MEMORY.md and anything under archive/ are excluded.
    """
    out = []
    for p in d.glob("*.md"):
        if p.name == "MEMORY.md":
            continue
        if pin_re.search(p.name):
            continue
        if volatile_re.search(p.name):
            out.append(p)

    def key(p: Path):
        m = DATE_RE.search(p.name)
        return (m.group(1) if m else "0000-00-00", p.stat().st_mtime)

    return sorted(out, key=key, reverse=True)


# ── commands ──────────────────────────────────────────────────────────────────

def cmd_report(d: Path, args, vol_re, pin_re) -> int:
    size = index_file(d).stat().st_size
    lines = index_lines(d)
    pointers = [ln for ln in lines if ln.lstrip().startswith("- [")]
    longs = [ln for ln in pointers if len(ln) > args.max_chars]
    vol = volatile_files(d, vol_re, pin_re)
    archivable = max(0, len(vol) - args.keep)
    over = size > BUDGET
    status = (f"🔴 OVER budget by {size - BUDGET}" if over
              else f"🟢 under budget, {BUDGET - size} bytes headroom")
    print(f"memory dir: {d}")
    print(f"MEMORY.md:  {size} bytes / budget {BUDGET}  ({status})")
    print(f"index pointers:        {len(pointers)}")
    print(f"lines over {args.max_chars} chars:   {len(longs)}   (run `lint` to find them)")
    print(f"volatile state files:  {len(vol)}   keep={args.keep}   archivable={archivable}")
    if archivable:
        print(f"  → `archive --keep {args.keep} --apply` moves {archivable} old file(s) out of the index")
    arch = d / "archive"
    if arch.is_dir():
        print(f"already archived:      {len(list(arch.glob('*.md')))} file(s) in archive/ (off-index, knowledge intact)")
    return 1 if over else 0


def cmd_lint(d: Path, args, vol_re, pin_re) -> int:
    longs = sorted(
        ((len(ln), ln) for ln in index_lines(d)
         if ln.lstrip().startswith("- [") and len(ln) > args.max_chars),
        reverse=True,
    )
    if not longs:
        print(f"🟢 no index line exceeds {args.max_chars} chars.")
        return 0
    print(f"{len(longs)} index line(s) over {args.max_chars} chars — shorten the hook to its gist "
          f"(detail stays inside the file, not the index):\n")
    for n, ln in longs:
        m = LINK_RE.search(ln)
        print(f"  {n:>4} chars  {Path(m.group(1)).name if m else '?'}")
    return 0


def cmd_archive(d: Path, args, vol_re, pin_re) -> int:
    vol = volatile_files(d, vol_re, pin_re)
    to_archive = vol[args.keep:]
    if not to_archive:
        print(f"🟢 nothing to archive (volatile files: {len(vol)} ≤ keep {args.keep}).")
        return 0
    archived_names = {p.name for p in to_archive}
    lines = index_lines(d)
    drop = [ln for ln in lines
            if (m := LINK_RE.search(ln)) and Path(m.group(1)).name in archived_names]

    mode = "APPLYING" if args.apply else "DRY-RUN (pass --apply to execute)"
    print(f"[{mode}] move {len(to_archive)} volatile file(s) to archive/ (keep {args.keep} newest):")
    for p in to_archive:
        print(f"  → archive/{p.name}")
    print(f"index lines to drop: {len(drop)}")

    if not args.apply:
        print("\n(dry-run — nothing changed)")
        return 0

    (d / "archive").mkdir(exist_ok=True)
    for p in to_archive:
        shutil.move(str(p), str(d / "archive" / p.name))
    kept = [ln for ln in lines
            if not ((m := LINK_RE.search(ln)) and Path(m.group(1)).name in archived_names)]
    index_file(d).write_text("\n".join(kept) + "\n", encoding="utf-8")
    new_size = index_file(d).stat().st_size
    print(f"\n✅ archived {len(to_archive)} file(s), dropped {len(drop)} index line(s). "
          f"MEMORY.md now {new_size} bytes "
          f"({'🟢 under' if new_size <= BUDGET else '🔴 over'} budget {BUDGET}).")
    print("Knowledge intact: files are in archive/ (still on disk & greppable).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Keep a Claude Code agent's MEMORY.md index under budget without losing knowledge.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("command", nargs="?", default="report", choices=["report", "lint", "archive"],
                    help="report (default) | lint | archive")
    ap.add_argument("--project", type=Path, help="project path; memory dir derived from it (default: CWD)")
    ap.add_argument("--dir", type=Path, help="explicit memory dir (overrides --project/CWD)")
    ap.add_argument("--keep", type=int, default=3, help="how many newest volatile files to keep in the index (default 3)")
    ap.add_argument("--max-chars", type=int, default=MAX_LINE, help=f"index line length limit (default {MAX_LINE})")
    ap.add_argument("--volatile", default=DEFAULT_VOLATILE, help="regex: filenames that are archival candidates")
    ap.add_argument("--pin", default=DEFAULT_PIN, help="regex: filenames that are NEVER archived (durable)")
    ap.add_argument("--apply", action="store_true", help="archive: actually move files (otherwise dry-run)")
    args = ap.parse_args()

    d = resolve_dir(args)
    if not index_file(d).exists():
        print(f"ERROR: no MEMORY.md at {d}\n"
              f"  Run from inside a project that has Claude Code memory, or pass --project/--dir.",
              file=sys.stderr)
        return 2

    vol_re = re.compile(args.volatile)
    pin_re = re.compile(args.pin)
    return {"report": cmd_report, "lint": cmd_lint, "archive": cmd_archive}[args.command](d, args, vol_re, pin_re)


if __name__ == "__main__":
    sys.exit(main())
