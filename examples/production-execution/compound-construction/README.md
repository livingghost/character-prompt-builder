# Synthetic image-prompting tasks

This package contains seven synthetic tasks and separate assessment notes for
[Agent evaluation](../../../references/runtime/agent-evaluation.md). The files
define evaluation inputs and assessment criteria; they are not execution results.
Cases 01-05 examine interacting construction requirements. Cases 06-07 examine
prompt-review judgment about expression, useful detail and revision scope.
These are different bounded assessments, not a combined claim of capability.

## Contents

- [Case 01](tasks/case-01.md)
- [Case 02](tasks/case-02.md)
- [Case 03](tasks/case-03.md)
- [Case 04](tasks/case-04.md)
- [Case 05](tasks/case-05.md)
- [Case 06](tasks/case-06.md)
- [Case 07](tasks/case-07.md)
- [Assessment notes](assessor-notes.md)

## Use

Give only the text of one task file to the agent for each independent task. Keep the assessment notes separate until after the agent has completed its response. Do not include another task's response in the next task's input.

Use `assessor-notes.md` afterward to assess the response. Its explanations establish feasibility and assessment criteria; they do not restrict valid responses to a single composition or wording.
