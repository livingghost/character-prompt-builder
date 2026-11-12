# Generation Package

Use this complete technical contract to construct, verify or forward a Generation Package. Dispatcher image routes include feature `generation-package` automatically. Standalone package construction for an external run selects that feature explicitly; an ordinary external image request does not need it. [Image Generation Runtime](image-generation.md) owns the shared depiction, target and reference semantics. [Production workflow](production-workflow.md) selects the current operation; [Prepared request execution](production-request-execution.md) and [Dispatcher execution](production-dispatch.md) own its authorization, send and recovery.

## Contents

- [Generation Package](#generation-package)
- [Verification and host forwarding](#verification-and-host-forwarding)
- [Forward the exact verified input](#forward-the-exact-verified-input)
- [Failure policy](#failure-policy)
- [Concurrent batch dispatch](#concurrent-batch-dispatch)

## Generation Package

Before preparing an external run whose delivery will also be packaged, read its selected model and complete artifact contract:

```bash
python scripts/execution_routes.py read generation --operation prepare --execution external \
  --feature generation-package --model MODEL_ID --root STUDIO
```

Keep the task's actual `execution: "external"` and select `generation-package` in its features. The builder uses the run's pinned reading and exact delivery. The package is a separately verified artifact; it does not replace the external run's sealed request or authorize submission.

Dispatcher production compiles and publishes the package, request preview and execution plan together:

```bash
python scripts/production_workflow.py prepare --root STUDIO --choices work/draft/choices.json
```

Use `draft-inputs` to create editable sources, then `prepare --choices` to compile
them directly. `build-inputs` exports derived inputs when that output is wanted;
`prepare --task` also accepts an existing direct task. New work and restored runs
use the same editing source. `execute` sends only the prepared request;
[Production workflow](production-workflow.md) locates each complete operation contract. A different request needs a
new prepared input, variant or intentional repeat, never an extra send on the
same run.

Before preparing:

1. Author the final prompt, rendering intent, selected target and applicable controls. Include the portable negative and image intent when present, and negative provenance whenever a negative source is active. A selected plot retains its actual approval. Use a [Production Specification](../production-specification.md#stateless) when the depiction needs that specialist contract, including managed subject state; ordinary descriptive work can express its scene directly in the prompt. Stateless work names no state lineage. The compiler writes derived files and binds their paths.
2. Record investigated construction questions with `--record lookups.json --element NAME` and resolve their adopted, composed or unused outcome under [Prompt-only Core](prompt-only-core.md#saved-prompt-artifacts). For a tag-based target, run its mandatory vocabulary search on the actual prompt channels and resolve the returned wording choices in that same record. Settle with the selected `--model MODEL_ID`, prompt, negative when used, weighting parser and selected plot when present. Descriptive work whose sources suffice needs no unused retrieval document; missing tag-search evidence cannot use that path. Unavailable or unsettled required retrieval blocks packaging. Approval to prepare is not approval to send.
3. Edit the ordered source choices and scope in `authoring.references` when references are selected. The builder creates the canonical prepared-reference-set and binds `generation.references`; attachment positions and board regions follow the selection. An existing prepared set can supply those choices. Preserve its source authority and state coverage, and do not author a second competing source list.

The authored parameter object can contain `{"width":832,"height":1248}`;
the builder writes its JSON file. Existing direct file inputs remain valid
public inputs. Parameter loading does not normalize prompt text.

`scripts/build_generation_payload.py` builds the Generation Package of a prepared run again, to inspect or reconstruct it. It never changes the run's request:

- The prompt is the run's delivery; there is no prompt option.
- When the run's task declares `generation.production_spec`, `plot`, `retrieval_record` or `parameters`, the builder reads that document from the run's snapshot. Naming the matching option is refused.
- When the run declares no such document, its matching file option supplies the package input. This supports standalone package construction from an external run as well as reconstruction of a dispatcher package.
- The model comes from the task's selected target or its selected specification's `target_model`; a conflicting override is not another request.
- Every file argument is a `/`-separated path below `--production-root`, or an absolute path. `--parameters-file -` reads one JSON object from standard input.
- An existing `--out` or companion is refused with `OUTPUT_ALREADY_EXISTS`; the builder never replaces a package.

The synthetic run of `examples/generation/build_example.py` declares the specification, plot, retrieval record and parameters, and the builder reads those four from the run. It takes the runtime selectors of the printed `prepare_argv`, below the example's `--out` directory (`OUT`). It also takes `--request-validation-file`, because the synthetic offering names no parameter schema:

```bash
python scripts/build_generation_payload.py \
  --production-root STUDIO \
  --production-run RUN \
  --continuity robot=one-off \
  --request-validation-file validation.json \
  --state-file OUT/runtime/state.json --cache-dir OUT/runtime/cache \
  --managed-root OUT/runtime/managed --pack-root OUT/runtime/packs/example \
  --out rebuilt-package.json
```

The builder derives the rest:

- The run is the open work task's current run, or the one `--production-run` names.
- The route reading is the one the run pinned.
- The request check is derived from the selected parameter schema the offering names, when the offering names one and the request needs no execution policy. Otherwise `--request-validation-file` supplies an authored record, as [Model request evidence](model-evidence.md#the-request-validation-record) describes.
- Visual continuity comes from `--continuity SUBJECT=DECISION`, one `recurring`, `one-off` or `undecided` decision for each production subject. The builder writes the decisions under the studio's `work/continuity/` as their basis. `--visual-continuity-file` supplies a complete record instead.

The first images of a new character are `undecided` exploration. Once the author accepts one as its identity, later images are `recurring`. `--character SUBJECT=CHARACTER` records a subject under its studio character, which a recurring subject needs. That character's current accepted identity images must be among the prepared references, and the builder refuses `recurring` without one. `--sheet-panel` marks an image for a character sheet panel.

A refused build prints the common diagnostics and exits 2 for an input defect; [Production diagnostics](production-diagnostic-navigation.md#exit-codes) lists every exit status. Naming a document the synthetic run already holds:

```json
{"ok": false, "diagnostics": [{"code": "INPUT_CONSISTENCY_ERROR", "severity": "error", "phase": "arguments",
  "file": "plot.json", "pointer": null, "message": "the prepared run holds its plot, so --plot-file competes with it",
  "required_action": "Drop --plot-file; the builder reads the run's plot.", "blocked_checks": [], "option": "--plot-file"}]}
```

For state-aware work, use `scripts/build_state_generation_package.py` with the same production arguments. It reads the prompt from the run's delivery and reports a refusal in the same common diagnostics. It validates each managed subject's supplied graph, story order, selection identity, era, appearance, state hash and references against the shared Production Specification. A multi-subject state-aware task supplies `generation.state_graphs`; a stateless participant needs no invented history. Each graph's Identity Contract character ID must exactly match the corresponding reference-selection subject and Production Specification subject IDs. `build_generation_payload.py` handles ordinary stateless input and rejects state-aware lineage. The state-aware path requires its shared Production Specification and managed graphs. Ordinary stateless generation uses a specification only when that specialist contract is selected.

State-aware example:

```bash
python scripts/build_state_generation_package.py \
  --model MODEL_ID \
  --plot-file approved-plot.json \
  --retrieval-record-file retrieval-settled.json \
  --negative-file final-negative.txt \
  --integrated-prompt-file integrated-prompt.txt \
  --negative-provenance-file negative-provenance.json \
  --brief-file source-brief.txt \
  --intent-file creative-intent.json \
  --production-spec-file production-specification.json \
  --state-graphs-file state-graphs.json \
  --references-file prepared-reference-package/prepared-reference-set.json \
  --request-validation-file request-validation.json \
  --continuity C01=recurring --character C01=C01 \
  --parameters-file parameters.json \
  --production-root STUDIO \
  --state-file PACK_STATE_JSON \
  --cache-dir CATALOG_CACHE \
  --managed-root MANAGED_PACKS \
  --pack-root ADDITIONAL_PACK_ROOT \
  --out generation-package.json
```

The builder revalidates the prepared set, copies every committed model carrier into the named sibling `<generation-package-stem>.references` directory, rewrites only carrier paths to package-relative paths inside that exact companion, rebuilds reference and generation-input hashes, verifies the staged pair, and publishes with rollback protection. Both builders refuse an existing package or companion, before building and again at publication.

Move the Generation Package JSON and its named companion together. Every carrier, including a composite board, must use a relative path under that exact companion. Absolute paths, outside-companion paths, traversal, and inferred neighboring files are invalid. Source provenance remains tied to the active pack and is revalidated under the same runtime.

## Verification and host forwarding

Verify and export the committed generation input:

```bash
python scripts/verify_generation_payload.py \
  generation-package.json \
  --studio-root STUDIO \
  --prompt-out verified-prompt.txt \
  --negative-out verified-negative.txt \
  --native-negative-out verified-native-negative.txt \
  --payload-out verified-generation-input.json \
  --target MODEL_ID \
  --state-file PACK_STATE_JSON \
  --cache-dir CATALOG_CACHE \
  --managed-root MANAGED_PACKS \
  --pack-root ADDITIONAL_PACK_ROOT
```

The verifier output retains the complete positive prompt, authored negative text, all three transport records with their availability and hashes, the complete `prepared_reference_set` and `prepared_reference_set_sha256`, its embedded canonical Reference Use Plan and plan hash, its nested Surface and Lighting Plan and hash, and the optional finalized reference-selection origin tied to State Lineage. It does not replace those objects with an abbreviated inventory.

- A relative package or output path is below `--studio-root STUDIO`; an absolute path needs no root.
- Each output (`--prompt-out`, `--negative-out`, `--native-negative-out`, `--payload-out`) must be a new file; an existing one is refused with `OUTPUT_ALREADY_EXISTS`.
- A text output holds the verified text byte for byte, with no added newline.
- A failure prints the common diagnostics and exits with the status its codes select, 2 for an input defect (synthetic, trimmed):

```json
{"ok": false, "diagnostics": [{"code": "OUTPUT_ALREADY_EXISTS", "phase": "output", "file": "vp.txt",
  "message": "--prompt-out names an existing file, which is kept: vp.txt",
  "required_action": "Choose a new --prompt-out.", "option": "--prompt-out"}]}
```

For every ordered prepared-reference row, preserve the complete source identity and source hash, bounded authority, intended influence, `subject_uses`, exact model-facing transport path, media type and transport hash, deterministic derivation, precedence, and, when state-aware, `binding_id`, `covers`, `review_dimensions`, `unsupported_or_occluded_state`, and `unsupported_assumptions`. Verification reopens current active-pack source bytes and every committed package-relative carrier byte; it also validates the optional board and its panel/source/transport hashes separately from the board hash. A pack-backed activated reference still requires its non-null embedded plan, while a supplied-file-only selection remains on the plan-null path.

The output also retains `negative_transport_mode`, the exact mode-specific `negative_transport_instruction`, negative provenance, Production Specification plus hash, State Lineage plus hash, verified parameters, and `generation_input_sha256`. That generation-input hash commits the prompts and selected rendition, parameters, Production Specification, State Lineage and selection lineage, and the complete prepared-reference-set commitment as one immutable generation input. Mutating authority, selection scope, source bytes, prepared transport, board, parameter, or lineage requires rebuilding and reverifying the package.

Require all assertions to be true:

- `forward_verified_prompt_transport`;
- `forward_verified_negative_transport`;
- `forward_ordered_reference_transports`;
- `do_not_reconstruct_from_chat`.

Those four true assertions together with the verifier's structured `host_forwarding` object are the complete forwarding contract. The adapter must not supplement them from the sparse brief, chat history, source directories, adjacent files, or remembered model behavior.

When the model record carries an offering, prepare the task, complete the execution decisions, and execute the run:

```bash
python scripts/production_workflow.py prepare --root STUDIO --task task.json
python scripts/production_workflow.py draft-execution --root STUDIO --run RUN --grant GRANT --out decisions.json
python scripts/production_workflow.py execute --root STUDIO --run RUN --decisions-file decisions.json
```

The seed, the output count and the service come from the task. [Prepared request execution](production-request-execution.md) owns the decision file, and [Production permissions](production-permissions.md) owns the authority each operation needs.

`scripts/dispatch.py` previews the run a package is bound to and sends nothing:

```bash
python scripts/dispatch.py PACKAGE --studio STUDIO --character SUBJECT_ID --slot SLOT_ID [--preview-out FILE]
```

The preview shows the sealed request of the prepared run, the one `execute` sends, and checks it against the validation evidence the run fixed. A relative path is a `/`-separated path below the studio root.

The preview refuses:

- a package bound to no prepared run (`EXECUTION_NOT_APPLICABLE`);
- a package or recording target that differs from the sealed run (`INPUT_CONSISTENCY_ERROR`);
- newly supplied source arguments that differ from their declared input (`SOURCE_CHANGED`);
- a run that already owns an execution (`DISPATCH_ALREADY_CLAIMED`).

Otherwise it prints the rendering choice, a few plain lines and the exact request the service would receive. The lines name:

- the model and the service with its endpoint;
- the output count;
- whether a negative prompt is sent;
- the run's quoted cost;
- the production run;
- each review requirement of the package;
- where `--preview-out` saved the trace, or how to save it.

A last line says `shown, not sent`. `--preview-out FILE` saves the sealed request, its transformation trace and the validation report. The synthetic run, trimmed:

```text
model: cpb-synthetic-image as synthetic:robot (offering observed 2000-01-01)
service: synthetic at http://localhost/cpb-synthetic-no-network (record observed None)
outputs: 1
negative prompt: none authored
cost: 0 USD at most (Aggregate ceiling for the explicitly listed external effects: send: Local synthetic transport performs no network request.)
production run: 01a10323-7b8a-764e-8196-44f1fb79b46e
review: Assess the selected direction against this exact rendition.
more: --preview-out FILE saves the trace and validation
shown, not sent; production_workflow.py execute sends it under the run's authorization
request (sha256 71bece6826a2f6820a6e6ebe206474f9f741159fcc648754c41a1a9de700587f):
{"count": 1, "height": 32, "model": "synthetic:robot", "operation": "generate", "prompt": "A flat graphic portrait of a simple synthetic robot standing against a plain background.", ...}
```

`execute` saves every returned image as a Production candidate with its request, response, answer, package and actual file. When the task declares a `recording` destination, it also records a Studio iteration and rewrites the gallery; a characterless output remains with its work task and run.

- The answer is kept once, and each image's response names its place in that answer and the answer's SHA-256.
- Images beside a refusal are kept, and so is a count that differs from the authorization. `run.json` in the journal records the expected and received counts, any refusal and any failed download.
- Authorized and returned counts remain distinct; a mismatch is not successful completion.
- An image the answer carries inline is decoded from it. One it names by URL is downloaded only over https from a host the transport declares. Either is kept only when its bytes are an image.

When a download fails, the images that arrived stay recorded, and `python scripts/production_workflow.py resume --root STUDIO --run RUN_ID` saves the rest from the saved answer without sending again. Direction, selection and canonical adoption require their separate authority; see [Production permissions](production-permissions.md).

The offering's service ID identifies its [Studio authentication](studio-authentication.md) configuration. Each service has one entry in the Studio's private `credentials.json`: `api_key` holds a saved value, or `api_key_env` names its runtime environment variable. Follow the existing source and the owner's choice. For a named environment source, execution reads the variable from its own process. For saved input, the Agent prepares the service's field and gives the owner the actual file path and JSON Pointer. It pauses edits while the owner fills the string and saves. Models offered by the same service use that entry, and a saved value remains available independently of environment variables.

After the chosen source is available, the Agent checks that service and the target run's authentication selection and readiness, then continues its reported next action. Missing configuration or an unusable source requires its setup or repair action. The transport receives the value separately. The execution claim retains the service and source, including the variable name for an environment source; authenticated recovery requires that recorded source. Rotating a value at the same source preserves the request. The transport sends the value only to the endpoint it accepts from the service record. That endpoint uses https, or http on a loopback address for a local test service. It never follows a redirect.

`production_workflow.py execute` performs the authorized upload and send. The public `dispatch.py` command previews the sealed request. The included Runware transport implements image generation and image upscaling; it uploads the sealed image bytes as a data URI through Media Storage and verifies the returned stored bytes before using its media UUID. A public source URL is unnecessary for that byte transport. Retained source URLs remain provenance and do not replace the sealed bytes. A catalog entry for another operation, such as video, supplies knowledge without adding an executable adapter for that operation. External host-tool execution uses the selected host tool's authentication. A Studio credential setting serves the dispatcher and does not configure that other host.

A 5xx answer, a redirect, a timeout or a dropped connection leaves unknown whether the service carried out the request. The run journal records that send as indeterminate with its reason, `execute` stops, and nothing is sent again. `resume` asks the provider once per call through the transport's lookup, and `resume --watch` keeps asking while the provider reports the task pending. When the provider holds no task, `draft-outcome` and `resume --outcome-file` record it, as [Production execution](production-recovery.md#status-and-resume) shows. The optional deadline is `PRODUCTION_HTTP_TIMEOUT_SECONDS`; see [Resource handling](../resource-handling.md).

A model exposed on no service here is sent by hand, and `studio.py iterate` records its result before anything else is done with it.

A send a loopback service answered 503, as the run journal keeps it in `indeterminate.json` (synthetic, from `scripts/dispatch_recovery_smoke_test.py`):

```json
{"body":"synthetic busy","http_status":503,"outcome":"indeterminate","reason":"the service answered 503"}
```

## Forward the exact verified input

`negative_transport_instruction` must equal the verifier-confirmed target instruction exactly. Forward only `host_forwarding.effective_prompt`, the exact verified negative channel, `host_forwarding.parameters`, and `host_forwarding.selected_references`. The effective prompt preserves the authored depiction with the selected target's declared negative handling; internal reference bindings remain verification records.

For `multi-image`, selected references are the committed independent transports in plan order. For `single-board`, the array contains only the committed board. Do not reconstruct from chat. Do not append, paraphrase, reorder, substitute, omit, add, rescope, re-rasterize, scan directories, or resolve carrier paths outside the verifier.

## Failure policy

For package dispatch, stop when the required environment remains incomplete; the target lacks a declared media type or negative mode; selected evidence is missing, unsafe, changed, or ineligible; the Surface and Lighting Plan is unresolved; the reference count exceeds the endpoint; a carrier escapes its companion; a package or hash check fails; or the host cannot receive every committed transport.

Do not continue by dropping references, changing modes, rebuilding prompt text from chat, scanning an output directory, or forwarding an unverified path. Revise the reviewed plan and regenerate the prepared set and Generation Package.

## Concurrent batch dispatch

When the user requests several images at once, across different models or as concurrent variants of one model, complete this runtime for every image first, then follow [Batch Generation Runtime](batch-generation.md). A batch only changes dispatch and review; every image keeps its own verified package, adapter, and image intent.
