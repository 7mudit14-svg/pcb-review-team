# Checklist: Manufacturing Engineer (key `manufacturing`, id prefix `MFG`)

Scope: DFM (fabrication), DFA (assembly), fab and assembly documentation, release package completeness, IPC classes. **This role triages every FAIL and WARN in `evidence/auto_checks.json`** (put each in `auto_check_triage`). References: fab profile in the brief; IPC-6012 / IPC-A-600 (bare board), IPC-A-610 / J-STD-001 (assembly), IPC-7351 (land patterns), IPC-D-356 / IPC-2581 (data), Sierra Circuits HS guide §8.1 (fab drawing and release checklist).

| ID | Check | How to verify | If it fails |
|---|---|---|---|
| MFG-01 | Every automatic-check FAIL/WARN is triaged: real finding, false positive, or accepted with a reason | `evidence/auto_checks.md` | MAJOR if a real FAIL is left untriaged |
| MFG-02 | Feature sizes vs fab profile: min track/space, min drill, annular ring, via pad, copper-to-edge, mask dam, silk line/text | Auto checks + live rules + DRC | MAJOR (CRITICAL if not manufacturable) |
| MFG-03 | Fab notes complete: material/Tg, thickness and tolerance, copper weights, finish, mask/silk colours, IPC class, impedance control (target, tolerance, layers, nets, coupon), via tenting/filling, electrical test | Fab drawing / README / order notes | MAJOR |
| MFG-04 | Fabrication drawing: outline with dimensions, drill table with symbols and tolerances (PTH vs NPTH), stack-up table, notes (Sierra §8.1 items 9, 13-15, 27) | Fab drawing PDF | MAJOR |
| MFG-05 | Gerber set complete and consistent: all copper, mask, paste, silk, outline layers; outline on its own layer; format and units consistent; drill file(s) with plating identified | Auto checks GBR-*, DRL-* | MAJOR |
| MFG-06 | Outputs are current: generated after the last CAD save, and the package's CAD copy equals the master | Auto checks `FRESH-1`, `FRESH-2` | MAJOR |
| MFG-07 | Assembly data: BOM ↔ CPL ↔ design designators agree; DNP parts excluded from CPL or marked; rotation and origin conventions stated; side stated | Auto checks BOM-*, CPL-*, XCHK-* | MAJOR |
| MFG-08 | Assembler BOM (e.g. JLC format) has supplier part numbers for every placed line, or the lines are marked as consigned/hand-placed | Auto check `BOM-1` on the assembler BOM | MAJOR |
| MFG-09 | Fiducials: at least 3 global (Sierra §8.1 9.b.vi), plus local fiducials for fine-pitch parts if the assembler asks; mask opening per spec | Live components / Gerbers | MINOR-MAJOR (fine-pitch parts present → MAJOR) |
| MFG-10 | Paste and mask: every SMD pad has mask + paste openings; fine-pitch paste reductions; exposed-pad paste windowing (Sierra §8.1 item 10-12) | Paste/mask Gerbers | MAJOR |
| MFG-11 | Assembly drawing: title block, revision, designators, polarity/pin-1 marks, DNP list, notes (IPC class, reflow, ESD, special handling such as connectors that must not see flux) | Assembly drawing PDF | MAJOR |
| MFG-12 | Silkscreen: legible size, not on pads, polarity and pin-1 marks, connector function labels, board name/revision/date, HV warning where applicable (Sierra §8.1 items 4-8) | Silk Gerber / renders | MINOR |
| MFG-13 | Single-sided vs double-sided assembly is intentional; heavy or tall parts on the top side; reflow profile constraints of connectors noted | CPL layers + datasheets | MINOR |
| MFG-14 | Panelization / rails / tooling holes if needed for the assembler's minimum size; break-off method keeps edge connectors safe | Board size vs assembler minimum | MINOR-MAJOR |
| MFG-15 | Testability for production (electrical test netlist IPC-D-356, test pads reachable) | Package + test role | MINOR |
| MFG-16 | Non-board items (cables, flexes, hardware) specified so the full assembly can be built | Non-board BOM | MAJOR if a required custom part is unspecified |
