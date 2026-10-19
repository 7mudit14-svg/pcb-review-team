# Checklist: Power Engineer (key `power`, id prefix `PWR`)

Scope: power tree, budget, distribution (connectors, copper, vias, planes), decoupling, switching converters, protection. References: IPC-2152 / IPC-2221 (conductor current), Sierra Circuits High-Speed PCB Design Guide ch. 6 (PDN), TI SZZA009 §2.1-2.2 (grounds, bypassing, ferrite beads).

| ID | Check | How to verify | If it fails |
|---|---|---|---|
| PWR-01 | Power budget per rail: typical and worst-case current for every load, with sources (datasheet or requirement) and margin | Build the table; cite datasheets | MAJOR |
| PWR-02 | Connector power contacts: count × derated rating ≥ worst-case current, for supply **and** return | `pcb_calc.py contacts`, connector datasheet derating note | CRITICAL if under-rated |
| PWR-03 | Copper capacity: every power path (traces, necks at pads, bars between pins, planes) carries the current at an acceptable temperature rise | `pcb_calc.py trace-current` per narrowest segment (live track widths) | MAJOR |
| PWR-04 | Via capacity: enough vias per layer transition for the current (≈ 0.5-1 A per 0.3 mm via, depending on plating) | Count vias on the power nets (live `pcb_get_vias`) | MAJOR |
| PWR-05 | IR drop from input connector to the load pins is acceptable for the load's input tolerance | Estimate R of contacts + copper | MAJOR |
| PWR-06 | Decoupling: each IC supply pin has the datasheet-recommended capacitance, placed close with a short via path to ground; bulk capacitance at the board input | Datasheet + placement | MAJOR |
| PWR-07 | Switching converter (boost/buck/charge pump): hot loop minimal, input and output caps close, switch node small and away from sensitive nets, components rated for peak current and voltage | Datasheet layout guidance + live placement | MAJOR |
| PWR-08 | Noise isolation between noisy and sensitive loads (ferrite bead / RC / separate pour), and the bead's DC current and DCR are acceptable | Bead datasheet impedance vs current curve | MINOR-MAJOR |
| PWR-09 | Inrush / hot-plug behaviour: input capacitance vs upstream limits (e.g. USB VBUS limits), soft-start, eFuse/load switch if the host needs control | Spec + datasheets | MAJOR if the upstream limit is exceeded |
| PWR-10 | Protection: overcurrent, short-circuit and reverse polarity where cables can be miswired, or a justified waiver | Schematic + docs | MAJOR for user-pluggable inputs |
| PWR-11 | Ground system: continuous return under power and signal paths, mounting holes and chassis connection intentional, no unintended ground loops through cables | Planes + docs | MAJOR |
| PWR-12 | Planes: power plane pulled back from the board edge, no isolated islands, thermal relief settings OK for assembly | Live polygons/rules | MINOR-MAJOR |
| PWR-13 | High-voltage rails generated on board (boost outputs, lens/LED drivers) are clearly classed and their worst-case voltage is stated | Datasheet / reference | MAJOR |
| PWR-14 | Thermal: the hottest parts (regulators, drivers, high-current connectors) stay inside ratings at the worst ambient | Datasheet θJA, power dissipation estimate | MAJOR |
