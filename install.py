#!/usr/bin/env python3
"""Install the pcb-review team into a project (or your user profile) for Claude Code.

  python install.py --project PATH [--with-pdf] [--force]
  python install.py --user [--with-pdf] [--force]

Copies .claude/agents/hw-*.md and .claude/skills/pcb-review/ into
PATH/.claude/ (project scope) or ~/.claude/ (user scope). Project scope also
creates pcb-review.config.json from the example if none exists.

--with-pdf  creates a small virtual environment with pypdf inside the
            installed skill (skills/pcb-review/.venv) so large PDFs (standards,
            datasheets, requirement documents) can be turned into text for the
            reviewers, and records it as pdf_python in the project config.
--force     overwrite files that already exist.

Nothing else on the system is changed: no hooks, no settings.json edits.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import venv

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, ".claude")


def copy_tree(src, dst, force):
    copied, skipped = 0, 0
    for dp, dn, fns in os.walk(src):
        dn[:] = [d for d in dn if d not in ("__pycache__", ".venv")]
        rel = os.path.relpath(dp, src)
        os.makedirs(os.path.join(dst, rel), exist_ok=True)
        for fn in fns:
            s, d = os.path.join(dp, fn), os.path.join(dst, rel, fn)
            if os.path.exists(d) and not force:
                skipped += 1
                continue
            shutil.copy2(s, d)
            copied += 1
    return copied, skipped


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--project", help="project root to install into")
    g.add_argument("--user", action="store_true", help="install into ~/.claude for all projects")
    ap.add_argument("--with-pdf", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    root = os.path.abspath(a.project) if a.project else os.path.expanduser("~")
    target = os.path.join(root, ".claude")
    os.makedirs(os.path.join(target, "agents"), exist_ok=True)
    n_agents = 0
    for fn in sorted(os.listdir(os.path.join(SRC, "agents"))):
        if fn.startswith("hw-") and fn.endswith(".md"):
            d = os.path.join(target, "agents", fn)
            if not os.path.exists(d) or a.force:
                shutil.copy2(os.path.join(SRC, "agents", fn), d)
                n_agents += 1
    c, s = copy_tree(os.path.join(SRC, "skills", "pcb-review"), os.path.join(target, "skills", "pcb-review"), a.force)
    print(f"agents installed: {n_agents}; skill files copied: {c}, kept existing: {s}")
    print(f"-> {target}")

    pdf_python = ""
    if a.with_pdf:
        vdir = os.path.join(target, "skills", "pcb-review", ".venv")
        if not os.path.exists(vdir):
            venv.create(vdir, with_pip=True)
        py = os.path.join(vdir, "Scripts" if os.name == "nt" else "bin", "python.exe" if os.name == "nt" else "python")
        subprocess.check_call([py, "-m", "pip", "install", "--quiet", "pypdf>=4,<6"])
        pdf_python = py
        print(f"pypdf environment ready: {py}")

    if a.project:
        cfg = os.path.join(root, "pcb-review.config.json")
        if not os.path.exists(cfg):
            with open(os.path.join(SRC, "skills", "pcb-review", "reference", "config.example.json"), encoding="utf-8") as fh:
                data = json.load(fh)
            data["pdf_python"] = pdf_python
            with open(cfg, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            print(f"created {cfg}: edit it, or run /pcb-review setup")
        elif pdf_python:
            with open(cfg, encoding="utf-8") as fh:
                data = json.load(fh)
            data["pdf_python"] = pdf_python
            with open(cfg, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            print(f"updated pdf_python in {cfg}")
    print("Start a new Claude Code session in the project so the hw-* agents load, then run /pcb-review "
          "(or /pcb-review quick).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
