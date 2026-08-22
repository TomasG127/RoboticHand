# Low-Cost Dexterous Robotic Hand

A tendon-driven anthropomorphic robotic hand and wrist, designed from scratch to reach
**22 degrees of freedom** on a **sub-$400 bill of materials** — benchmarked against the
$2,400 ORCA Dexterity Hand V1.

Independent engineering project · May 2026 – present · Tomas Garcia

> **Status:** active development. A functional finger, palm, wrist, and forearm-gantry
> prototype is built and running on the bench. Tendon routing is complete for 18 of the
> 22 planned DOF. See [Current State](#current-state) for exactly what is and isn't done.

---

## Why

Dexterous robotic hands are priced out of reach for individuals and small labs. Most of
that cost sits in machined parts and proprietary actuators, not in anything fundamental
to the problem. The goal here is to find out how much of that capability survives a hard
cost constraint — FDM-printed structure, hobby-grade serial-bus servos, and off-the-shelf
UHMWPE line — and where the design has to get clever to make up the difference.

## Design targets

| Requirement | Target | Status |
|---|---|---|
| Degrees of freedom | 22 (4 per finger, 4 thumb, 2 wrist) | 18 routed |
| Bill of materials | < $400 | on track |
| Structure | FDM-printable, no machined parts | met |
| Actuation | Serial-bus hobby servos, forearm-mounted | specified |
| Reference point | ORCA Dexterity Hand V1 ($2,400) | — |

## Architecture

**Transmission.** Fully tendon-driven. Dyneema/UHMWPE line runs from forearm-mounted
servos through Bowden routing to capstan and crimp-sleeve anchors at each joint. Keeping
every actuator off the hand itself is what makes the finger and palm geometry printable
at this scale.

**Wrist.** A 2-DOF differential built around an octagonal ring-pulley arrangement, driven
by a coupled servo pair. Diagonal motion is handled by a mixing routine with magnitude
normalization rather than by naive per-axis summation.

**Actuation.** A 22-servo architecture — 14 × Feetech STS3215 for the higher-torque joints
and 8 × SCS0009 for splay and DIP. The two families use incompatible packet protocols and
both default to ID 1, so they run on physically separate buses through separate handler
instances (`sms_sts` / `scscl`). Diagnosing that was one of the more instructive failures
of the project: the symptom looked exactly like intermittent hardware death.

**Structure.** 12 unique FDM-printed parts across the whole assembly. Part count was held
down deliberately by reusing geometry across assemblies rather than optimizing each joint
in isolation.

## Engineering approach

The part of this project I'd point at first isn't a component — it's a process decision.

Before committing the wrist to fabrication, I ran a full hand-calculation pass over the
bearing loads and tendon-routing geometry rather than printing a revision and finding out.
That pass caught **six distinct geometry errors** before any of them reached hardware:

1. Idler angle and position
2. Gap between the two wrist axes
3. Width of the two axes
4. Asymmetric wrap angles, which would have produced unequal tendon length change between
   sides of the differential
5. Wrap direction of the line around each palm spool
6. A deliberately asymmetric axis width needed to clear the forearm

Five of those six would have been expensive to diagnose after assembly and nearly invisible
in CAD. The sixth turned out to be a constraint rather than a mistake. Verification before
fabrication is cheap; iteration in printed hardware is not.

Design iteration is tracked the same way — the DIP joint coupling went through three CAD
revisions in Alibre Atom3D, evaluating a torsion-spring return against a flexure hinge, and
that comparison is still open.

## Control

`control/` holds the Python bench-test tooling: keyboard-driven jog control over the
Feetech serial bus, built on `ftservo-python-sdk` and `pynput`.

Arrow keys drive the wrist differential pair, WASD drives independent finger joints, and
I/K and J/L drive the SCS0009 motors. It uses incremental **position** control with soft
travel limits rather than velocity mode, so overshoot stays bounded when a joint hits a
mechanical stop during testing.

**Scope, precisely:** this script is currently written and tested against the **6 servos**
on the finger-and-wrist prototype — not the full 22-servo build, which isn't assembled yet.

## Current state

**Built and tested**
- Functional finger, palm, wrist differential, and forearm gantry, assembled and running
- Tendons routed and secured in Bowden tubes to the motors
- 6 servos wired, addressed, and driven under keyboard jog control
- Dual-protocol (STS/SCS) bus architecture working
- Wrist differential mixing math with magnitude normalization
- Motor pulley sizing settled: 15 mm on the STS joints, reduced on the wrist for torque,
  6–8 mm minimum on the SCS motors given the tighter torque budget

**Not yet done**
- Remaining 4 of 22 DOF unrouted
- Full 22-servo assembly not built
- Full range-of-motion cable self-crossing and bearing radial-load study still pending
- Thumb CMC axis orientation not finalized for the 4-DOF thumb target
- DIP underactuation approach undecided (torsion spring vs. flexure hinge vs. full
  motorization via a forearm-routed tendon)

## Repository contents

```
control/    Python bench-test and jog control tooling
docs/       design notes, bill of materials, photos
LICENSE     PolyForm Noncommercial 1.0.0 — applies to code only
NOTICE      scope of that license; reserved rights
```

**CAD is not published here.** The mechanical design, CAD source, and derived meshes are
maintained privately and are not part of this repository. This is deliberate, not an
oversight — see [NOTICE](NOTICE).

## License

Source code in this repository is available under the
[PolyForm Noncommercial License 1.0.0](LICENSE): free to read, learn from, modify, and use
for noncommercial purposes.

Everything else — the mechanical design, CAD, documentation, and media — is
**© 2026 Tomas Garcia, all rights reserved**, and is not licensed. See [NOTICE](NOTICE) for
the full scope. Commercial licensing inquiries welcome.

## Contact

Tomas Garcia — B.S. Mechanical Engineering, University of Florida
[linkedin.com/in/garciatomas127](https://linkedin.com/in/garciatomas127)
