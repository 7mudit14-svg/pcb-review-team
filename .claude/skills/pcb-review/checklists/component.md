# Checklist: Component Engineer (key `component`, id prefix `CMP`)

Scope: part selection, ratings and derating, lifecycle, availability, second sources, BOM content. Footprint geometry belongs to the junior PCB engineer (JPCB-01..05); this role checks that the *selected part* fits the application.

| ID | Check | How to verify | If it fails |
|---|---|---|---|
| CMP-01 | Every populated BOM line has manufacturer + exact MPN (with packaging suffix) and the MPN matches the value/footprint in the design | BOM vs schematic vs datasheet | MAJOR |
| CMP-02 | Voltage rating with margin: caps ≥ 1.5-2× working voltage (or per company derating), resistors' working-voltage limit at peaks, diodes' VRRM vs the worst-case reverse voltage | Datasheets + circuit voltages (include switching peaks) | CRITICAL if exceeded; MAJOR if margin < derating |
| CMP-03 | MLCC DC-bias and temperature derating: effective capacitance at the operating voltage still meets the circuit's need | Manufacturer DC-bias curves (e.g. Murata SimSurfing data) | MAJOR |
| CMP-04 | Current/power ratings: inductor Isat/Irms vs peak current, ferrite bead rated current and DCR drop, resistor power, connector contact current with the all-contacts-loaded derating | Datasheets + `pcb_calc.py contacts` | CRITICAL if exceeded |
| CMP-05 | Temperature range of every part covers the product's environment, including self-heating | Datasheets vs requirement | MAJOR |
| CMP-06 | Lifecycle: no obsolete / NRND / last-time-buy parts without a stated reason and alternate | Manufacturer or distributor lifecycle status (cite source + date) | MAJOR |
| CMP-07 | Availability: stock at the intended assembler or at two distributors; lead time noted for long-lead parts | Distributor / LCSC pages (cite date) | MAJOR for a single-source part with no stock |
| CMP-08 | Second source or drop-in alternate listed for each passive and for critical actives; differences called out (dielectric class, temp range) | BOM alternates column | MINOR (MAJOR for critical single-source) |
| CMP-09 | Datasheet availability: every part has a public datasheet; NDA-only parts are flagged with the unverifiable parameters | `datasheets/` folder | MAJOR if a critical parameter is unverifiable |
| CMP-10 | Connector system: mating part (cable/FPC/header) is specified; mating cycles, retention, contact plating compatible; vendor ecosystem consistent | Datasheets / non-board items list | MAJOR |
| CMP-11 | Package choice vs assembly capability (WLP/BGA pitch, 0201, bottom-terminated parts) and vs the fab's minimum features | Fab/assembler capability + datasheet | MAJOR |
| CMP-12 | Reference-design substitutions (a part replaced vs the vendor reference) are justified and equivalent in the parameters that matter | Reference BOM vs chosen BOM | MAJOR |
| CMP-13 | Value consistency: the same value uses the same MPN everywhere unless there is a reason (e.g. a higher voltage part on one net) | BOM grouping | MINOR (MAJOR if the special part could be swapped out) |
| CMP-14 | RoHS/REACH/halogen-free requirements met if stated | Datasheets | MINOR-MAJOR |
