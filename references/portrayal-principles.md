# Portrayal Principles: a Small Authoring Dictionary

Use this optional dictionary while designing how a recognizable identity expresses itself, or
when a portrayal reads as generic. Its eight entries are useful distinctions rather than a
taxonomy or a personality type to assign everyone. A pattern can govern an unpeopled place, a
process or a narrator as well as a character.

The [library](portrayal-principles.json) is CPB-authored design guidance, not a psychological
classification, a FilmWorld result, a corpus-derived claim or a collection of proven image
prompts. Real-person records stay bound to evidence; a creative pattern establishes nothing about
an actual person's private motives.

## Find and read a complete entry

```bash
python scripts/portrayal_principles.py search "steady contrast"
python scripts/portrayal_principles.py inspect persistence
python scripts/portrayal_principles.py inspect designed-contrast
python scripts/portrayal_principles.py validate
python scripts/portrayal_principles.py --help
python scripts/world_realization_smoke_test.py
```

Search matches exact English tokens in IDs, names, summaries and tags and reports the matched
terms rather than an artistic score or semantic certainty. When it finds nothing, write the
principle in the project's own words rather than forcing an unsuitable record. Inspect returns the
complete entry. A missing ID or malformed record returns a JSON error and exit 1; bad CLI use
returns 2. The script writes nothing, adopts nothing and needs no pack, network or generator.

## Entries and application

| ID | Organizing principle |
|---|---|
| `persistence` | Recognition through what remains across changing conditions |
| `designed-contrast` | Recognition through linked modes and the transition between them |
| `gradual-change` | Recognition through a traceable transformation |
| `contextual-expression` | Coherent expression under different interlocutors, roles or situations |
| `channel-lag` | Meaningful timing differences between available expressive channels |
| `disclosure` | Changed understanding without an assumed change in underlying fact |
| `scoped-rupture` | An authored departure from a scoped established pattern |
| `indeterminacy` | Deliberately bounded uncertainty rather than a forced definitive identity |

Each complete entry holds:

- recognition logic;
- held dimensions;
- variation;
- activation questions;
- temporal shape;
- channel translation;
- world constraints;
- misuses;
- a hypothetical example;
- a counterexample;
- adoption instructions;
- its source basis.

Read the whole entry; the row above is only its label.

Select a pattern only when it helps state the creator's aim. Name the intent ID and record why the
pattern applies, which parts fall outside it, and the project-specific interpretation. The owning
authorial intent register sets scope and adoption status; a retrieved ID is design provenance
rather than a hidden runtime command, and retrieval alone adopts nothing. When a library entry is
edited, the adopted intent and instantiated rules keep their authority: review the affected
interpretations explicitly and change personas only through that review. Several patterns can
coexist at different scopes, each for a stated aim rather than to raise an imagined individuality
score.

An individual subject instantiates the pattern through the complete persona:

- internal priorities;
- known information;
- voice;
- posture;
- attention;
- choices;
- conditional response;
- switch;
- held features;
- aftermath.

A non-agent subject uses its world or design record rather than an invented mind. Keep to the
adopted body's channels and the selected medium's capabilities.

`persistence` is recognition through what remains; one identical pose, silence in every scene or
emotional absence misreads it. `designed-contrast` links two modes; casual speech as false and
decisive speech as the true personality misreads it. The same decisive line can serve either
pattern, depending on surrounding behavior and timing. Pronoun, gender, species, age, occupation,
backstory and genre stay outside both entries.

Use the [performance probes](runtime/character-performance.md) and the
[intent review](runtime/authorial-intent.md) to compare an ordinary case, a consequential changed
condition and an unused situation, as the request needs. Characters may react alike in some cases,
and one isolated line may leave them hard to tell apart; review the whole span, including
constancy and variation. World-state and presentation dependencies follow
[Scoped Realization](runtime/world-realization.md). Image prompt wording still passes the separate
retrieval-before-composition gate and its evidence rules.
