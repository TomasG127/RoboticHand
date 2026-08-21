# Design Notes

Running log of design decisions, the reasoning behind them, and what analysis caught.

---

## Pre-fabrication geometry validation

Before any finger geometry was printed, wrist bearing loads and the full tendon path were
worked out by hand. The intent was to check that tendon length change through the joint sweep
stayed within the take-up range of the spool, and that bearing reactions were inside the
capacity of the printed housing.

The analysis caught six errors. Each is recorded here with what was wrong and what it would
have cost had it reached hardware.

### 1. Idler angle
*What was wrong:*
*Consequence if built:*
*Fix:*

### 2. Idler position
*What was wrong:*
*Consequence if built:*
*Fix:*

### 3. Inter-axis gap
*What was wrong:*
*Consequence if built:*
*Fix:*

### 4. Axis width
*What was wrong:*
*Consequence if built:*
*Fix:*

### 5. Asymmetric wrap angles
Wrap angle asymmetry between the two sides of the joint changes effective tendon length as the
joint sweeps, so a tendon tensioned correctly at one end of travel goes slack or binds at the
other.

*What was wrong:*
*Consequence if built:*
*Fix:*

### 6. Spool wrap direction
*What was wrong:*
*Consequence if built:*
*Fix:*

### Kept deliberately: axis-width asymmetry for forearm clearance
Not an error. The axis widths differ on purpose to clear the forearm gantry. Recorded here so a
future reader does not "fix" it.

---

## DIP joint coupling: torsion spring vs. flexure hinge

Three CAD revisions in Alibre Atom3D.

| Revision | Approach | Outcome |
|---|---|---|
| v1 | | |
| v2 | | |
| v3 | | |

**Current choice:**
**Reasoning:**

---

## Wrist differential

Octagonal ring-pulley differential, 2 DOF.

**Why a differential rather than two serial joints:**
**Why octagonal rather than circular:**
**Bearing selection and load path:**

---

## Tendon and anchoring

- **Line:** Dyneema / UHMWPE
- **Anchoring:** capstan wrap plus crimp sleeve
- **Why not set screws or knots:**
- **Observed slip behavior:**

---

## Open questions

- Tendon pretension: what is the right value, and how is it set repeatably?
- Print orientation for the finger links: layer adhesion vs. surface finish in the tendon channel
- Whether the palm needs a metal insert at the highest-load idler
