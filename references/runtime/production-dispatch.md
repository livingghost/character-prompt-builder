# Dispatcher execution

Use this contract for `execution: dispatcher`, together with [Prepared request execution](production-request-execution.md), [Permissions](production-permissions.md) and [Recovery](production-recovery.md). The route reader delivers each complete body.

## Send and retain the prepared request

For a dispatcher, `execute` performs these steps in order:

1. It loads the sealed package and exact request.
2. It rechecks the recording destination: the Studio character, the slot, the sheet-panel condition and the subject mapping.
3. It resolves the Studio's credential selection and checks current grants and exact request approval.
4. In one transaction, it records the dispatcher handoff, records execution ownership with the nonsecret credential selection and claims the run.
5. The transaction commits before network I/O; each upload and the send then gets its own durable start boundary.
6. It saves the provider answer, downloads every returned image and registers each one as a candidate.
7. Once the provider result is terminal and all returned images are saved, it deletes the inputs uploaded by this execution through the selected transport's deletion capability. Source files, generated images and response records remain saved.

Missing scope or approval rolls back step 4 before any upload or send.
Each upload or send boundary checks the current grant and the live packs again, whatever an earlier check cached.
Revocation after a start boundary cannot undo the started request.
The send boundary records the management identifiers sent with the request.
The prepared submit scope includes deletion of its own uploaded inputs where the transport supports it. Deletion uses the immutable upload receipts and a separately saved request, so cleanup needs no new submission decision. A new generation always uploads again; only recovery within the same execution reuses its completed uploads.
An upload that the provider refuses, or that ends without a saved answer, stops the execution before its send. The inputs it uploaded before are deleted in the same call; [Recovery](production-recovery.md#status-and-resume) describes the upload whose outcome stays unknown.

## Authentication at execution

[Studio authentication](studio-authentication.md) owns credential configuration and its CLI. The selected offering's service ID identifies one entry in the Studio's private `credentials.json`. That entry contains a saved `api_key` or an `api_key_env` variable name. Follow the existing configuration and the owner's chosen method. Missing configuration or an unusable source gives a diagnostic and a concrete setup or repair action.

For an environment source, the Agent uses `studio.py credentials prepare SERVICE --environment NAME`. Execution reads that variable from its own process. Check the service and run once the variable is available. When the service has no entry, the general diagnostic proposes saved-entry preparation; follow an existing environment choice by preparing that named source. `set --from-env` instead copies the current variable value into `api_key`.

For saved input, the Agent runs the returned `credentials-prepare` action and finishes the required service entries before handing the owner `input.path` and `input.json_pointer`. The owner fills `api_key` under the selected service name and saves, while the Agent pauses its own edits. The Agent then checks that service and this run's authentication selection and readiness. The handoff requires access to the same file in the execution environment. An empty string is a supported waiting state, with a `credentials-status` action requiring the owner's input. Saved input becomes available to the next authentication resolution; submission remains governed by execution authority.

The claim records the nonsecret service and source, including the variable name for `api_key_env`. Pre-send continuation and provider lookup require that recorded source. A change between saved and environment sources, or a change to the recorded variable name, requires explicit restoration before authenticated continuation. Replacing the value at the same saved field or environment variable supports rotation and preserves the prepared request. For recovery, supply a value belonging to the provider account that owns the pending task; the local source identity does not establish that remote account relationship.

A source-difference diagnostic returns an explicit restoration action with `requires_author_input: true`. Apply the user's existing direction when it settles the intended source, or obtain the owner's decision when that choice remains open. A setup action with `requires_author_input: false` prepares the saved field within the authorized task. The Agent presents any remaining value-entry handoff after setup. Credential JSON stays outside ordinary production inputs and evidence, preserving the run's credential-independent input identity.

A complete saved answer can be downloaded and registered without resolving the API credential. A transport declared credential-free also needs no key. External host tools keep their own authentication; exact handoff and submission authorization still govern their use.

Local availability checks establish readability and format. They make no provider request and grant no submission authority. The value is supplied separately to the transport, outside request and input content hashes.
