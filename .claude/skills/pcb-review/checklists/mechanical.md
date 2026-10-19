# Checklist: Mechanical Integration Engineer (key `mechanical`, id prefix `MEC`)

Scope: board outline, holes and fixings, height and keep-outs, connector orientation, cable/flex routing and bend radius, enclosure fit, 3D model. References: IPC-2223 (flex design: bend radius, stiffeners), connector catalogs (FPC insertion, slack, actuator clearance), IPC-2615 (dimensioning).

| ID | Check | How to verify | If it fails |
|---|---|---|---|
| MEC-01 | Board outline within the allowed envelope; corner radii/chamfers and notches dimensioned | Outline (Gerber `GBR-OUTLINE`, live outline) vs mechanical drawing/requirement | CRITICAL if it does not fit |
| MEC-02 | Mounting holes: positions match the mating part's hole pattern within tolerance, diameter suits the fastener, keep-out around heads/standoffs, plated/unplated and grounding intentional | Live pads/holes vs mating drawing | CRITICAL for misaligned holes |
| MEC-03 | Height stack-up: every element from the reference surface to the enclosure (standoff, board, tallest part, cable bend, connector actuator open) summed with tolerances; margin stated | Datasheet heights + standoff + board thickness; recompute | CRITICAL if over the limit |
| MEC-04 | Keep-outs for parts on the mating board underneath (heatsinks, connectors, tall parts): no bottom-side parts or copper features that can touch; air gap stated | Mating drawing + PCB bottom side | CRITICAL for a collision |
| MEC-05 | Connector orientation: cable entry side faces the cable path; pin 1 location consistent with the cable/flex type; actuator/latch has room to open; insertion is possible in assembly order | Connector drawings + placement + assembly sequence | CRITICAL for an impossible insertion or a reversed pin 1 |
| MEC-06 | Flex/FFC routing: bend radius ≥ the flex's minimum (IPC-2223: larger for multilayer and **dynamic** flexing), slack for assembly, no bend at the stiffener, length specified | Flex spec/drawing + geometry | MAJOR (CRITICAL if a dynamic flex is under-specified) |
| MEC-07 | Moving parts: if the board or its cable moves in use (gimbal, motor, hinge), the cable is rated for dynamic flexing and strain-relieved | System description + cable spec | MAJOR |
| MEC-08 | Fasteners and hardware listed (standoffs, screws, washers) with thread, length and material; torque or assembly notes if connectors are sensitive to board flex | Non-board BOM / assembly notes | MINOR-MAJOR |
| MEC-09 | 3D model complete: connector and tall-part bodies present, mating board/enclosure mock-up used for a clearance check | STEP / 3D views | MAJOR if the height or fit claim is unproven |
| MEC-10 | Board flex/warp sensitivity: fine-pitch connectors and BGAs away from fixing points; board thickness suits the span | Placement + connector notes (e.g. warp limits) | MINOR |
| MEC-11 | Access: test points, connectors and labels reachable after assembly in the enclosure | Placement vs assembly | MINOR |
| MEC-12 | Fabrication drawing dimensions: outline, cut-outs, holes from a datum, thickness and tolerances | Fab drawing PDF | MAJOR |
