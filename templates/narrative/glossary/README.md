# Glossary

One file per term this series uses in its own way: a place name, an institution, a piece of
equipment, a rank, a piece of slang, a thing only these people call that.

A term belonging to two characters belongs to neither of them. Written into two persona files it
becomes two definitions that are edited separately, and nothing marks which one a scene was
written against. It lives here, once, and the persona files point at it.

## The front matter every file carries

The first block of each file is the only part a machine reads. Everything below it is prose.

```
---
kind: term
id: the-late-shift
name: the late shift
references: [kanda-station]
---
```

`kind` is what this file is, and it has to match the directory the file sits in. `id` is what the
rest of the project calls it, and it has to match the file name, because that is how the project
finds it. `references` names the other ids this file talks about.

That last line is what makes the check run both ways. A file nothing names is reported, and a name
with no file behind it is refused; neither is visible from inside a single document.

```
python <skill>/scripts/narrative_index.py <series>
python <skill>/scripts/narrative_entity.py --series <series> add term <id> --name "<name>"
python <skill>/scripts/narrative_entity.py --series <series> rename <old> <new>
```

Write the file with the command rather than by hand. Renaming in particular has to be one: an id
sits in the file, in the narrative's pointers, in every scene that happens there, and in the
references other files declare, and a rename that reaches three of those four is worse than none.

## What a glossary file carries

- the term, and the one-line definition a reader needs to follow a scene;
- who uses it and who does not, because a word one faction uses and another refuses is a
  characterisation and not a synonym;
- what it is not, where a near neighbour would be confused with it;
- the chapter it is first heard in, if the audience meets it later than the characters do.
