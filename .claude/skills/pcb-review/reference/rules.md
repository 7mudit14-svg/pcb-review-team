# Review rules (every agent reads this first)

## 1. You review; you do not design
- **Read-only.** Never edit, save, move or delete design files, libraries, outputs or documents. Never call EDA tools that change a design (anything that places, routes, modifies, deletes, saves, runs an ECO or an autorouter). You write only inside the run directory you were given.
- **The designer owns the decisions.** Where a fix involves a real engineering choice (topology, part, pinout, trade-off), set `needs_designer_decision: true` and lay out the options with their trade-offs. Don't pick one for them.
- **House rules count.** The brief may list project house rules (schematic style, routing style, naming). Review against them like any other requirement.

## 2. Evidence or it didn't happen
- Every finding needs at least one `evidence` entry. It must be one of:
  - **datasheet**: a manufacturer PDF with page/section/table (`datasheets/X.pdf p.4 Table 2`).
  - **measurement**: a value read from the design (live EDA query or exported data) with the query or file it came from.
  - **calculation**: a `pcb_calc.py` command line and its result, or a shown formula.
  - **document**: a file + section/line (`4_Documentation/Approach.md §9`).
  - **standard**: a clause you are confident of (IPC-2221B Table 6-1, IPC-2152, IPC-7351, IPC-2223 ...).
- **Datasheet first.** Device facts (pin function, rating, threshold, package, land pattern, derating) come from the manufacturer datasheet, not from symbol text, distributor pages or memory. Check the project `datasheets/` folder first. If you fetch one online, cite the URL.
- If a datasheet is unavailable (NDA, obsolete), say so. Mark the item `UNKNOWN`, don't guess, and state the risk it leaves.
- Quote numbers with units and their source. Recompute critical numbers (impedance, current, spacing, skew, height stack) instead of trusting the design documents.
- A "finding" must be something specific and checkable at a location (designator, net, pin, layer, file, section). Generic advice belongs under `notes`, not under findings.

## 3. Severity
| Severity | Meaning | Examples |
|---|---|---|
| **CRITICAL** | The board will not work, can be damaged or is unsafe, or a hard requirement is violated. Blocks release. | wrong pinout, P/N swap through a connector, rating exceeded, missing ground return, board does not fit, USB2 lines connected when forbidden |
| **MAJOR** | Likely malfunction, significant reliability/yield risk, or a required deliverable is missing or wrong. Fix before release unless the designer waives it. | impedance far off target, unverified assumption on a critical interface, stale outputs, BOM/CPL mismatch, missing fab notes |
| **MINOR** | Quality, maintainability or documentation issue with low functional risk. | silkscreen overlap, inconsistent naming, missing test label |
| **INFO** | Observation, assumption to record, or suggestion. | future improvement, alternative part |

Severity reflects consequence × likelihood, *for this product's stated requirements*.

## 4. Confidentiality
- Files listed under `confidential` in the brief (e.g. a customer's problem statement or a vendor drawing) may be read locally, but **never** quote them into web searches, never send them to any external service, and never reproduce them at length in outputs. Paraphrase the requirement and cite the file + section.
- Web searches are for public part datasheets and standards only.

## 5. Output contract
Write exactly the file(s) the brief tells you to, as **valid JSON** (UTF-8, no comments, no trailing commas). Then write the short Markdown companion if asked. Keep the JSON under ~60 findings. Merge duplicates and drop trivia.

### Discipline engineer → `findings/<discipline>.json`
```json
{
  "discipline": "pcb",
  "role": "Senior PCB Design Engineer",
  "mode": "review",
  "summary": "2-4 sentences: overall state of this discipline.",
  "findings": [
    {
      "id": "PCB-001",
      "severity": "MAJOR",
      "title": "SSRX pair crosses the L2 split near J1",
      "location": "J1 pins 17-18, L1, x=12.4 y=10.1 mm",
      "requirement": "R2 / checklist PCB-07",
      "checklist_item": "PCB-07",
      "evidence": [
        {"type": "measurement", "source": "evidence/live/pcb_get_polygons.json", "detail": "L2 GND region gap 0.6 mm under segment ..."},
        {"type": "standard", "source": "Sierra HS guide §3.5.6.2", "detail": "traces over split planes break the return path"}
      ],
      "impact": "Return current detours, so expect a common-mode spike and eye closure.",
      "recommendation": "Options: (a) stitch the gap with a GND bridge, (b) reroute the pair 1 mm west. Trade-off: ...",
      "confidence": "high",
      "needs_designer_decision": false
    }
  ],
  "checked_ok": [{"item": "PCB-03 diff-pair skew", "evidence": "SSTX P/N 15.22/15.22 mm (live trace lengths)"}],
  "not_checked": [{"item": "PCB-11 crosstalk", "reason": "no field solver available"}],
  "auto_check_triage": [{"check": "GBR-MINTRACE", "disposition": "accepted", "note": "3.5 mil fan-out inside the WLP, at the fab minimum"}],
  "notes": "Optional free text."
}
```
- `id` prefix = the discipline key in capitals (`EMB`, `CIR`, `CMP`, `PWR`, `PCB`, `MEC`, `MFG`, `JPCB`, `TST`), numbered 001...
- `auto_check_triage` is only required from the engineer the brief assigns automatic-check triage to (manufacturing by default). Dispositions: `finding` (you raised it as a finding, so give the id in `note`), `false_positive`, `accepted`.

### Independent reviewer → `verdicts/<discipline>.json`
```json
{
  "discipline": "pcb",
  "reviewer": "independent",
  "verdicts": [
    {"finding_id": "PCB-001", "verdict": "CONFIRMED", "final_severity": "MAJOR",
     "rationale": "Re-measured: ...", "evidence": [{"type": "measurement", "source": "...", "detail": "..."}],
     "recommendation_check": "OK", "corrected_recommendation": ""}
  ],
  "added_findings": [ { "id": "PCB-R01", "severity": "MINOR", "title": "...", "location": "...", "evidence": [...], "recommendation": "...", "confidence": "medium", "needs_designer_decision": false } ],
  "coverage_gaps": ["Checklist items the engineer neither checked nor listed as not_checked"],
  "notes": ""
}
```
`recommendation_check` judges the proposed fix separately from the finding: `OK`, `WRONG` (the fix would cause a new problem; explain it and give `corrected_recommendation`) or `INCOMPLETE`. A correct finding with a harmful fix is common, so always check the fix against the design (shorts, clearances, mask/paste geometry, ratings).
Verdicts: `CONFIRMED` (evidence holds), `REFUTED` (evidence wrong or misread; say why), `DOWNGRADED` / `UPGRADED` (real, but wrong severity; give `final_severity`), `UNVERIFIED` (could not reproduce either way; say what data is missing).

### Interview mode → `interview/<discipline>.md`
6-10 questions an expert evaluator in your discipline would ask about this design. For each: the question, a strong answer grounded in the project documents (cite them), the follow-up they would push on, and any weak spot the designer should prepare or fix.
