# Dexterous Robotic Hand

This is a tendon-driven robotic hand with a target of 22 degrees of freedom and a parts budget below $400, previously an independent project by Tomas Garcia and now under collaborative development by our student team.

**Status: prototype development, October 2026.** This is not a finished 22-DOF hand.

## Current build

- Built: forearm motor gantry, wrist, palm, and one actuated finger.
- Tendon routing has been developed for four fingers. The thumb is still outstanding.
- Basic bench control has been used to move the prototype. The working bench script is **not yet published here**.
- We have not published measured joint range, speed, grip force, endurance, or verified total build cost.

## Design targets

| Item | Target or current choice |
| --- | --- |
| Degrees of freedom | 22 planned, including a 2-DOF wrist and 4-DOF thumb |
| Actuation | Baseline: 14 Feetech STS3215 and 8 SCS0009 servos |
| Transmission | Tendon-driven, with forearm-mounted motors |
| Fabrication | Primarily FDM-printed parts |
| Bill of materials | Below $400, **not yet verified** |
| CAD | Alibre Atom3D used for the original prototype |

Motor alternatives, the final controller, sensing, and several mechanical details are still under review. The targets above are not performance results.

## Repository

- [`control/`](control/) contains an **unfinished Python control scaffold**, not the script currently used on the bench. [`hand_control.py`](control/hand_control.py) has no working bus or keyboard loop yet. Do not use it to drive tensioned hardware.
- [`docs/DESIGN_NOTES.md`](docs/DESIGN_NOTES.md) has earlier design notes and incomplete sections. Treat it as draft history until the current design is documented.
- [`docs/BOM.md`](docs/BOM.md) is an older estimate, not the current inventory or a verified cost breakdown.
- [`docs/TEST_LOG.md`](docs/TEST_LOG.md) is a template, not a record of measured performance.
- [`media/`](media/) has a media plan. Prototype photos and videos have not been added.

We use separate project documents and issue tracking for ongoing work. Relevant open GitHub issues include [tendon anchoring](https://github.com/TomasG127/RoboticHand/issues/5), [PTFE tube support](https://github.com/TomasG127/RoboticHand/issues/6), [control software](https://github.com/TomasG127/RoboticHand/issues/7), and [thumb design](https://github.com/TomasG127/RoboticHand/issues/12).

## Next work

- Document the existing prototype and its actuator/joint map.
- Improve tendon tensioning and the motor-end tube supports.
- Replace the control scaffold with tested, documented code.
- Develop the thumb and evaluate actuator options.
- Measure motion, range, speed, force, and durability before making performance claims.
- Cost the full bill of materials against the budget target.

## CAD and license

CAD source, meshes, and manufacturing files are **not public**. Do not add them to this repository without an explicit decision to release them.

The [PolyForm Noncommercial 1.0.0 license](LICENSE) applies **only to source code**. Mechanical designs, documentation, and media remain reserved. See [NOTICE](NOTICE).

## Main Contact

Tomas Garcia
[LinkedIn](https://linkedin.com/in/garciatomas127)

## Secondary Contacts

Nicholas Chaves

Brandon Covert

Eric Chen
[LinkedIn](https://www.linkedin.com/in/eric-chen-597a0242b/)

Alberto Riefkohl Zambrana
[LinkedIn](https://www.linkedin.com/in/alberto-riefkohl/)
