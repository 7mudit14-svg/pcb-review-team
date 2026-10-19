# Checklist: Hardware Test Engineer (key `test`, id prefix `TST`)

Scope: design for test (DFT), bring-up plan, verification of each requirement, production test, fault isolation. The test engineer asks: *when the first board arrives, how do we prove each requirement, and how do we find the fault if it fails?*

| ID | Check | How to verify | If it fails |
|---|---|---|---|
| TST-01 | Each requirement has a test: method, equipment, pass/fail criterion (numbers), and who/what performs it | Requirements trace + bring-up plan | MAJOR |
| TST-02 | Bring-up sequence is safe: visual → resistance checks between rails → current-limited power → rails → interfaces one at a time → full function; abort criteria defined | Bring-up doc | MAJOR |
| TST-03 | Test access: every rail, ground, key control signal and HV node is probeable (test pad, via or component pad) with a label; probe points reachable in the assembled state | Layout + silkscreen | MAJOR for rails/HV with no access |
| TST-04 | High-speed links have a verification method (enumeration speed, link training status, error counters, eye/BER if equipment exists, loopback) | Bring-up plan | MAJOR |
| TST-05 | HV nodes: measurement method and safety notes (probe rating, discharge, max voltage), and a check that the HV stays within part ratings | Plan + datasheets | MAJOR |
| TST-06 | Control interfaces (I2C/SPI/GPIO) have a first-contact test (address scan, ID register read) and a fallback if logic levels or addressing are wrong (rework option, DNP footprint) | Plan + schematic options | MAJOR |
| TST-07 | Current consumption limits per mode are stated for test (idle, active, peak) with tolerances | Power budget | MINOR-MAJOR |
| TST-08 | Fault-isolation aids: 0 Ω links or jumpers to split rails/loads, LED or test pad indicators, ability to power sub-blocks separately | Schematic | MINOR |
| TST-09 | Rework feasibility of risky parts (WLP/BGA, fine-pitch connectors): access for hot air, no tall parts shadowing; spare footprints if a fix is anticipated | Placement | MINOR |
| TST-10 | Production test: fixture-able test pads (size, pitch, one side), IPC-D-356 netlist for bare-board test, time per board | Package | MINOR |
| TST-11 | Environmental/robustness tests implied by requirements (temperature, vibration, flex cycling for moving cables, ESD) are listed even if not performed | Requirements | MINOR-MAJOR |
| TST-12 | Test documentation: where results are recorded, revision tracking of test procedures | Docs | INFO-MINOR |
