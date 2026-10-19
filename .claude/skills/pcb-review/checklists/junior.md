# Checklist: Junior PCB Engineer (key `junior`, id prefix `JPCB`)

Scope: the careful, line-by-line verification work: footprints and library parts against datasheets, and consistency between every document in the package. This role does not judge architecture; it proves that what the documents say is what the design contains.

| ID | Check | How to verify | If it fails |
|---|---|---|---|
| JPCB-01 | Each footprint's pad size, pitch, row spacing and pad count match the manufacturer's recommended land pattern (IPC-7351 if none given) | Datasheet drawing vs footprint pad data (live `pcb_get_component_pads` / library) | CRITICAL for a wrong pitch/count; MAJOR for out-of-tolerance pads |
| JPCB-02 | Pin-1 / polarity / pad numbering in each footprint matches the datasheet and the symbol (incl. mounting pads, odd/even rows, mirrored numbering) | Datasheet vs footprint vs symbol | CRITICAL |
| JPCB-03 | Courtyard, silkscreen and assembly outlines are drawn and do not overlap pads; component heights set (needed for 3D/height checks) | Library / 3D | MINOR-MAJOR |
| JPCB-04 | Each part's 3D model matches its datasheet body and height | STEP / 3D | MAJOR if heights are unproven |
| JPCB-05 | Footprints for parts without public drawings (NDA or obsolete) are flagged with their source and the risk | Library notes | MAJOR |
| JPCB-06 | Designators unique and consistent across schematic, PCB, BOM, CPL and assembly drawing | Auto checks + documents | MAJOR |
| JPCB-07 | Every number in the documents matches the design (trace widths, gaps, stack-up values, lengths, pin assignments, part numbers, counts of vias/holes, board size) | Compare docs (approach, README, CSVs) with live data / auto checks; list each mismatch | MAJOR (CRITICAL if a doc would make the fab or assembler do the wrong thing) |
| JPCB-08 | Requirement and decision IDs referenced in documents exist and say what is claimed; no stale references to removed parts or old designators | Docs cross-reference | MINOR-MAJOR |
| JPCB-09 | Schematic PDF, PCB images and drawings show the same revision as the CAD files (title blocks, dates, revision letters consistent) | PDFs vs CAD | MINOR-MAJOR |
| JPCB-10 | BOM columns complete and consistent (value, rating, package, MPN, supplier PN, populate flag); quantities equal designator counts | Auto checks BOM-* + manual | MAJOR |
| JPCB-11 | Package README / index lists every file actually present and nothing missing | Inventory (`INV-1`) vs README | MINOR |
| JPCB-12 | Spelling/units/notation consistent (mm vs mil, Ω, µF), no placeholder text (TBD, XXX, ???) left | Grep documents | MINOR |
