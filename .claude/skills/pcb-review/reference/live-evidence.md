# Collecting live EDA evidence (Hardware Lead only)

The Lead collects one read-only snapshot before any reviewer starts, so every agent works from the same data and the EDA bridge is not hit by many agents at once. Save each result as JSON under `<run>/evidence/live/<tool_name>.json`. If a call fails or times out, write `{"error": "..."}` to that file, note it in the brief and move on. **Never retry a hanging call.**

## Altium Designer via eda-agent (`eda: "altium-eda-agent"`)
**Preferred:** `python -I SKILL_DIR/scripts/eda_snapshot.py --out RUN/evidence/live --mcp-json .mcp.json --server eda-agent`. It calls the read-only tools below, refuses anything off its allowlist, and writes each result to disk. The table below is what it runs. Use the manual route only if the script can't start the server.

**Manual fallback:** load the tools with ToolSearch (`select:mcp__eda-agent__<name>,...`) in one call, then run them in this order:

| Order | Tool | Why |
|---|---|---|
| 1 | `app_ping` | Bridge alive, versions. If this fails, skip the live snapshot and say so in the brief. |
| 2 | `app_get_active_document`, `app_list_documents` | Confirm the open PcbDoc is the one in the config (compare paths). Record the `modified` flag. Unsaved edits mean the snapshot may not match the files on disk. |
| 3 | `proj_get_stats`, `proj_get_compile_freshness` | Project size; stale compile warning. |
| 4 | `proj_get_differences` | Schematic ↔ PCB sync. |
| 5 | `proj_get_erc_violations` | ERC (stored). |
| 6 | `pcb_get_components` | Designator, footprint, X/Y, rotation, layer. |
| 7 | `pcb_get_board_outline` | Outline, cut-outs. |
| 8 | `pcb_get_layer_stackup` | Layers, dielectric heights, Dk. |
| 9 | `pcb_get_design_rules`, `pcb_get_diff_pair_rules` | Rule set as implemented. |
| 10 | `pcb_get_net_classes` (members=false), `pcb_get_differential_pairs` | Classes, pair objects and P/N skew. **Zero pair objects is itself a finding.** |
| 11 | `pcb_get_trace_lengths` | Per-net routed length. |
| 12 | `pcb_get_vias`, `pcb_get_polygons`, `pcb_get_unrouted_nets` | Vias, pours, completeness. |
| 13 | `proj_get_nets` or `list_nets` | Net list. |
| 14 | `proj_get_bom` | BOM as the project sees it. |

Optional, only if time allows:
- `pcb_render_svg` per copper layer (layer names are `TopLayer`, `MidLayer1`, `MidLayer2`, `BottomLayer`, `TopOverlay`). Convert the SVGs to PNG with a headless browser if one is installed, so reviewers can look at them.
- `obj_query` for specific objects a reviewer asks about.

**Do not call** `pcb_run_drc` (modal dialog), `pcb_autoroute`, `pcb_layout_audit` (known to hang the bridge), or anything that modifies, saves, syncs or runs an ECO. For DRC, use the newest DRC report file (HTML) in the package or `Project Outputs`, and compare its time with the PcbDoc's save time (pcb_checks `FRESH-1`).

## KiCad (`eda: "kicad"`)
Use `kicad-cli` if installed: `kicad-cli pcb drc --format json`, `kicad-cli sch erc`, `kicad-cli pcb export pos`, `kicad-cli sch export netlist`. Write the outputs to `evidence/live/`. The `.kicad_pcb` and `.kicad_sch` files are text, so reviewers can also read them directly.

## No EDA access (`eda: "none"`)
Rely on the package (Gerbers, BOM, CPL, PDFs, reports) and the automatic checks. Every reviewer must list what it could not verify without the CAD data.
