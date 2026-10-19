# Checklist: Circuit Engineer (key `circuit`, id prefix `CIR`)

Scope: schematic correctness at pin level against datasheets and reference designs. Out of scope: part sourcing (component), layout (pcb).

| ID | Check | How to verify | If it fails |
|---|---|---|---|
| CIR-01 | Every IC pin is connected as its datasheet requires (power, ground, exposed pad, NC vs DNC, test/mode pins) | Datasheet pin table, pin by pin, vs netlist | CRITICAL |
| CIR-02 | The circuit matches the vendor reference design, or each deviation is justified | Reference schematic/BOM in the brief or the datasheet's application circuit | MAJOR (CRITICAL if functional) |
| CIR-03 | Connector pin numbering in the symbol matches the manufacturer drawing (pin 1, odd/even rows, mounting pads) | Connector drawing vs symbol vs footprint | CRITICAL |
| CIR-04 | Pin-swaps and mirrored pinouts are intentional and the mating side (cable/flex/peer) is consistent | Follow pin 1 through the cable/flex type (same-side vs opposite-side contacts) | CRITICAL |
| CIR-05 | Unused pins are handled per datasheet (tied, floating allowed, No-ERC marked) and unused outputs cannot be enabled by accident | Datasheet + schematic | MAJOR |
| CIR-06 | Pull-ups/pull-downs: present where needed, value suits the bus speed and load, connected to the correct rail, not duplicated across boards beyond spec | Datasheet + bus spec (e.g. I2C rise time vs pull-up and capacitance) | MAJOR |
| CIR-07 | Passive values are computed and justified (feedback/limit resistors, RC, current limits, bias), and the computed result is inside the datasheet range | Recompute with datasheet equations; cite page | MAJOR |
| CIR-08 | Polarity and orientation of polarized parts (diodes, electrolytics, LEDs) is correct in the schematic | Symbol pin names vs datasheet | CRITICAL |
| CIR-09 | Voltage domains do not mix without translation; every net has one driver type (no two push-pull outputs together) | Netlist + datasheets | CRITICAL |
| CIR-10 | Differential pairs and controlled-impedance nets are identified in the schematic (net names, directives / net classes) so layout rules can bind to them | Schematic directives / net classes | MAJOR |
| CIR-11 | ERC clean, or every remaining warning explained | ERC report / live `proj_get_erc_violations` | MAJOR for unexplained errors |
| CIR-12 | Schematic is readable: functional blocks, consistent net names, no ambiguous junctions, notes for non-obvious choices, title block filled | Schematic PDF | MINOR (house style may raise this) |
| CIR-13 | High-voltage or high-current nets are identified (net class, notes) so layout can apply spacing and width rules | Schematic net classes / notes | MAJOR if HV is unmarked |
| CIR-14 | Protection where an interface leaves the enclosure or is user-touchable (ESD, reverse polarity, overcurrent), or a justified statement why not | Schematic + docs | MAJOR for external interfaces |
| CIR-15 | Schematic ↔ PCB in sync (no unmatched parts or nets) | Live `proj_get_differences` | CRITICAL if out of sync |
