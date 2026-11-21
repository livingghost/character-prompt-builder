"""Acquire an explicitly selected run's input revision for new authoring.

Logical source names keep their meaning in the retained revision. A domain
consumer selects either that revision or current files before acquiring its
graph; current replacements never inherit a process-wide file overlay.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import copy
from pathlib import Path
import tempfile

import execution_contract as c
from production_diagnostics import ProductionError


def identity_context(root: Path, context: dict, *, read_run=None) -> dict:
    """Project a registered retained boundary from its immutable saved revision.

    A context which already records the boundary needs no source-run access.
    An older context can obtain missing owner evidence from its exact saved
    input. Current editable choices, files and basis never redefine that input.
    This function returns a reading projection; it does not rewrite registration.
    """
    if ('retained_identity_sources' in context
            or (context.get('authoring_work') or {}).get('operation') != 'amend'):
        return context
    import production_identity_boundary as boundary
    retained = boundary.from_coverage(context.get('identity_coverage'))
    source = (context.get('derived_from') or {}).get('source_run')
    projected = copy.deepcopy(context)

    def missing(message, reason, *, owner='derived_from.source_run', **details):
        retained['unresolved'].append(boundary.unknown(owner=owner, message=message,
            reason=reason, comparison_side='retained_identity_sources',
            **({'run': source.get('run'), 'input_sha256': source.get('input_sha256')}
               if isinstance(source, dict) else {}), **details))
        projected['retained_identity_sources'] = retained
        return projected

    if source is None:
        # A complete acquired inventory remains meaningful without a saved
        # run. Earlier coverage could, however, omit a reference owner when a
        # direct source happened to contain the same bytes. Do not invent that
        # omitted authority from the candidate which is being compared.
        coverage = context.get('identity_coverage') or {}
        recorded = {(row.get('authority') or {}).get('reference') for row in retained['sources']}
        for row in coverage.get('reference_choices', []):
            if 'identity' not in row.get('use_for', []) or row.get('id') in recorded:
                continue
            missing('The retained reference use has no acquired original authority proof.',
                'retained-source-owner-unavailable', owner='identity_coverage.reference_choices',
                source='reference:' + str(row.get('id')))
        task = context.get('task_content') or {}
        graph_path = (task.get('generation') or {}).get('state_graphs')
        if graph_path and not any((row.get('authority') or {}).get('owner') for row in retained['sources']):
            missing('The retained graph owner inventory has no acquired source revision.',
                'retained-source-owner-unavailable', owner='task_content.generation.state_graphs', file=graph_path)
        projected['retained_identity_sources'] = retained
        return projected
    if not isinstance(source, dict) or not isinstance(source.get('run'), str) or not source.get('input_sha256'):
        return missing('The registered context has no exact saved input revision.',
            'retained-source-run-revision-mismatch')
    try:
        if read_run is None:
            import production_operations as workflow
            loaded = workflow.read_run(root, source['run'])
        else:
            loaded = read_run(source['run'])
    except (OSError, ValueError, KeyError, TypeError) as error:
        return missing(str(error), 'retained-source-run-unavailable')
    if (loaded.prepared.get('run') != source['run']
            or loaded.prepared.get('input_sha256') != source['input_sha256']):
        return missing('The saved run differs from the exact input revision recorded by this context.',
            'retained-source-run-revision-mismatch',
            actual_input_sha256=loaded.prepared.get('input_sha256'))
    try:
        with CapturedInputs(root, loaded) as captured:
            restored = captured.identity_sources()
    except (OSError, ValueError, KeyError, TypeError) as error:
        return missing(str(error), 'retained-source-owner-unavailable')
    # The saved source inventory supplies missing owners; meaningful evidence
    # already registered by this draft remains independently available. A
    # conflict remains visible for the common comparator to resolve explicitly.
    combined = copy.deepcopy(restored)
    for row in retained['sources']:
        if row not in combined['sources']:
            combined['sources'].append(copy.deepcopy(row))
    for row in combined['unresolved']:
        row.update(comparison_side='retained_identity_sources',
            reason='retained-source-owner-unavailable', run=source['run'], input_sha256=source['input_sha256'])
    projected['retained_identity_sources'] = combined
    return projected


def read_named(root: Path, path: str) -> bytes:
    """Acquire one explicit captured source revision in its owning Studio."""
    import production_operations as production_workflow
    prefix, run, relative = path.split('/', 2)
    if prefix != '@run' or not relative:
        raise ValueError('captured source must name @run/RUN/STUDIO_PATH')
    try:
        loaded = production_workflow.read_run(root, run)
    except ProductionError as exc:
        if exc.diagnostic.code != 'RUN_NOT_REGISTERED':
            raise
        raise ProductionError('EVIDENCE_SNAPSHOT_MISSING',
            'The captured input revision is not registered in this Studio.',
            phase='source-read', file=path, run=run,
            required_action='Open the draft in the Studio that owns this run, or select available evidence '
                            'at the validation field that names this captured source.') from exc
    return CapturedInputs(root, loaded).bytes(relative)


class CapturedInputs:
    """The complete saved Studio source graph and its portable media archive."""

    def __init__(self, root: Path, loaded):
        self.root = c._root(root)
        self.loaded = loaded
        self.prepared = loaded.prepared
        self.paths = {row['path']: row for row in self.prepared['dependencies']
                      if row['space'] in {'studio', 'task-source'}}
        self._bytes = {}
        self._references = None
        self._reference_temporary = None

    def close(self):
        if self._reference_temporary is not None:
            self._reference_temporary.cleanup()
            self._reference_temporary = None
        self._references = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def bind(self, reader):
        """Use this revision's retained named evidence without walking its parents."""
        package = self.loaded.artifacts.get('package.json') or {}
        for path, item in (package.get('input_snapshots') or {}).items():
            if not path.startswith('@run/'):
                continue
            existing = reader.retained_snapshots.get(path)
            if existing is not None and existing != item:
                raise ValueError('one captured source revision has different byte witnesses: ' + path)
            reader.retained_snapshots[path] = copy.deepcopy(item)

    def bytes(self, path: str) -> bytes:
        if path not in self.paths:
            raise ProductionError('EVIDENCE_SNAPSHOT_MISSING',
                'The selected run has no captured bytes for this source.',
                phase='variation', file=path, run=self.prepared['run'],
                required_action='Select a current source through its authored field, or prepare from current choices.')
        if path not in self._bytes:
            self._bytes[path] = self.loaded.evidence.read(self.paths[path]['sha256'])
        return self._bytes[path]

    def identity_sources(self) -> dict:
        """Read saved source owners with the same inventory used by a new draft.

        Finished inputs use their resolved reference set and binding. Unfinished
        inputs use their exact saved editable choices. All locators resolve in
        this publication's acquired bytes and source archive, never live files.
        """
        import production_identity
        import production_identity_boundary as boundary
        task = copy.deepcopy(self.prepared['task'])
        overlay = {}
        retained = self.references()
        if retained is not None:
            for path, raw in retained['files'].items():
                overlay[path] = raw
                overlay[str(retained['root'] / path)] = raw
            for row in retained['prepared']['selected_references']:
                proof = row['source']
                key = str(proof['resolved_path'])
                original = retained['companion'] + '/sources/' + proof['sha256']
                raw = retained['files'].get(original)
                if raw is None:
                    raw = self.loaded.evidence.read(proof['sha256'])
                if c.digest(raw) != proof['sha256']:
                    raise ValueError('saved identity media differs from its acquired proof: ' + key)
                if key in overlay and overlay[key] != raw:
                    raise ValueError('one retained identity locator has conflicting acquired bytes: ' + key)
                overlay[key] = raw
                if not Path(key).is_absolute():
                    overlay[str(self.root / key)] = raw
            path = '@retained-identity/prepared-references.json'
            overlay[path] = c.encoded(retained['prepared'])
            task.setdefault('generation', {})['references'] = path
        binding = self.loaded.consumer.get('image_input')
        if binding is not None:
            value = copy.deepcopy(binding)
            if retained is not None:
                value['prepared_reference_set'] = copy.deepcopy(retained['prepared'])
                from reference_delivery import reference_id
                originals = {reference_id(row): row['source'] for row in retained['prepared']['selected_references']}
                for row in value.get('references', []):
                    original = originals.get(row['id'])
                    if original is None:
                        raise ValueError('the saved binding has no exact original reference owner: ' + row['id'])
                    # A delivered carrier can be resized, converted or placed
                    # on a board. Retention compares the original source owner,
                    # just as reference_choices does when opening a new draft.
                    row['file'] = original['resolved_path']
                    row['sha256'] = original['sha256']
            path = '@retained-identity/image-input.json'
            overlay[path] = c.encoded(value)
            task['image_input'] = path

        def read(path):
            if path in overlay:
                return overlay[path]
            selected = path
            if Path(path).is_absolute():
                try:
                    selected = Path(path).relative_to(self.root).as_posix()
                except ValueError:
                    raise ValueError('the saved input has no acquired original for identity source: ' + path) from None
            return self.bytes(selected)

        choices = None
        revision = self.prepared.get('authored_revision') or {}
        if revision.get('state') == 'draft':
            descriptor = revision.get('choices')
            if not isinstance(descriptor, dict):
                return {'sources': [], 'unresolved': [boundary.unknown(owner='authored_revision.choices',
                    message='The unfinished saved input has no exact editable choices revision.')]}
            raw = read(descriptor['path'])
            if c.digest(raw) != descriptor['sha256']:
                raise ValueError('the saved unfinished choices differ from their retained descriptor')
            choices = c.decode(raw)
        basis = c.decode(read(task['work_basis'])) if task.get('work_basis') else None
        return production_identity.source_snapshot(task, read, choices=choices, basis=basis)

    def export(self, prefix: str, *, selected_paths=None) -> tuple[dict[str, bytes], dict[str, str]]:
        """Return the source tree and its explicit destinations for a new draft.

        Keys of ``files`` are relative to the requested output directory. The
        path map lets each domain owner redirect only its declared locators.
        Neither the parent publication nor its original files are written.
        """
        files, paths = {}, {}
        selected = set(selected_paths) if selected_paths is not None else None
        for path, source in self.paths.items():
            if selected is not None and path not in selected and str(self.root / path) not in selected:
                continue
            name = 'sources/' + source['sha256'] + Path(path).suffix.lower()
            files[name] = self.bytes(path)
            paths[path] = prefix.rstrip('/') + '/' + name
        retained = self.references()
        if retained is not None:
            prepared, companion = retained['prepared'], retained['companion']
            if companion:
                for path, raw in retained['files'].items():
                    name = 'references/' + path
                    files[name] = raw
                    paths[path] = prefix.rstrip('/') + '/' + name
                    paths[str(retained['root'] / path)] = paths[path]
                for old, new in retained['carrier_paths'].items():
                    paths[old] = paths[new]
            for row in prepared['selected_references']:
                source = row['source']
                archive = retained['source_archive']
                if archive is not None:
                    old = str(source['resolved_path'])
                    name = 'references/' + companion + '/sources/' + source['sha256']
                    if name in files:
                        paths[old] = prefix.rstrip('/') + '/' + name
                        try:
                            paths[Path(old).relative_to(self.root).as_posix()] = paths[old]
                        except ValueError:
                            pass
            original_path = (self.prepared['task'].get('generation') or {}).get('references')
            original = c.decode(self.bytes(original_path)) if original_path in self.paths else None
            if original is not None:
                pairs = [(old['transport']['resolved_path'], new['transport']['resolved_path'])
                         for old, new in zip(original['selected_references'], prepared['selected_references'], strict=True)]
                pairs += [(old['delivered_path'], new['delivered_path'])
                          for old, new in zip(original['prompt_artifacts'], prepared['prompt_artifacts'], strict=True)]
                if original.get('single_board') is not None:
                    pairs.append((original['single_board']['resolved_path'], prepared['single_board']['resolved_path']))
                for old, new in pairs:
                    if new in paths:
                        paths[old] = paths[new]
                        if not Path(old).is_absolute():
                            paths[str((self.root / original_path).parent / old)] = paths[new]
        return files, paths

    def references(self):
        """Expose a saved canonical reference set and its owned companion tree."""
        if self._references is not None:
            return self._references
        package = self.loaded.artifacts.get('package.json')
        prepared = package.get('prepared_reference_set') if package is not None else None
        if prepared is None:
            prepared = (self.loaded.consumer.get('image_input') or {}).get('prepared_reference_set')
        if prepared is None:
            return None
        from generation_payload_builder import validate_generation_package_carrier_paths
        prepared = copy.deepcopy(prepared)
        root = self.loaded.directory
        files, carrier_paths = {}, {}
        if package is not None:
            companion = validate_generation_package_carrier_paths(prepared, package_root=root)
        else:
            companion = 'image-input.references'
        for item in self.loaded.manifest['files']:
            if not companion or not item['path'].startswith(companion + '/'):
                continue
            raw = c.read(c.local(self.loaded.directory, item['path']))
            if c.digest(raw) != item['sha256']:
                raise ValueError('retained reference companion changed: ' + item['path'])
            files[item['path']] = raw
        if package is None:
            # External preparation captures original source bytes through the
            # image-input rows and delivered carriers in the object store.
            self._reference_temporary = tempfile.TemporaryDirectory(prefix='cpb-retained-references-')
            root = Path(self._reference_temporary.name)
            for row in prepared['selected_references']:
                source = row['source']
                files[companion + '/sources/' + source['sha256']] = self.loaded.evidence.read(source['sha256'])
            def carrier(row, field, digest):
                old = row[field]
                path = companion + '/model-references/' + digest
                files[path] = self.loaded.evidence.read(digest)
                carrier_paths[old] = path
                row[field] = path
            for row in prepared['selected_references']:
                carrier(row['transport'], 'resolved_path', row['transport']['sha256'])
            for row in prepared['prompt_artifacts']:
                carrier(row, 'delivered_path', row['delivered_sha256'])
            if prepared['single_board'] is not None:
                carrier(prepared['single_board'], 'resolved_path', prepared['single_board']['sha256'])
            for path, raw in files.items():
                output = root / path
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(raw)
            from state_protocol import finalize_artifact
            prepared = finalize_artifact(prepared)
        self._references = {'prepared': prepared, 'root': root, 'companion': companion,
                'source_archive': root / companion / 'sources' if companion else None,
                'files': files, 'carrier_paths': carrier_paths}
        return self._references

    def reference_choices(self, prefix: str, *, mirrored_input: bool = False):
        """Restore editable reference choices from saved carriers and source bytes."""
        retained = self.references()
        if retained is None:
            return None
        import production_reference_inputs
        choices = production_reference_inputs.draft(retained['prepared'], package_root=retained['root'],
            root=self.root, mirrored_input=mirrored_input, source_archive=retained['source_archive'])
        _, paths = self.export(prefix, selected_paths=())
        return production_reference_inputs.relocate_sources(choices, paths)

    def selected(self, task: dict, *, current_paths=(), current_fields=(), inherit_task_inputs: bool = False):
        return RetainedSelection(self, task, current_paths=set(current_paths),
                                 current_fields=set(current_fields), inherit_task_inputs=inherit_task_inputs)


class RetainedSelection:
    """Select saved bytes independently for each unchanged input owner."""

    def __init__(self, captured: CapturedInputs, task: dict, *, current_paths: set[str],
                 current_fields: set[str], inherit_task_inputs: bool):
        self.captured = captured
        self.task = task
        self.current_paths = current_paths
        self.current_fields = current_fields
        self.inherit_task_inputs = inherit_task_inputs
        self.used = {}
        self.directory = None

    def selected_path(self, path: str | None) -> bool:
        return (self.inherit_task_inputs and path is not None and path in self.captured.paths
                and path not in self.current_paths)

    def selected_field(self, field: str) -> bool:
        if field in self.current_fields:
            return False
        if not self.inherit_task_inputs and field not in {'world_views', 'moment_views', 'scene_materials'}:
            return False
        before = self.captured.prepared['task']
        old = (before.get('generation') or {}).get(field) if field in (before.get('generation') or {}) else before.get(field)
        after = (self.task.get('generation') or {}).get(field) if field in (self.task.get('generation') or {}) else self.task.get(field)
        return old == after and (not isinstance(after, str) or self.selected_path(after))

    def read(self, path: str) -> bytes:
        raw = self.captured.bytes(path)
        self.used[path] = raw
        return raw

    @contextmanager
    def staging(self):
        """Own temporary paths; materialize only what a selected domain reads."""
        with tempfile.TemporaryDirectory(prefix='cpb-retained-inputs-') as temporary:
            self.directory = Path(temporary)
            try:
                yield self
            finally:
                self.directory = None
                self.captured.close()

    def materialize(self, path: str, *, acquired: bool = True) -> bytes:
        if self.directory is None:
            raise ValueError('retained source acquisition needs its staged source tree')
        raw = self.read(path) if acquired else self.captured.bytes(path)
        selected = c.local(self.directory, path, exists=False)
        if not selected.is_file():
            selected.parent.mkdir(parents=True, exist_ok=True)
            selected.write_bytes(raw)
        return raw

    def source_root(self, field: str) -> Path:
        """Directory consumers inspect the complete selected source revision."""
        if not self.selected_field(field):
            return self.captured.root
        for path in self.captured.paths:
            self.materialize(path, acquired=False)
        return self.directory

    @contextmanager
    def scope(self, field: str):
        """Resolve a retained domain's nested Studio locators from its saved graph."""
        if not self.selected_field(field):
            yield
            return
        if self.directory is None:
            raise ValueError('retained source acquisition needs its staged source tree')
        with ExitStack() as stack:
            for path in self.captured.paths:
                stack.enter_context(c.staged_inputs(self.captured.root, path, self.directory / path,
                                                   on_resolve=self.materialize))
            yield

    def reference(self, path: str):
        """A retained prepared set uses its already captured portable carriers."""
        if not self.selected_path(path):
            return None
        return self.captured.references()

    def image_input(self, task: dict, add):
        """Keep an unchanged dispatcher binding's source identities and bytes.

        The image model contract is resolved again. Reference delivery and
        current source eligibility are checked by the generation owner against
        this binding, without changing its historical source locations.
        """
        import image_input
        binding = copy.deepcopy(self.captured.loaded.consumer['image_input'])
        image_input.validate_binding(binding)
        model = copy.deepcopy(binding['model'])
        image_input._model_contract(model)
        if model != binding['model']:
            raise ValueError('retained image input needs a current model selection')
        plan = c.decode(add(self.captured.root, task['image_input']))
        if c.content_id(plan) != binding['plan_sha256']:
            raise ValueError('retained image input plan differs from its captured binding')
        add(self.captured.root, binding['model']['evidence']['path'])
        for row in binding['references']:
            if c.digest(add(self.captured.root, row['file'])) != row['sha256']:
                raise ValueError('retained image input source differs from its binding')
        if binding.get('prepared_references') is not None:
            if c.digest(add(self.captured.root, binding['prepared_references'])) != binding['prepared_references_sha256']:
                raise ValueError('retained prepared references differ from their image input')
        return binding

    def acquired_dependencies(self, dependencies: list[dict]) -> dict[str, bytes]:
        """The retained bytes this compilation actually recorded, for publication."""
        return {row['path']: self.used[row['path']] for row in dependencies
                if row['space'] in {'studio', 'task-source'} and row['path'] in self.used
                and row['sha256'] == self.captured.paths[row['path']]['sha256']}
