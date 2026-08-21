# CAD

Source models authored in Alibre Atom3D.

| Folder | Contents |
|---|---|
| `source/` | Native Alibre part and assembly files |
| `stl/` | Exported meshes, as printed |
| `step/` | Neutral-format exports for anyone without Alibre |

Export a STEP alongside every STL. Alibre files are not widely readable and a mesh cannot be
edited; STEP is what makes this repository useful to someone else.

## Naming

`<subsystem>_<part>_v<rev>`, for example `finger_proximal-link_v3`.
