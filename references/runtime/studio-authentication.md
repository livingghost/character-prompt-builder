# Studio authentication

Activate this document when configuring a service API key, inspecting or changing its source, or repairing authentication before execution or recovery. Use the service ID selected by the model's offering. Each service has one authentication entry in the Studio's private `credentials.json`: `api_key` holds a saved value, or `api_key_env` names the process environment variable that supplies it.

The Studio supplies access to the service. [Production permissions](production-permissions.md) supplies authority for the exact operation, and [Production execution](production-execution.md) performs the authorized request. An available key establishes neither a grant nor approval of a request.

## Contents

- [Choose the credential source](#choose-the-credential-source)
- [Prepare key entry](#prepare-key-entry)
- [Use a process environment variable](#use-a-process-environment-variable)
- [Verify the saved key and continue](#verify-the-saved-key-and-continue)
- [Check the selected source and continue](#check-the-selected-source-and-continue)
- [Supply a saved value through the setter](#supply-a-saved-value-through-the-setter)
- [Service configuration and storage](#service-configuration-and-storage)
- [Change a source, rotate a value or remove an entry](#change-a-source-rotate-a-value-or-remove-an-entry)
- [Execution and recovery](#execution-and-recovery)
- [Logs and saved evidence](#logs-and-saved-evidence)
- [Local protection and portability](#local-protection-and-portability)
- [Diagnose availability](#diagnose-availability)

## Choose the credential source

Run commands in the skill's locked uv environment as [SKILL.md](../../SKILL.md#mandatory-execution-environment) specifies. `--studio` accepts the Studio or a directory inside it and defaults to the working directory. `SERVICE` is the ID used by the model's selected offering. Models offered by that service use the same service entry.

Inspect the service with `credentials status SERVICE --studio STUDIO`. Follow its existing configuration and the user's chosen method. For an unconfigured service, prepare the source established by the task and existing preferences. Ask the owner to choose only when those leave the method open. The Agent performs configuration, availability checks and continuation; the owner supplies the key through the selected source.

| Selected source | Agent setup | Owner input |
| --- | --- | --- |
| Saved JSON value | `credentials prepare SERVICE --studio STUDIO` | Fill `api_key` directly under the service name in the prepared `credentials.json`, then save. The Agent gives the actual path and exact JSON Pointer. |
| Process environment variable | `credentials prepare SERVICE --environment NAME --studio STUDIO` | Supply `NAME` through the executing process's established environment or secret-injection mechanism. The JSON records its name in `api_key_env`. |

A diagnostic for an unconfigured service proposes saved-entry preparation. When the user selected an environment source, prepare that named source instead. Both paths finish with the [selected-source checks](#check-the-selected-source-and-continue).

Each service declares exactly one source. A missing saved value remains attached to its `api_key` field; a missing environment value remains attached to its named variable. Resolve availability at that source. Hidden terminal input, stdin and `set --from-env` are additional ways to write the service's saved JSON value.

## Prepare key entry

The Agent prepares the service's `api_key` string in the Studio's private UTF-8 `credentials.json`. The owner's task is to fill that string with the API key and save the file.

For a Runware offering, inspect its service selection and prepare the private input file:

```bash
python scripts/studio.py credentials status runware --studio STUDIO
python scripts/studio.py credentials prepare runware --studio STUDIO
```

Use the diagnostic's `next_action.argv` when it matches the selected method. A `credentials-prepare` action with `requires_author_input: false` belongs to the Agent. Complete the required service entries before handing the file to the owner, then pause the Agent's own edits until the owner finishes saving. Commands lock their updates, but an external text editor does not participate in that lock.

This synthetic example shows the complete file for one service awaiting input:

```json
{
  "example-service": {
    "api_key": ""
  }
}
```

The Agent creates this structure. The owner replaces only the empty string at `example-service.api_key` with their API key, preserving valid JSON. A key containing a quote or backslash needs the corresponding JSON string escape; an editor with JSON support can help preserve the syntax. Saving completes the owner's input step. The Agent then checks availability and continues the production task.

Preparation returns the actual file path and JSON Pointer. This illustrative excerpt identifies the prepared input field:

```json
{
  "available": false,
  "input": {
    "path": "/work/example-studio/credentials.json",
    "format": "json",
    "encoding": "utf-8",
    "json_pointer": "/example-service/api_key"
  }
}
```

Give the owner the returned `input.path`, the service name, the exact field identified by `input.json_pointer`, and the returned writing instructions. For `/example-service/api_key`, explain that `api_key` is inside `example-service`. Keep explanatory text and sample values outside the credential value. An empty string is the supported input-waiting state; an empty file is incomplete JSON.

Use this handoff where the owner can open the same file the Agent prepared. If the execution environment is separate from the owner's machine, establish access to that file or use a supported input channel the owner can access. Include the actual reachable destination in the handoff.

Repeated `prepare` retains an existing saved value or environment source. A usable saved source returns its input location with `available: true` and `next_action: null`; proceed to readiness checks. An environment source returns `input: null` and its current availability. To change an existing source deliberately, use the explicit options in [Change a source, rotate a value or remove an entry](#change-a-source-rotate-a-value-or-remove-an-entry).

A saved value is the JSON string at the selected service's `api_key` field. Authentication passes that decoded string unchanged: whitespace, escaped line breaks, Unicode, punctuation and length have no common key-format rule. The empty string is the input-waiting state. UTF-8 with or without a leading BOM is accepted; command writes use ordinary UTF-8 JSON.

## Use a process environment variable

Configure the variable that supplies the key to the executing process:

```bash
python scripts/studio.py credentials prepare SERVICE --environment LOCAL_API_TOKEN --studio STUDIO
python scripts/studio.py credentials status SERVICE --studio STUDIO
```

Use the variable name specified by the owner or the existing configuration. The name is independent of service IDs and model names. For a synthetic service, the complete configuration is:

```json
{
  "example-service": {
    "api_key_env": "LOCAL_API_TOKEN"
  }
}
```

Execution reads the variable's current value when an authenticated operation needs it. The configuration stores only its name. This preparation completes source selection in one command and can run before the variable is available. Its result distinguishes configuration success from `available: false` with a diagnostic.

The variable must be available to the process running the Skill. Keep the owner's established environment or secret-injection mechanism in place. A variable supplied to another process or machine needs to be made available to this execution environment. The Agent verifies that service through `credentials status`, keeping the value in its selected source.

`prepare --environment NAME` selects a live environment source. `set --from-env NAME` copies the variable's current value into a saved `api_key` string. Choose the operation that matches the owner's method. Changing the environment value affects subsequent reads of a live source. For an existing execution, supply a value for the provider account that owns its pending task.

Continue through [Check the selected source and continue](#check-the-selected-source-and-continue) once the source is available.

## Verify the saved key and continue

After the owner reports that the JSON has been saved, the Agent checks the same service through `credentials status`. Keep values with their credential owner and use this nonsecret inspection rather than printing the private file. Prompts, task files, command arguments and chat carry the service and input location, while the private input channel carries the value.

A prepared entry waiting for input produces the same path and JSON Pointer, with a `credentials-status` action whose `requires_author_input` is `true`. Present that handoff, wait for the owner's saved input, and then perform the status command.

A malformed JSON document requires correction of the existing file. Its input metadata uses an empty JSON Pointer to identify the whole document, and the file is retained for repair. A selected `api_key` that is not a string identifies `/SERVICE/api_key`; supply its string value while preserving other services. Other saved values remain available when the document's structure is readable. An operating-system read failure is reported as an access failure. The authentication reader imposes no additional file-permission, ownership, link-count or size requirement.

Saving makes the value available to the next authentication resolution. The Agent checks after the handoff. File changes alone do not start monitoring or submit a request.

## Check the selected source and continue

After the selected saved or environment source is ready, the Agent checks the service and target run:

```bash
python scripts/studio.py credentials status SERVICE --studio STUDIO
python scripts/production_workflow.py status --root STUDIO --run RUN_ID
```

Confirm that the service is available and that the run's `authentication.selection` identifies the intended service and source. Inspect `authentication.required`, `authentication.available`, `readiness`, diagnostics and `next_action`. A run status command's top-level `ok` means that inspection succeeded. An unscoped credential listing can also succeed with no configured services. Use the named service and the specific run to establish readiness.

Resume the original task through its reported next action after the required input and current authorization checks are satisfied. Local availability means the selected source supplied a nonempty string. The provider establishes key validity, account identity, permissions and balance when an authorized operation uses the key. Local availability inspection makes no provider request.

## Supply a saved value through the setter

The owner can use the prepared JSON field or an available input channel. To receive a value through hidden terminal input:

```bash
python scripts/studio.py credentials set SERVICE --studio STUDIO
```

The prompt hides the value. Without a usable terminal, the command reports the input limitation and a preparation action for the JSON handoff. An existing approved channel can supply standard input:

```bash
python scripts/studio.py credentials set SERVICE --stdin --studio STUDIO
```

The caller supplies the complete stdin text, including any intended whitespace. The setter saves that text unchanged, including a trailing newline if the caller supplies one. The setter captures the service's existing entry before receiving input, then checks that the entry is unchanged before saving. A concurrent source change or saved-key update returns a diagnostic and preserves the current file. Inspect the service and repeat the intended update when appropriate.

To import a value already present in the executing process's environment:

```bash
python scripts/studio.py credentials set SERVICE --from-env LOCAL_API_TOKEN --studio STUDIO
```

`--from-env` saves the variable's current value in this service's `api_key`. Subsequent executions use that saved copy. Changing or removing the input environment variable leaves the saved value intact. `--stdin` and `--from-env` are mutually exclusive input options.

All setter methods receive a nonempty string and preserve it unchanged. `set` explicitly selects saved storage, including when the service previously used an environment variable. Its report contains the selection and local availability while keeping the value, its fragments and its hash private.

## Service configuration and storage

The service name is the top-level key in `credentials.json`. Its entry contains exactly one of these fields:

| Service entry | Meaning | Value owner |
| --- | --- | --- |
| `{"api_key":""}` | A prepared saved-value field; the empty string awaits owner input. | The service's `api_key` string in this Studio's private JSON. |
| `{"api_key_env":"LOCAL_API_TOKEN"}` | A selected runtime environment source. | `LOCAL_API_TOKEN` in the executing process. |

The two fields are mutually exclusive. Use one complete service entry for its chosen method. Each additional service gets its own top-level entry in the same file. Models using the same service reuse that entry. Service identifiers use lowercase letters, digits and hyphens and start with a letter or digit. Environment names use letters, digits and underscores, beginning with a letter or underscore.

A named lookup or status check inspects that service's source and value. An unrelated service entry or additional metadata does not block the lookup. Updates preserve other entries. A status listing reports each configured service independently; Studio validation checks the configured source identities separately from value availability.

A new execution resolves the selected offering's service. A claimed execution also requires the nonsecret source recorded with its claim. The source record exists for execution recovery; the owner edits only the service's `api_key` or `api_key_env` configuration.

Credential management operates on local Studio configuration. Use the exact service ID from the selected offering. Local management does not require loading a catalog and does not prove that a matching service or executable transport is available. Model and service definitions remain with their pack owners.

## Change a source, rotate a value or remove an entry

The first `prepare SERVICE` creates an empty `api_key` field if the service has no entry. Later preparation preserves its existing source and value. The owner can replace the string at `/SERVICE/api_key` and save to rotate the value; the Agent then checks that service and the affected run. The setter writes the same field. Changing the value within this source preserves the prepared request and its content hashes.

An explicit source change replaces the service's entry:

```bash
python scripts/studio.py credentials prepare SERVICE --environment LOCAL_API_TOKEN --studio STUDIO
python scripts/studio.py credentials prepare SERVICE --stored --studio STUDIO
```

Use the command for the chosen method. `--environment NAME` selects the named live variable and replaces any saved entry for that service. `--stored` creates an empty `api_key` when switching from an environment source and preserves an existing saved value. The Agent completes this setup before asking the owner to fill an empty string. These options are mutually exclusive. `set` also selects saved storage while supplying its value.

A claimed execution continues to require its recorded source. When the current source differs, inspect the expected selection and the user's direction. Apply that direction when it settles the intended source; ask for a decision when it leaves the account relationship open. The returned repair command restores the recorded source explicitly. Restoration may prepare a saved field that needs owner input. Follow that handoff before continuing the existing run.

Remove the service's local authentication entry with:

```bash
python scripts/studio.py credentials remove SERVICE --studio STUDIO
```

This deletes the entry, including its saved value or environment-variable reference, while preserving other services. The process environment and the provider's key remain under their own owners. Provider revocation is a separate provider operation. A claimed execution whose service entry was removed requires its recorded source to be prepared again before authenticated continuation.

A whole Studio folder copy includes `credentials.json` and its saved keys. Those copied values are independent of the original file. Environment entries keep their variable names and read them from the new executing process. Moving or copying the Studio retains the service names and source identities recorded in its executions; the owner establishes that the supplied values belong to the accounts those tasks need.

## Execution and recovery

`production_workflow.py execute` resolves authentication before claiming the dispatcher execution. The claim records the service and source, with the variable name when the source is `api_key_env`. These illustrative selections contain no credential values:

```json
{"service":"example-service","source":"api_key"}
```

```json
{"service":"example-service","source":"api_key_env","variable":"LOCAL_API_TOKEN"}
```

The included Runware transport implements image generation and image upscaling. `dispatch.py` displays the exact sealed request; the Production execute command performs the upload and send.

For an unclaimed run, readiness checks the service's current entry. Once claimed, pre-send continuation or provider lookup requires the recorded source. Changing from `api_key` to `api_key_env`, changing back, or changing the recorded variable name produces a source-difference diagnostic. Its explicit restoration action has `requires_author_input: true`; resolve the intended source from the user's direction or the owner's decision before restoring it. Recovery retains the original request identifiers and submission evidence.

Replacing the value at the same `api_key` field, or changing the value of the same environment variable, supports rotation. For recovery, use a replacement belonging to the same provider account that owns the task. Source identity identifies the local input location; the provider and credential owner establish the remote account behind its value.

A complete saved answer can be downloaded and registered without resolving the API key. This recovery may fetch retained result URLs; it does not submit another generation request. A transport declared credential-free uses no authentication value. Dispatcher run status includes `authentication.required`, `available`, `selection`, `diagnostics`, and `remote_validation: "not-performed"`. `required` states whether the next provider step needs a value; `available` is `null` when no credential lookup is necessary.

These observations belong to live status. `check`, `prepare`, prepared inputs, requests and the frozen execution plan retain their credential-independent identity. A run can be prepared before its API key is available.

External host tools use their host's authentication, and their run status reports `authentication: null`. The Studio setting serves the dispatcher; host tools and connectors own their own credential setup. External execution continues through the exact handoff, claim, host call and settlement procedure.

## Logs and saved evidence

The credential value is supplied separately as an authentication input to the transport. Authored prompts, model records, Generation Packages, sealed request payloads, input hashes and execution-selection metadata retain their own content. The private `credentials.json` lives inside the Studio but remains outside the ordinary production input and artifact contract. Private writes avoid registering key contents, size or content hash as operation artifacts.

Credential commands return service names, nonsecret source selections, availability and diagnostics. Authentication values read by the running operation are registered for later log redaction, including short or numeric strings. [Operation diagnostics](operation-logs.md#what-the-records-keep) owns the distinction between explicit values and automatic environment discovery, and the behavior of redacted exit explanations.

The saved provider answer retains returned response content. A provider's sensitive response text can therefore appear in the saved answer. Diagnostic redaction has its own scope; it does not transform arbitrary console output or formal response evidence. Inspect the actual artifacts intended for sharing.

`logs-export` collects its bounded diagnostic records and re-applies their redaction. Official Skill packaging rejects declared private credential state in release inputs. These operations keep `credentials.json` out of their exports, while an arbitrary whole-folder copy or backup includes it. Handle the actual credential file as private account configuration when choosing what to share or retain. The private-path boundary identifies declared credential state; renamed copies of its contents require their own handling.

## Local protection and portability

Preparation appends root-anchored credential and temporary-file rules to the Studio's `.gitignore`, preserving its existing bytes and retaining an already-final rule block. This setup completes before a credential file is published. Git ignore governs ordinary staging of untracked files; already-tracked files, forced staging and whole-folder copies follow their respective owners.

The file is plaintext JSON, and the operating system controls access. Command writes use a temporary file created with the operating system's private-file defaults before publishing the complete JSON. On POSIX this creates mode `0600`; Windows uses the directory's access rules. Reading an existing configuration does not inspect or repair its permissions, owner, file type, links or timestamps. Storage access failures are reported from the ordinary file operation.

Each authentication lookup reads the current JSON and takes the selected service's `api_key` string, or reads the variable named by `api_key_env`. It returns that value unchanged. The reader adds no document-size limit, key-length limit, whitespace normalization or provider-independent key syntax. A lookup uses the document it reads; the next lookup reads the setting again. A syntactically valid JSON document and a configured string establish local availability only. The selected transport and service determine whether that value works for their authentication method. Finish saving before checking availability.

Credential commands lock the Studio and publish complete JSON updates after comparing the current file with the bytes read for that edit. A concurrent change returns a diagnostic and preserves the current file. This comparison protects the owner's edits when saving an update.

The Agent completes preparation before handing the JSON to the owner and pauses its own updates while the owner edits. An external editor can save an older buffer independently of command locks. Whole-document syntax errors receive a document-repair diagnostic that retains the file for correction. Authentication resolves the declared service entry within the Studio; ordinary task input paths remain outside that mechanism.

A local credential travels with its Studio when the complete folder is copied. An environment entry reads the process that executes the command. Confirm these actual access relationships when moving, sharing or restoring a Studio.

## Diagnose availability

`CREDENTIAL_UNAVAILABLE` identifies an unconfigured service, an unavailable selected string, an unreadable or malformed configuration, or a source differing from a claimed execution. Follow its concrete action for the Studio and service. Repairing authentication preserves the prompt, request and run identity with their existing owners.

| Observed state | Agent action | Owner handoff |
| --- | --- | --- |
| Service has no entry | Follow the [source choice](#choose-the-credential-source): prepare a saved field or the specified environment variable. | Choose the method only when the task and existing preferences leave it open. |
| Saved source needs preparation | Run the returned `credentials-prepare` action with `requires_author_input: false`, then inspect its result. | Give the actual path and JSON Pointer after setup, when a value is still needed. |
| Environment source is selected but its variable is missing or empty | Retain the selected name and check the process's configured source. Recheck that service after correction. | Supply the intended variable through the established environment mechanism. |
| Prepared `api_key` is the empty string | Retain its path and JSON Pointer; check the same service after the owner saves. | Fill that JSON string with the key and save. `credentials-status` requires owner input while the value is pending. |
| Selected saved value is not a string | Use the returned `/SERVICE/api_key` location. | Supply a JSON string and preserve the rest of the document. |
| JSON syntax or structure is malformed | Retain the existing file and present the document-repair diagnostic, whose JSON Pointer is empty. | Correct the JSON document and save it. |
| Claim's source differs from the current entry | Inspect the expected selection and the user's account direction, then use the returned explicit restoration action. | Decide the intended account relationship when existing direction leaves it open. |
| The selected value is locally available | Check the target run's authentication selection, readiness and next action, then continue within its authority. | Key entry is complete. |

Use `studio.py credentials status SERVICE --studio STUDIO` for the intended service, then `production_workflow.py status --root STUDIO --run RUN_ID` for the specific run. Provider rejection, quota, billing and account permissions are reported by the actual service operation. Interpret those failures from the returned evidence; local checks establish that the selected source supplied a value.
