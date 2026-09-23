# Reusable authoring material example

This is a constructed data-flow example, not a genre template, an artistic Persona, a real model run or user approval. It keeps exact excerpts and their application separate, saves original bytes, and creates evidence-linked extraction candidates without canonical adoption.

From the installed skill directory, run:

```sh
python scripts/create_authoring_example.py --root /absolute/path/to/empty-project
python scripts/scene_persona.py verify --root /absolute/path/to/empty-project --plan scene-plan.json --bundle scene-material --require-ready
python scripts/source_material.py verify --root /absolute/path/to/empty-project --bundle source-material
python scripts/protocol_exchange.py export --root /absolute/path/to/empty-project --artifact scene-material/material.json --out public-exchange
python scripts/protocol_exchange.py verify --root /absolute/path/to/empty-project --bundle public-exchange
```

For actual scenes replace the short constructed functional model with complete applicable originals, read them, and make the scene selection and review yourself. Changing any part of `originals/subject.md` invalidates local scene reuse, and `scene_persona.py impact` says whether the change touched a quoted heading; the archived import remains an exact copy of the imported source. No `version` or `revision` counter is needed to identify these contents.
