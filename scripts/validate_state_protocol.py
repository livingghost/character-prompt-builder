#!/usr/bin/env python3
"""Validate Shared State Protocol and the canonical state-aware pilot.

This validator checks artifact contracts, lineage, deterministic examples, and
runtime artifact boundaries. It does not claim to evaluate generated image or video
quality.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import tempfile
import sys
from pathlib import Path
from typing import Any, Sequence

from production_spec import validate as validate_production_spec
from state_protocol import (
    ARTIFACT_SCHEMA_FILES,
    artifact_hash,
    load_json,
    validate_against_schema,
    validate_artifact,
    validate_state_artifact_graph,
)
from prepare_generation_references import validate_prepared_reference_set
from verify_generation_payload import verify
from shot_request import validate_request as validate_shot_request
from shot_request_smoke_test import run as run_shot_binding_smoke
from default_only_example_resolution_smoke_test import evaluate as evaluate_default_only_examples
from io_budget import environment_seconds

ROOT=Path(__file__).resolve().parents[1]

REQUIRED_ARTIFACT_TYPES=set(ARTIFACT_SCHEMA_FILES)

REQUIRED_DOCS=(
 'references/state-protocol.md','references/character-identity-contract.md',
 'references/state-event-ledger.md','references/state-aware-prompt-workflow.md',
 'references/reference-bundle-workflow.md','references/state-writeback-routing.md',
 'references/video-model-identity-evaluation-battery.md','references/state-protocol-schema-index.md',
 'references/morphology-and-species-contracts.md','references/derived-visual-evidence.md',
)

REQUIRED_HANDOFF=(
 'scripts/shot_request.py',
 'scripts/shot_request_smoke_test.py',
 'schemas/viewpoint/shot-request.schema.json',
 'templates/handoff/shot-request.template.json',
)

REQUIRED_AUXILIARY_CONTRACTS=(
 ('schemas/reference-use-plan.schema.json','templates/reference-use-plan.json'),
 ('schemas/surface-lighting-plan.schema.json','templates/surface-lighting-plan.json'),
 ('schemas/prepared-reference-set.schema.json','templates/prepared-reference-set.json'),
)

DISTINCTIVE_DETAIL_OBSERVATION_PATHS=(
 'schemas/distinctive-detail-observation.schema.json',
 'schemas/distinctive-detail.schema.json',
 'templates/distinctive-detail-observation-template.json',
)







def validate_distinctive_detail_observation_contract(
    template:dict[str,Any],
    observation_schema:dict[str,Any],
    detail_schema:dict[str,Any],
)->dict[str,Any]:
    """Exercise template-mode structure and the unchanged strict instance schema."""

    checks=[]
    errors=[]

    def record(name:str,passed:bool,detail:str)->None:
        checks.append({'name':name,'passed':passed,'detail':detail})
        if not passed:
            errors.append(f'{name}: {detail}')

    detail_properties=detail_schema.get('properties',{})
    placeholder_fields=sorted(
        name for name,schema in detail_properties.items()
        if isinstance(schema,dict) and int(schema.get('minLength',0))>0
    )
    template_probe=copy.deepcopy(template)
    probe_detail=template_probe.get('extracted_detail',{})
    if isinstance(probe_detail,dict):
        for name in placeholder_fields:
            if probe_detail.get(name)=='':
                probe_detail[name]=f'template-probe-{name}'

    template_errors=validate_against_schema(template_probe,observation_schema)
    record(
        'template-mode-allows-declared-empty-authoring-slots',
        not template_errors,
        'template structure is schema-valid after deterministic placeholder probes'
        if not template_errors else '; '.join(template_errors),
    )

    missing_path=copy.deepcopy(template_probe)
    missing_path.pop('source_scope',None)
    missing_errors=validate_against_schema(missing_path,observation_schema)
    record(
        'template-mode-rejects-missing-required-path',
        any("missing required property 'source_scope'" in item for item in missing_errors),
        'missing source_scope was rejected' if missing_errors else 'missing source_scope was accepted',
    )

    type_drift=copy.deepcopy(template_probe)
    type_drift['extracted_detail']['continuity_rules']='not-an-array'
    type_errors=validate_against_schema(type_drift,observation_schema)
    record(
        'template-mode-rejects-type-drift',
        any('continuity_rules' in item and 'expected type' in item for item in type_errors),
        'continuity_rules type drift was rejected'
        if type_errors else 'continuity_rules type drift was accepted',
    )

    strict_empty_errors=validate_against_schema(template,observation_schema)
    expected_empty_paths={f'$.extracted_detail.{name}' for name in placeholder_fields}
    observed_empty_paths={item.split(':',1)[0] for item in strict_empty_errors}
    record(
        'strict-instance-rejects-empty-template-slots',
        expected_empty_paths.issubset(observed_empty_paths),
        f'strict validation rejected {len(expected_empty_paths)} declared empty slots'
        if expected_empty_paths.issubset(observed_empty_paths)
        else f'strict validation omitted paths {sorted(expected_empty_paths-observed_empty_paths)}',
    )

    completed_errors=validate_against_schema(template_probe,observation_schema)
    record(
        'deterministic-completed-probe-passes-strict-instance-schema',
        not completed_errors,
        'deterministic probe instance passed strict validation'
        if not completed_errors else '; '.join(completed_errors),
    )

    invalid_completed=copy.deepcopy(template_probe)
    invalid_completed['extracted_detail'][placeholder_fields[0]]=''
    invalid_completed_errors=validate_against_schema(invalid_completed,observation_schema)
    record(
        'template-mode-does-not-weaken-strict-instance-validation',
        any(
            f'$.extracted_detail.{placeholder_fields[0]}' in item
            and 'minLength' in item
            for item in invalid_completed_errors
        ),
        'strict validation still rejects an emptied completed-instance field'
        if invalid_completed_errors else 'strict validation accepted an emptied completed-instance field',
    )
    return {'ok':not errors,'checks':checks,'errors':errors}


def validate(root:Path=ROOT)->dict[str,Any]:
    errors=[]; warnings=[]; validated=[]
    # The public closure includes viewpoint and reusable morphology dependencies,
    # not only the application's root-level artifact registry.
    try:
        proc = subprocess.run(
            [sys.executable, str(root / 'scripts/protocol_exchange.py'), 'check-installed'],
            cwd=root, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
            capture_output=True, text=True, encoding="utf-8",
            timeout=environment_seconds('VALIDATE_REGRESSION_TIMEOUT_SECONDS'),
        )
        public_contract = json.loads(proc.stdout)
        if proc.returncode or not public_contract.get('ok'):
            errors.append('installed public contract: ' + proc.stdout + proc.stderr)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        public_contract = {'ok': False, 'errors': [str(exc)]}
        errors.append('installed public contract: ' + str(exc))
    try:
        default_only_examples=evaluate_default_only_examples(root)
    except Exception as exc:
        default_only_examples={
            'ok':False,
            'resolved_record_ids':[],
            'missing_record_ids':[],
            'errors':[f'default-only example resolution failed: {exc}'],
        }
    if not default_only_examples.get('ok'):
        errors.append(
            'default-only runnable example resolution: '
            +'; '.join(str(value) for value in default_only_examples.get('errors',[]))
        )
    schema_dir=root/'schemas'
    artifact_map={}
    for path in sorted(schema_dir.glob('*.schema.json')):
        try: data=json.loads(path.read_text(encoding='utf-8'))
        except Exception as exc:
            errors.append(f'invalid schema JSON {path.name}: {exc}'); continue

        props=data.get('properties',{})
        kind=(props.get('artifact_type') or {}).get('const') if isinstance(props,dict) else None
        if kind:
            if kind in artifact_map: errors.append(f'duplicate artifact_type schema: {kind}')
            artifact_map[kind]=path.name
    missing=sorted(REQUIRED_ARTIFACT_TYPES-set(artifact_map))
    if missing: errors.append(f'missing protocol schemas: {missing}')
    unregistered=sorted(set(artifact_map)-set(ARTIFACT_SCHEMA_FILES))
    if unregistered: errors.append(f'artifact schemas missing from the explicit registry: {unregistered}')
    for kind,schema_name in sorted(ARTIFACT_SCHEMA_FILES.items()):
        if artifact_map.get(kind)!=schema_name:
            errors.append(
                f'artifact schema registry mismatch for {kind}: '
                f'expected {schema_name}, discovered {artifact_map.get(kind)}'
            )

    for relative in REQUIRED_DOCS:
        if not (root/relative).is_file(): errors.append(f'missing state protocol document: {relative}')

    for relative in REQUIRED_HANDOFF:
        if not (root/relative).is_file(): errors.append(f'missing shot-request artifact: {relative}')
    auxiliary_contracts_validated=[]
    for schema_relative,template_relative in REQUIRED_AUXILIARY_CONTRACTS:
        schema_path=root/schema_relative
        template_path=root/template_relative
        if not schema_path.is_file():
            errors.append(f'missing auxiliary schema: {schema_relative}')
            continue
        if not template_path.is_file():
            errors.append(f'missing auxiliary template: {template_relative}')
            continue
        try:
            schema=load_json(schema_path)
            template=load_json(template_path)
            contract_errors=validate_against_schema(template,schema)
            if contract_errors:
                errors.append(f'{template_relative}: '+'; '.join(contract_errors))
                continue
            mutated=copy.deepcopy(template)
            required_fields=schema.get('required',[])
            if required_fields:
                mutated.pop(required_fields[0],None)
                if not validate_against_schema(mutated,schema):
                    errors.append(
                        f'{template_relative}: schema does not enforce its first required field'
                    )
                    continue
            auxiliary_contracts_validated.append(template_relative)
        except Exception as exc:
            errors.append(f'{template_relative} validation failed: {exc}')
    distinctive_detail_contract={'ok':False,'checks':[],'errors':['not validated']}
    missing_distinctive=[relative for relative in DISTINCTIVE_DETAIL_OBSERVATION_PATHS if not (root/relative).is_file()]
    if missing_distinctive:
        errors.append(f'missing distinctive-detail observation contract paths: {missing_distinctive}')
    else:
        try:
            distinctive_detail_contract=validate_distinctive_detail_observation_contract(
                load_json(root/DISTINCTIVE_DETAIL_OBSERVATION_PATHS[2]),
                load_json(root/DISTINCTIVE_DETAIL_OBSERVATION_PATHS[0]),
                load_json(root/DISTINCTIVE_DETAIL_OBSERVATION_PATHS[1]),
            )
            if not distinctive_detail_contract.get('ok'):
                errors.append(
                    'distinctive-detail observation contract: '
                    +'; '.join(distinctive_detail_contract.get('errors',[]))
                )
            else:
                auxiliary_contracts_validated.append(
                    DISTINCTIVE_DETAIL_OBSERVATION_PATHS[2]
                )
        except Exception as exc:
            errors.append(f'distinctive-detail observation contract validation failed: {exc}')
    handoff_validated=False
    handoff_template=root/'templates/handoff/shot-request.template.json'
    if handoff_template.is_file():
        try:
            handoff_errors=validate_shot_request(load_json(handoff_template), allow_placeholder_hash=True)
            handoff_validated=not handoff_errors
            if handoff_errors: errors.append('shot-request template: '+'; '.join(handoff_errors))
        except Exception as exc:
            errors.append(f'shot-request template validation failed: {exc}')

    template_dir=root/'templates/state'
    for path in sorted(template_dir.glob('*.json')):
        try: data=load_json(path)
        except Exception as exc:
            errors.append(f'invalid state template {path.name}: {exc}'); continue

        if data.get('artifact_type'):
            report=validate_artifact(data,allow_placeholder_hashes=True); validated.append(path.name)
            if not report.get('ok'): errors.append(f'{path.name}: '+'; '.join(report.get('errors',[])))

    pilot_source=root/'examples/state-aware-pilot'
    for source_name, expected_kind in (
        ('species-morphology-profile.json','species-morphology-profile'),
        ('individual-morphology-contract.json','individual-morphology-contract'),
        ('character-identity-contract.json','character-identity-contract'),
    ):
        source_path=pilot_source/source_name
        if not source_path.is_file():
            errors.append(f'missing pilot source artifact: {source_name}')
            continue
        try:
            source_data=load_json(source_path)
            if source_data.get('artifact_type')!=expected_kind:
                errors.append(f'pilot source {source_name}: expected artifact_type {expected_kind}')
            source_report=validate_artifact(source_data)
            if not source_report.get('ok'):
                errors.append(f'pilot source {source_name}: '+'; '.join(source_report.get('errors',[])))
        except Exception as exc:
            errors.append(f'pilot source {source_name}: {exc}')
    state_schema_path=pilot_source/'character-state-schema.json'
    identity_path=pilot_source/'character-identity-contract.json'
    if state_schema_path.is_file() and identity_path.is_file():
        try:
            state_schema=load_json(state_schema_path)
            state_schema_report=validate_artifact(state_schema)
            if not state_schema_report.get('ok'):
                errors.append('pilot source character-state-schema.json: '+'; '.join(state_schema_report.get('errors',[])))
            if state_schema.get('identity_contract_sha256')!=artifact_hash(load_json(identity_path)):
                errors.append('pilot character state schema identity hash mismatch')
        except Exception as exc:
            errors.append(f'pilot character state schema validation failed: {exc}')

    pilot=root/'examples/state-aware-pilot/generated'
    required_pilot=(
      'world-state-snapshot.json','state-snapshot-C01.json','scene-context-snapshot.json',
      'visual-state-projection.json','appearance-adaptation-proposal.json',
      'asset-render-specification.json','state-lineage.json','production-specification.json',
      'generation-package.json','generation-package-verification.json',
      'reference-selection.json','prepared-reference-set.json',
      'reference-bundle/reference-bundle-plan.json',
    )
    for relative in required_pilot:
        path=pilot/relative
        if not path.is_file(): errors.append(f'missing pilot artifact: {relative}'); continue
        if relative.endswith('.json') and relative not in {'production-specification.json','generation-package.json','generation-package-verification.json','prepared-reference-set.json'}:
            data=load_json(path)

            report=validate_artifact(data)
            if not report.get('ok'): errors.append(f'pilot {relative}: '+'; '.join(report.get('errors',[])))
    spec_path=pilot/'production-specification.json'
    if spec_path.is_file():
        report=validate_production_spec(load_json(spec_path),require_content=True)
        if not report.get('ok'): errors.append('pilot production spec: '+'; '.join(report.get('errors',[])))
    state_graph_validated=False
    graph_paths={
      'lineage':pilot/'state-lineage.json',
      'species_profile':pilot_source/'species-morphology-profile.json',
      'individual_morphology':pilot_source/'individual-morphology-contract.json',
      'identity_contract':pilot_source/'character-identity-contract.json',
      'state_snapshot':pilot/'state-snapshot-C01.json',
      'scene_context':pilot/'scene-context-snapshot.json',
      'visual_projection':pilot/'visual-state-projection.json',
      'asset_render_spec':pilot/'asset-render-specification.json',
      'production_spec':pilot/'production-specification.json',
    }
    if all(path.is_file() for path in graph_paths.values()):
        try:
            graph_report=validate_state_artifact_graph(
                **{name:load_json(path) for name,path in graph_paths.items()}
            )
            state_graph_validated=bool(graph_report.get('ok'))
            if not state_graph_validated:
                errors.append('pilot state artifact graph: '+'; '.join(graph_report.get('errors',[])))
        except Exception as exc:
            errors.append(f'pilot state artifact graph validation failed: {exc}')

    plan_path=pilot/'reference-bundle/reference-bundle-plan.json'
    if plan_path.is_file():
        try:
            plan=load_json(plan_path)
            declared_files=[]
            for row in plan.get('assets',[]):
                if not isinstance(row,dict):
                    continue
                relative=str(row.get('render_spec_file') or '')
                declared_files.append(relative)
                child_path=plan_path.parent/relative
                if not child_path.is_file():
                    errors.append(f'pilot reference bundle missing child render spec: {relative}')
                    continue
                child=load_json(child_path)
                child_report=validate_artifact(child)
                if not child_report.get('ok'):
                    errors.append(
                        f'pilot reference bundle {relative}: '
                        +'; '.join(child_report.get('errors',[]))
                    )
                if row.get('render_spec_sha256')!=artifact_hash(child):
                    errors.append(f'pilot reference bundle {relative}: plan hash mismatch')
                if row.get('asset_id')!=child.get('asset_id'):
                    errors.append(f'pilot reference bundle {relative}: asset_id mismatch')
            actual_files=sorted(path.name for path in plan_path.parent.glob('*.render-spec.json'))
            if sorted(declared_files)!=actual_files:
                errors.append(
                    'pilot reference bundle child inventory differs from plan: '
                    f'declared={sorted(declared_files)}, actual={actual_files}'
                )
        except Exception as exc:
            errors.append(f'pilot reference bundle validation failed: {exc}')
    payload_path=pilot/'generation-package.json'
    if payload_path.is_file():
        try:
            from catalog_retrieval.runtime import using_pack_runtime
            from pack_manager import default_settings
            commons = load_json(root / 'packs/commons/pack.json')
            with tempfile.TemporaryDirectory(prefix='pilot-validation-') as workspace:
                runtime = Path(workspace)
                settings = default_settings(state_file=runtime/'state.json', cache_dir=runtime/'cache',
                    default_enabled_packs=[commons['pack_id']],
                    default_resource_providers={name: commons['pack_id'] for name in commons['content']['resource_bindings']})
                with using_pack_runtime(settings):
                    result=verify(load_json(payload_path),package_root=pilot,project=pilot)
            if result.get('verified') is not True: errors.append('pilot generation package is not verified')
        except ValueError as exc: errors.append(f'pilot generation package: {exc}')
    prepared_set_path=pilot/'prepared-reference-set.json'
    if prepared_set_path.is_file():
        try:
            prepared_set=validate_prepared_reference_set(
                load_json(prepared_set_path),model='gpt-image-2.5-flare',package_root=pilot
            )
            payload=load_json(payload_path) if payload_path.is_file() else {}
            if payload.get('prepared_reference_set')!=prepared_set:
                errors.append('pilot generation package prepared-reference-set differs from its artifact')
            if payload.get('prepared_reference_set_sha256')!=prepared_set.get('prepared_reference_set_sha256'):
                errors.append('pilot generation package prepared-reference-set hash differs from its artifact')
        except ValueError as exc:
            errors.append(f'pilot prepared reference set: {exc}')

    builder=root/'examples/state-aware-pilot/build_example.py'
    pilot_replacement_regression={
        'ok':False,'unexpected_sentinel_removed':False,'deterministic':False,
        'errors':['not run'],
    }
    if not builder.is_file():
        errors.append('missing deterministic state-aware pilot builder')
    else:
        env=dict(os.environ)
        env['PYTHONDONTWRITEBYTECODE']='1'
        deterministic_proc=subprocess.run(
            [sys.executable,str(builder),'--verify-deterministic'],
            cwd=str(root),env=env,text=True,encoding="utf-8",stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,
        )
        if deterministic_proc.returncode!=0:
            errors.append(
                'state-aware pilot deterministic verification failed: '
                +(deterministic_proc.stderr.strip() or deterministic_proc.stdout.strip())
            )
        replacement_proc=subprocess.run(
            [sys.executable,str(builder),'--replacement-self-test'],
            cwd=str(root),env=env,text=True,encoding="utf-8",stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,
        )
        if replacement_proc.returncode!=0:
            message=replacement_proc.stderr.strip() or replacement_proc.stdout.strip()
            errors.append('state-aware pilot clean-replacement regression failed: '+message)
            pilot_replacement_regression['errors']=[message]
        else:
            try:
                pilot_replacement_regression=json.loads(replacement_proc.stdout)
            except json.JSONDecodeError as exc:
                pilot_replacement_regression={
                    'ok':False,'unexpected_sentinel_removed':False,'deterministic':False,
                    'errors':[f'invalid replacement regression JSON: {exc}'],
                }
            if (
                pilot_replacement_regression.get('ok') is not True
                or pilot_replacement_regression.get('unexpected_sentinel_removed') is not True
                or pilot_replacement_regression.get('deterministic') is not True
            ):
                errors.append('state-aware pilot clean-replacement regression did not pass')

    try:
        shot_binding_regression=run_shot_binding_smoke(root)
    except Exception as exc:
        shot_binding_regression={
            'ok':False,'checks':0,'checked_bindings':[],
            'errors':[f'shot binding regression failed: {exc}'],
        }
    if not shot_binding_regression.get('ok'):
        errors.append(
            'real shot binding regression: '
            +'; '.join(str(value) for value in shot_binding_regression.get('errors',[]))
        )

    return {
      'validator':'shared-state-protocol','ok':not errors,
      'public_contract':public_contract,
      'artifact_schema_count':len(artifact_map),'artifact_types':sorted(artifact_map),
      'state_template_count':len(list(template_dir.glob('*.json'))),'validated_artifact_templates':validated,
      'state_artifact_graph_validated':state_graph_validated,
      'shot_handoff_validated':handoff_validated,
      'auxiliary_contracts_validated':auxiliary_contracts_validated,
      'distinctive_detail_observation_contract':distinctive_detail_contract,
      'default_only_example_resolution':default_only_examples,
      'pilot_replacement_regression':pilot_replacement_regression,
      'shot_binding_regression':shot_binding_regression,
      'errors':errors,'warnings':warnings,
      'quality_claim':'none; this validator checks artifact and lineage contracts, not generated media quality',
    }


def main(argv:Sequence[str]|None=None)->int:
    p=argparse.ArgumentParser(); p.add_argument('root',nargs='?',default=str(ROOT)); p.add_argument('--report-out'); a=p.parse_args(argv)
    result=validate(Path(a.root).resolve())
    if a.report_out: Path(a.report_out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8', newline='\n')
    print(json.dumps(result,ensure_ascii=False,indent=2)); return 0 if result['ok'] else 1
if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
