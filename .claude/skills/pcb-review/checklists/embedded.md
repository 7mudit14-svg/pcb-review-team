# Checklist: Senior Embedded Engineer (key `embedded`, id prefix `EMB`)

Scope: system architecture, requirements traceability, interfaces between this board and everything it connects to, control and firmware implications, and system-level assumptions. Out of scope: copper geometry (pcb), part ratings (component), power-tree numbers (power), except where they break an interface.

| ID | Check | How to verify | If it fails |
|---|---|---|---|
| EMB-01 | Every requirement in the brief maps to a design feature **and** to a verification method | Build the trace table: requirement → where met → how proven. Look for orphans in both directions. | MAJOR (missing requirement → CRITICAL if it is a hard constraint) |
| EMB-02 | Stated assumptions are explicit, justified and listed with their consequences | Approach/decision docs. Hidden assumptions (e.g. "one board per camera", "host provides pull-ups") must be written down. | MAJOR if an unstated assumption drives the design |
| EMB-03 | Interface control: every connector pin has a name, direction, voltage domain and owner (this board / host / peripheral) | Schematic + pinout tables vs the peer's documented pinout (camera, motherboard, sensor) | CRITICAL for a mismatch with the peer's pinout |
| EMB-04 | Signal naming perspective is consistent end to end (TX/RX from whose side? P/N?) and crossovers happen exactly once | Follow each pair from source pin to sink pin through every connector and cable | CRITICAL if TX meets TX or P/N inverts where not allowed |
| EMB-05 | Protocol rules honoured: e.g. forbidden lines left unconnected, AC-coupling caps where the spec puts them, lane polarity, required sideband pins | Interface spec named in the brief + datasheets | CRITICAL for a forbidden connection; MAJOR otherwise |
| EMB-06 | Bus addressing: no address collisions on any shared bus, including multiple identical boards on one host | Device datasheets (address pins) + system topology | MAJOR (CRITICAL if both devices must work at once) |
| EMB-07 | Logic-level compatibility at every boundary (VIH/VIL/VOH/VOL, open-drain pull-up rail, 5 V tolerance) | Datasheet electrical tables for both sides | CRITICAL if out of spec; MAJOR if unverifiable (datasheet missing) |
| EMB-08 | Power-up / reset / enable states are defined: every enable, reset or select pin has a pull-up or pull-down or a driver, and its default does what the system expects | Schematic + datasheet default behaviour | MAJOR |
| EMB-09 | Hot-plug, power sequencing and back-powering between domains are considered (a peripheral powered before the host, I/O clamped through ESD diodes) | Datasheets (abs-max on I/O when unpowered) | MAJOR |
| EMB-10 | Firmware/host software implications are documented: register setup, safe defaults, outputs that must never be enabled, bring-up order | Approach doc / bring-up plan | MINOR-MAJOR |
| EMB-11 | Multi-instance / system context: if the product uses several identical boards (e.g. stereo pair), identification, addressing, synchronisation/trigger and cabling are addressed | Brief + docs | MAJOR if it blocks the system's purpose |
| EMB-12 | Modularity: blocks reusable, variants/options documented (DNP, 0 Ω options, spare pins), future-proofing justified rather than speculative | Schematic, variants, docs | MINOR |
| EMB-13 | Failure modes: what happens if a cable is unplugged, a rail shorts, the host stops driving a line; is the board safe? | Reasoned FMEA-lite in the findings | MAJOR for an unsafe failure |
| EMB-14 | The design decisions log matches what was built (no decision contradicted by the schematic/layout) | Decision IDs vs design | MAJOR |
| EMB-15 | Out-of-scope items are explicitly named (what the host/motherboard must provide) | Docs | MINOR |
