# Source-Grounded Unpeopled Realization Example

This fictional, source-pinned test scene contains a room and a signal lamp, not an implicit
protagonist or an adopted user project. It has no required emotional arc, dialogue or narrative
climax. `world.md` owns the explicitly authored conditions; `intent.md` owns its local portrayal aim.
`base.json`, `events.jsonl` and `processes.json` are the existing state-protocol input shapes.

`plan.json` presents the later state, then an earlier state, then the later state again. Each is
resolved independently. The ribbed shell's role-specific reference key remains equal while the
signal-state key changes. The only continuous connection is explicitly named from AFTER to RETURN;
array adjacency is not treated as continuity. The author-only test marker is absent from the
selected writer views, which receive only the two chosen scalar state fields and explicit directions.
No image or prose candidate has actually been generated or artistically evaluated.

From the installed `SKILL.md` directory:

```bash
python -B scripts/world_realization.py inspect --root examples/world-realization --plan plan.json
python -B scripts/world_realization.py build --root examples/world-realization --plan plan.json --out /tmp/cpb-realization-example
python -B scripts/world_realization.py verify --root examples/world-realization --plan plan.json --bundle /tmp/cpb-realization-example
python -B scripts/world_realization.py impact --root examples/world-realization --plan plan.json
python -B scripts/portrayal_principles.py inspect persistence
```

Choose an unused output directory; build never overwrites an existing one. After editing an actual
source in your own project, impact identifies stale dependencies. Review the change, update its
pinned hash intentionally and rebuild affected units. Do not change example files to fabricate a
review or a successful image. See [the complete contract](../../references/runtime/world-realization.md)
for fields, boundaries, resource limits and failures.
