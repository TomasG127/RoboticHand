# Low-Cost Dexterous Robotic Hand

A 22-DOF tendon-driven anthropomorphic hand designed to reach research-grade dexterity at a
sub-$400 bill of materials, roughly 1/6 the cost of the $2,400 ORCA Dexterity Hand V1 it
benchmarks against.

> **Status: active development.** A single finger, the palm, the wrist, and the forearm gantry
> are built and bench-tested. Tendon routing is solved for 18 of 22 planned degrees of freedom.
> The thumb is not yet designed, and the full servo set has not yet been purchased. Nothing
> below describes a finished hand, and the sections marked *Planned* are explicitly not built.

| | |
|---|---|
| **Target DOF** | 22 (4 fingers x 4 DOF, thumb 4 DOF, wrist 2 DOF) |
| **Routed so far** | 18 / 22 (thumb outstanding) |
| **BOM target** | < $400 |
| **Benchmark** | ORCA Dexterity Hand V1, ~$2,400 |
| **Actuation** | 14x Feetech STS3215, 8x SCS0009 serial-bus servos |
| **Transmission** | Dyneema / UHMWPE tendon, capstan + crimp-sleeve anchoring |
| **Wrist** | Octagonal ring-pulley differential |
| **Unique printed parts** | 12 |
| **CAD** | Alibre Atom3D |
| **Fabrication** | FDM (Bambu Lab P1S), silicone molding |

---

## Why this exists

Dexterous robotic hands are priced out of reach for individuals and most university labs. The
interesting question is not whether a 22-DOF hand can be built, but how much of its capability
survives when the budget is cut by roughly 85 percent. This project is an attempt to find that
line empirically: design it, print it, load it, and record where it actually breaks.

## What is built

- **Index finger** with the full 4-DOF joint stack, tendon-routed and bench-actuated
- **Palm** housing finger mounting and tendon idlers
- **Wrist**, 2-DOF, using an octagonal ring-pulley differential
- **Forearm gantry** carrying the servo bank and tendon terminations
- **Keyboard control script** (Python, serial) for incremental servo positioning during bench tests

## What is not built

- The thumb, which carries 4 of the 22 DOF, is undesigned
- Fingers 2 through 4 exist as validated geometry but are not printed as a set
- The full 22-servo bank is not purchased; bench tests run on a partial set
- There is no closed-loop control. Current code is direct open-loop position command
- No grip-force, cycle-life, or repeatability data has been collected yet

---

## Design notes

The most useful engineering on this project so far has been hand calculation done *before*
committing anything to the printer. Sizing wrist bearing loads and walking the tendon path
analytically caught six geometry errors that would otherwise have reached hardware:

1. Idler angle
2. Idler position
3. Inter-axis gap
4. Axis width
5. Asymmetric wrap angles, which change effective tendon length through the joint sweep
6. Spool wrap direction

A seventh asymmetry, a deliberate difference in axis width for forearm clearance, was kept
intentionally. Full write-up in [`docs/DESIGN_NOTES.md`](docs/DESIGN_NOTES.md).

The DIP joint coupling went through three CAD revisions comparing a torsion-spring return
against a flexure hinge. Reasoning and the current choice are documented in the design notes.

## Repository layout

```
cad/       Source CAD and exported STLs
control/   Python serial control for bench testing
docs/      Design notes, BOM, test log
media/     Photos and video of prototype subsystems
```

## Running the control script

```bash
cd control
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python hand_control.py --port /dev/ttyUSB0
```

Keys map to individual servo channels with soft limits applied. `ESC` releases torque on all
channels. See `control/README.md` for the key map.

> **Safety:** tendon-driven joints store energy. Keep hands clear of the finger sweep when
> torque is enabled, and verify soft limits against a slack tendon before tensioning.

## Roadmap

- [ ] Design and route the thumb (closes the last 4 DOF)
- [ ] Print and assemble fingers 2 through 4
- [ ] Purchase the balance of the servo bank
- [ ] Measure grip force and joint range of motion; publish the numbers
- [ ] Tendon cycle-life test to first failure
- [ ] Closed-loop position control, then a ROS 2 interface
- [ ] Costed BOM published against the sub-$400 target

## License

MIT. See [LICENSE](LICENSE).

## Contact

Tomas Garcia, B.S. Mechanical Engineering, University of Florida
[linkedin.com/in/garciatomas127](https://linkedin.com/in/garciatomas127)
