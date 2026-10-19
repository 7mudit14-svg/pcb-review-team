#!/usr/bin/env python3
"""merge_report.py - merge discipline findings and independent verdicts, apply the gate.

Deterministic on purpose: the release gate is computed by rules, not by a model.

Layout of a review run directory:
  findings/<discipline>.json     written by each discipline engineer
  verdicts/<discipline>.json     written by that discipline's independent reviewer
  evidence/auto_checks.json      written by pcb_checks.py (optional)
  waivers.json                   optional, written by the designer:
                                 [{"id": "PCB-003", "by": "name", "reason": "..."}]

Usage:
  python merge_report.py RUN_DIR [--validate-only]

Writes RUN_DIR/merged.json and RUN_DIR/summary.md and prints the gate.

Gate rules:
  BLOCKED                any CRITICAL finding that was not refuted or waived
  CONDITIONAL            otherwise, any MAJOR not refuted or waived, or any
                         automatic-check FAIL that no reviewer triaged
  READY_FOR_SIGNOFF      otherwise. A human still signs off; this tool never "approves".
"""
from __future__ import annotations

import glob
import json
import os
import sys

SEVERITIES = ["CRITICAL", "MAJOR", "MINOR", "INFO"]
VERDICTS = ["CONFIRMED", "REFUTED", "DOWNGRADED", "UPGRADED", "UNVERIFIED"]
REQUIRED_FINDING_KEYS = ["id", "severity", "title", "evidence", "recommendation"]


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def validate(run):
    problems = []
    findings, verdicts = {}, {}
    for p in sorted(glob.glob(os.path.join(run, "findings", "*.json"))):
        disc = os.path.splitext(os.path.basename(p))[0]
        try:
            d = load(p)
        except Exception as e:  # noqa: BLE001
            problems.append(f"{p}: not valid JSON ({e})")
            continue
        findings[disc] = d
        ids = set()
        for i, f in enumerate(d.get("findings", [])):
            for k in REQUIRED_FINDING_KEYS:
                if k not in f or f[k] in (None, "", []):
                    problems.append(f"{disc}: finding #{i} missing '{k}'")
            if f.get("severity") not in SEVERITIES:
                problems.append(f"{disc}: {f.get('id')} has severity {f.get('severity')!r}")
            if f.get("id") in ids:
                problems.append(f"{disc}: duplicate id {f.get('id')}")
            ids.add(f.get("id"))
    for p in sorted(glob.glob(os.path.join(run, "verdicts", "*.json"))):
        disc = os.path.splitext(os.path.basename(p))[0]
        try:
            d = load(p)
        except Exception as e:  # noqa: BLE001
            problems.append(f"{p}: not valid JSON ({e})")
            continue
        verdicts[disc] = d
        known = {f.get("id") for f in findings.get(disc, {}).get("findings", [])}
        for v in d.get("verdicts", []):
            if v.get("verdict") not in VERDICTS:
                problems.append(f"{disc}: verdict {v.get('verdict')!r} for {v.get('finding_id')}")
            if v.get("finding_id") not in known:
                problems.append(f"{disc}: verdict for unknown finding {v.get('finding_id')}")
            if v.get("verdict") in ("DOWNGRADED", "UPGRADED") and v.get("final_severity") not in SEVERITIES:
                problems.append(f"{disc}: {v.get('finding_id')} {v.get('verdict')} without a valid final_severity")
    return findings, verdicts, problems


def merge(run):
    findings, verdicts, problems = validate(run)
    waivers = {}
    wp = os.path.join(run, "waivers.json")
    if os.path.exists(wp):
        for w in load(wp):
            if w.get("id") and w.get("by") and w.get("reason"):
                waivers[w["id"]] = w
            else:
                problems.append(f"waivers.json: waiver needs id, by and reason: {w}")
    rows = []
    verified_any = bool(verdicts)
    for disc, d in findings.items():
        vmap = {v["finding_id"]: v for v in verdicts.get(disc, {}).get("verdicts", []) if "finding_id" in v}
        for f in d.get("findings", []):
            v = vmap.get(f.get("id"))
            sev = f.get("severity")
            if v is None:
                status = "UNREVIEWED" if verified_any else "SINGLE_CHECK"
            else:
                status = v["verdict"]
                if status in ("DOWNGRADED", "UPGRADED"):
                    sev = v.get("final_severity", sev)
            if f.get("id") in waivers:
                status = "WAIVED"
            rows.append({"discipline": disc, "role": d.get("role", disc), **f,
                         "original_severity": f.get("severity"), "final_severity": sev, "status": status,
                         "review_rationale": (v or {}).get("rationale", ""),
                         "recommendation_check": (v or {}).get("recommendation_check", ""),
                         "corrected_recommendation": (v or {}).get("corrected_recommendation", ""),
                         "waiver": waivers.get(f.get("id"))})
        for f in verdicts.get(disc, {}).get("added_findings", []):
            status = "WAIVED" if f.get("id") in waivers else "REVIEWER_ADDED"
            rows.append({"discipline": disc, "role": "Independent reviewer (" + disc + ")", **f,
                         "original_severity": f.get("severity"), "final_severity": f.get("severity"),
                         "status": status, "review_rationale": "Added by the independent reviewer (single check).",
                         "waiver": waivers.get(f.get("id"))})
    live = [r for r in rows if r["status"] not in ("REFUTED", "WAIVED")]
    crit = [r for r in live if r["final_severity"] == "CRITICAL"]
    major = [r for r in live if r["final_severity"] == "MAJOR"]

    auto_untriaged = []
    ap = os.path.join(run, "evidence", "auto_checks.json")
    if os.path.exists(ap):
        auto = load(ap)
        fails = [c["id"] + ":" + c["title"] for c in auto.get("checks", []) if c["status"] == "FAIL"]
        triaged = []
        for d in findings.values():
            for t in d.get("auto_check_triage", []):
                triaged.append(str(t.get("check", "")))
        # a triage entry may be "DRL-0", "DRL-0 FAIL" or "DRL-0 (file.csv)"; match on the check id prefix
        auto_untriaged = [f for f in fails
                          if not any(tr == f or tr.split()[0].split(":")[0] == f.split(":")[0] for tr in triaged if tr)]

    if crit:
        gate = "BLOCKED"
    elif major or auto_untriaged:
        gate = "CONDITIONAL"
    else:
        gate = "READY_FOR_SIGNOFF"
    order = {s: i for i, s in enumerate(SEVERITIES)}
    rows.sort(key=lambda r: (r["status"] in ("REFUTED", "WAIVED"), order.get(r["final_severity"], 9), r["discipline"]))
    score = {}
    for r in live:
        score.setdefault(r["discipline"], {s: 0 for s in SEVERITIES})[r["final_severity"]] += 1
    res = {"gate": gate, "problems": problems, "auto_checks_untriaged": auto_untriaged,
           "counts": {"total": len(rows), "live": len(live), "refuted": sum(r["status"] == "REFUTED" for r in rows),
                      "waived": sum(r["status"] == "WAIVED" for r in rows),
                      "critical": len(crit), "major": len(major)},
           "scorecard": score, "findings": rows,
           "decisions_needed": [r for r in live if r.get("needs_designer_decision")]}
    return res


def to_md(res):
    out = [f"## Gate: **{res['gate']}**", "",
           f"Live findings {res['counts']['live']} (CRITICAL {res['counts']['critical']}, MAJOR {res['counts']['major']}); "
           f"refuted {res['counts']['refuted']}; waived {res['counts']['waived']}.", ""]
    if res["auto_checks_untriaged"]:
        out += ["Automatic-check FAILs not triaged by any reviewer: " + "; ".join(res["auto_checks_untriaged"]), ""]
    out += ["### Scorecard (live findings)", "", "| Discipline | CRITICAL | MAJOR | MINOR | INFO |", "|---|---|---|---|---|"]
    for d, s in sorted(res["scorecard"].items()):
        out.append(f"| {d} | {s['CRITICAL']} | {s['MAJOR']} | {s['MINOR']} | {s['INFO']} |")
    out += ["", "### Findings", "", "| ID | Severity | Status | Discipline | Title | Location |", "|---|---|---|---|---|---|"]
    for r in res["findings"]:
        sev = r["final_severity"] + (f" (was {r['original_severity']})" if r["original_severity"] != r["final_severity"] else "")
        out.append(f"| {r.get('id')} | {sev} | {r['status']} | {r['discipline']} | "
                   f"{str(r.get('title', '')).replace('|', '/')} | {str(r.get('location', '')).replace('|', '/')} |")
    wrong = [r for r in res["findings"] if r.get("recommendation_check") in ("WRONG", "INCOMPLETE")]
    if wrong:
        out += ["", "### Fixes corrected by the independent reviewer", ""]
        out += [f"- **{r['id']}** ({r['recommendation_check']}): {r.get('corrected_recommendation') or r.get('review_rationale', '')[:300]}"
                for r in wrong]
    if res["decisions_needed"]:
        out += ["", "### Decisions needed from the designer", ""]
        out += [f"- **{r['id']}**: {r.get('title')}" for r in res["decisions_needed"]]
    if res["problems"]:
        out += ["", "### Input problems (fix and re-run)", ""] + [f"- {p}" for p in res["problems"]]
    return "\n".join(out) + "\n"


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    run = argv[0]
    if "--validate-only" in argv:
        _, _, problems = validate(run)
        print(json.dumps({"problems": problems}, indent=2))
        return 1 if problems else 0
    res = merge(run)
    with open(os.path.join(run, "merged.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=2)
    with open(os.path.join(run, "summary.md"), "w", encoding="utf-8") as fh:
        fh.write(to_md(res))
    print(json.dumps({"gate": res["gate"], "counts": res["counts"], "problems": len(res["problems"])}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
