#!/usr/bin/env python3
"""Current-contract tests for authorial intent, bindings and full-form creation.

    python scripts/authorial_intent_smoke_test.py

Synthetic current records only. No archived formats, migration, version-pair
comparisons, live services, creator approval or artistic scoring are exercised.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import authorial_intent_audit as reader
import narrative_entity
import narrative_index
import narrative_init
import persona_expression_audit

ROOT = Path(__file__).resolve().parents[1]


def entry(identifier: str = 'i-focus', status: str = 'proposed', **changes: str) -> str:
    values = {key: f'Authored {key.replace("_", " ")} in the stated synthetic scope.'
              for key in reader.REQUIRED_FIELDS}
    values.update(status=status, **changes)
    return f'### Intent {identifier}\n\n' + '\n'.join(
        f'- **{key}**: {value}' for key, value in values.items()) + '\n'


def call(function, *args):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = function(list(args))
    return code, json.loads(output.getvalue())


def hashes(root: Path):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


class CurrentRecordTests(unittest.TestCase):
    def test_complete_current_entry_has_required_locations(self):
        result = reader.parse_document(entry())
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['gaps'], [])
        self.assertEqual(set(result['intents']['i-focus']['fields']), set(reader.REQUIRED_FIELDS))

    def test_declared_status_vocabulary(self):
        for status in sorted(reader.STATUSES):
            with self.subTest(status=status):
                result = reader.parse_document(entry(status=status))
                self.assertEqual(result['errors'], [])
                self.assertEqual(result['intents']['i-focus']['declared_status'], status)

    def test_invalid_current_status_reports_error(self):
        self.assertTrue(reader.parse_document(entry(status='automatically-approved'))['errors'])

    def test_missing_current_field_is_a_gap(self):
        for field in reader.REQUIRED_FIELDS:
            with self.subTest(field=field):
                text = '\n'.join(line for line in entry().splitlines()
                                 if not line.startswith(f'- **{field}**:'))
                self.assertTrue(any(field in x['message'] for x in reader.parse_document(text)['gaps']))

    def test_blank_status_is_unresolved_not_adopted(self):
        result = reader.parse_document(entry(status=''))
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['intents']['i-focus']['declared_status'], '')
        self.assertTrue(result['gaps'])

    def test_examined_unknown_stays_a_review_gap(self):
        result = reader.parse_document(entry(review_basis='unknown: no output yet'))
        self.assertTrue(any('review_basis' in x['message'] for x in result['gaps']))

    def test_duplicate_id_is_unambiguous_error(self):
        result = reader.parse_document(entry()+'\n'+entry())
        self.assertTrue(any('duplicate intent ID' in x['message'] for x in result['errors']))

    def test_duplicate_required_field_is_error(self):
        result = reader.parse_document(entry()+'- **status**: adopted\n')
        self.assertTrue(any('duplicate field' in x['message'] for x in result['errors']))

    def test_distinct_ids_can_share_an_aim(self):
        result = reader.parse_document(entry('i-first')+'\n'+entry('i-second'))
        self.assertEqual(result['errors'], [])
        self.assertEqual(len(result['intents']), 2)

    def test_current_id_grammar_and_complete_identifier(self):
        # Portable identifier syntax is a contract; 64 characters is not a
        # semantic limit for an authored intent identifier stored in Markdown.
        for value in ('I-focus', 'with space', '1-start'):
            with self.subTest(value=value):
                self.assertTrue(reader.parse_document(entry(value))['errors'])
        for value in ('x' * 64, 'x' * 65, 'x' * 4096):
            with self.subTest(length=len(value)):
                result = reader.parse_document(entry(value))
                self.assertEqual(result['errors'], [])
                self.assertIn(value, result['intents'])

    def test_narrative_index_reports_current_intent_slot(self):
        details = narrative_index.placeholder_details('### Intent {intent_id}\n')
        self.assertTrue(any(item['label'] == '{intent_id}' for item in details), details)

    def test_form_slot_is_an_explicit_gap(self):
        result = reader.parse_document('### Intent {intent_id}\n')
        self.assertEqual(result['intents'], {})
        self.assertTrue(result['gaps'])

    def test_multiple_entries_keep_their_own_status(self):
        result = reader.parse_document(entry('i-a', 'proposed')+'\n'+entry('i-b', 'rejected'))
        self.assertEqual([v['declared_status'] for v in result['intents'].values()], ['proposed','rejected'])

    def test_comment_instruction_does_not_become_rule(self):
        self.assertEqual(reader.parse_document('<!--\n'+entry()+'\n-->')['intents'], {})

    def test_fenced_examples_are_not_rules_or_references(self):
        for marker in ('```', '~~~~'):
            text = marker+'text\n'+entry()+'- **authorial_intent_refs**: [x](bad.md#intent-x)\n'+marker+'\n'
            result = reader.parse_document(text)
            self.assertEqual(result['intents'], {})
            self.assertEqual(result['references'], [])

    def test_blockquote_and_frontmatter_are_not_rules(self):
        text = '---\nlabel: ### Intent i-fake\n---\n'+''.join('> '+line+'\n' for line in entry().splitlines())
        self.assertEqual(reader.parse_document(text)['intents'], {})

    def test_unclosed_delimiters_are_reported(self):
        for text in ('<!-- comment', '```text\nexample', '---\nkind: design'):
            with self.subTest(text=text):
                self.assertTrue(reader.parse_document(text)['errors'])

    def test_multiline_field_keeps_source_line(self):
        text = entry().replace('- **basis**: Authored basis in the stated synthetic scope.',
                               '- **basis**:\n  First line.\n  Second line.')
        result = reader.parse_document(text)
        self.assertEqual(result['gaps'], [])
        self.assertEqual(result['intents']['i-focus']['fields']['basis'], 4)

    def test_indented_markdown_references_are_supported(self):
        text='- **authorial_intent_refs**:\n  [one](x.md#intent-i-a)\n  [two](y.md#intent-i-b)\n'
        self.assertEqual(len(reader.parse_document(text)['references']), 2)

    def test_inapplicability_requires_a_reason(self):
        self.assertEqual(reader.parse_document('- **authorial_intent_refs**: n/a: no individual aim\n')['gaps'], [])
        self.assertTrue(reader.parse_document('- **authorial_intent_refs**: n/a\n')['gaps'])


class DependencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='cpb-intent-current-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, path: str, text: str | bytes) -> Path:
        p = self.root/path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text if isinstance(text, bytes) else text.encode('utf-8'))
        return p

    def project(self, status='proposed'):
        self.write('design/aim.md', entry(status=status))
        return self.write('personas/one.md', '- **authorial_intent_refs**: [aim](../design/aim.md#intent-i-focus)\n')

    def test_relative_link_resolves_exact_id(self):
        self.project()
        result = reader.audit(self.root, ['personas/one.md'])
        self.assertTrue(result['ok'],result['errors'])
        self.assertEqual(result['links'][0]['intent_id'], 'i-focus')
        self.assertEqual(result['links'][0]['target'], 'design/aim.md')

    def test_hashes_match_read_bytes(self):
        p = self.project()
        result = reader.audit(self.root, [p])
        record = next(x for x in result['files'] if x['path']=='personas/one.md')
        self.assertEqual(record['sha256'], hashlib.sha256(p.read_bytes()).hexdigest())

    def test_same_file_fragment_resolves(self):
        self.write('aim.md',entry()+'\n## Review\n- **authorial_intent_refs**: [aim](#intent-i-focus)\n')
        result = reader.audit(self.root,['aim.md'])
        self.assertTrue(result['ok'],result['errors'])
        self.assertEqual(len(result['files']),1)

    def test_multiple_inputs_read_common_target_once(self):
        self.project()
        self.write('notes/two.md','- **authorial_intent_refs**: [aim](../design/aim.md#intent-i-focus)\n')
        result = reader.audit(self.root,['personas/one.md','notes/two.md'])
        self.assertEqual(len(result['files']),3)
        self.assertEqual(len(result['links']),2)

    def test_repeated_input_is_read_once(self):
        p=self.project()
        result=reader.audit(self.root,[p,p])
        self.assertEqual(len(result['files']),2)

    def test_declared_proposal_is_not_promoted(self):
        self.project()
        result=reader.audit(self.root,['personas/one.md'])
        self.assertEqual(result['links'][0]['declared_status'],'proposed')
        self.assertTrue(result['review_notes'])
        self.assertEqual(result['adoption'],'not_assessed')

    def test_declared_adoption_is_not_verified(self):
        self.project('adopted')
        result=reader.audit(self.root,['personas/one.md'])
        self.assertEqual(result['links'][0]['declared_status'],'adopted')
        self.assertEqual(result['adoption'],'not_assessed')
        self.assertEqual(result['applicability'],'not_assessed')

    def test_rejected_intent_is_reported_not_applied(self):
        self.project('rejected')
        result=reader.audit(self.root,['personas/one.md'])
        self.assertTrue(result['ok'])
        self.assertIn('rejected',result['review_notes'][0]['message'])

    def test_missing_intent_id_is_error(self):
        p=self.project();p.write_text(p.read_text().replace('intent-i-focus','intent-i-missing'))
        self.assertTrue(reader.audit(self.root,[p])['errors'])

    def test_missing_target_is_error(self):
        p=self.project();(self.root/'design/aim.md').unlink()
        self.assertFalse(reader.audit(self.root,[p])['ok'])

    def test_unrelated_future_record_is_not_scanned(self):
        self.project()
        self.write('future.md', b'not utf8\xff')
        result=reader.audit(self.root,['personas/one.md'])
        self.assertTrue(result['ok'])
        self.assertNotIn('future.md',[x['path'] for x in result['files']])

    def test_result_omits_intent_prose_and_hidden_answers(self):
        self.write('design/aim.md',entry(portrayal_aim='HIDDEN_FUTURE_ANSWER'))
        result=reader.audit(self.root,['design/aim.md'])
        self.assertNotIn('HIDDEN_FUTURE_ANSWER',json.dumps(result))
        self.assertEqual(result['consumer_filtering'],'not_performed')

    def test_link_cycle_is_read_once_without_inferred_priority(self):
        self.write('a.md',entry('i-a')+'\n## Review\n- **authorial_intent_refs**: [b](b.md#intent-i-b)\n')
        self.write('b.md',entry('i-b')+'\n## Review\n- **authorial_intent_refs**: [a](a.md#intent-i-a)\n')
        result=reader.audit(self.root,['a.md'])
        self.assertTrue(result['ok'],result['errors'])
        self.assertEqual(len(result['files']),2)

    def test_encoded_local_space_is_supported(self):
        self.write('a space.md',entry())
        self.write('b.md','- **authorial_intent_refs**: [a](a%20space.md#intent-i-focus)\n')
        self.assertTrue(reader.audit(self.root,['b.md'])['ok'])

    def test_unrooted_file_cannot_be_read(self):
        self.write('a.md',entry())
        with self.assertRaises(ValueError):
            reader.bounded_path(self.root,self.root.parent/'outside.md')

    def test_remote_absolute_query_and_bad_fragment_are_errors(self):
        p=self.write('a.md',entry())
        for href in ('https://example.invalid/x.md#intent-i-focus','/x.md#intent-i-focus',
                     'a.md?q=1#intent-i-focus','a.md','a.md#other-i-focus',
                     '../outside.md#intent-i-focus','a.md#intent-UPPER','C:/x.md#intent-i-focus'):
            with self.subTest(href=href),self.assertRaises(ValueError):
                reader.link_target(self.root,p,href)

    def test_symlink_file_is_error(self):
        target=self.write('a.md',entry());link=self.root/'b.md';link.symlink_to(target)
        self.assertFalse(reader.audit(self.root,[link])['ok'])

    def test_symlink_parent_is_error(self):
        self.write('real/a.md',entry());(self.root/'link').symlink_to(self.root/'real',target_is_directory=True)
        self.assertFalse(reader.audit(self.root,['link/a.md'])['ok'])

    def test_directory_and_non_markdown_are_errors(self):
        self.write('x.txt','data')
        for value in ('.','x.txt'):
            self.assertFalse(reader.audit(self.root,[value])['ok'])

    def test_unreadable_utf8_keeps_partial_result(self):
        self.project();self.write('bad.md',b'\xff')
        result=reader.audit(self.root,['bad.md','personas/one.md'])
        self.assertFalse(result['ok'])
        self.assertEqual(len(result['files']),2)

    def test_bom_and_crlf_are_supported(self):
        self.write('a.md',b'\xef\xbb\xbf'+entry().replace('\n','\r\n').encode())
        self.assertTrue(reader.audit(self.root,['a.md'])['ok'])

    def test_explicit_input_budget_is_enforced(self):
        self.write('a.md',b'x'*32)
        self.assertFalse(reader.audit(self.root,['a.md'],max_bytes=16)['ok'])
        self.assertTrue(reader.audit(self.root,['a.md'])['ok'])

    def test_explicit_dependency_budget_is_enforced(self):
        self.project()
        self.assertFalse(reader.audit(self.root,['personas/one.md'],max_files=1)['ok'])
        self.assertTrue(reader.audit(self.root,['personas/one.md'])['ok'])

    def test_audit_leaves_every_file_byte_unchanged(self):
        self.project();before=hashes(self.root)
        reader.audit(self.root,['personas/one.md'])
        self.assertEqual(hashes(self.root),before)

    def test_current_content_edit_changes_fingerprint(self):
        self.project()
        before=reader.audit(self.root,['design/aim.md'])['files'][0]['sha256']
        self.write('design/aim.md',entry(portrayal_aim='Another explicit current proposal.'))
        after=reader.audit(self.root,['design/aim.md'])['files'][0]['sha256']
        self.assertNotEqual(before,after)

    def test_invalid_root_and_empty_inputs_report_errors(self):
        self.assertFalse(reader.audit(self.root/'missing',['a.md'])['ok'])
        self.assertFalse(reader.audit(self.root,[])['ok'])

    def test_cli_gap_exit_is_not_semantic_failure(self):
        self.write('a.md',entry(review_basis='undecided: inspect the output'))
        code,result=call(reader.main,'--root',str(self.root),'a.md')
        self.assertEqual(code,0)
        self.assertTrue(result['gaps'])
        code,result=call(reader.main,'--root',str(self.root),'a.md','--fail-on-gaps')
        self.assertEqual(code,2)
        self.assertEqual(result['semantic_quality'],'not_assessed')

    def test_cli_read_error_exit(self):
        code,result=call(reader.main,'--root',str(self.root),'missing.md')
        self.assertEqual(code,1)
        self.assertFalse(result['ok'])

    def test_cli_works_from_an_unrelated_directory(self):
        self.project()
        result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/authorial_intent_audit.py'),
                               '--root',str(self.root),'personas/one.md'],cwd=self.root,
                              text=True,capture_output=True,check=False)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(json.loads(result.stdout)['ok'])

    def test_help_exposes_current_arguments(self):
        result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/authorial_intent_audit.py'),'--help'],
                              text=True,capture_output=True,check=False)
        self.assertEqual(result.returncode,0)
        for flag in ('--root','--fail-on-gaps'):
            self.assertIn(flag,result.stdout)


class CurrentIntentRenameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.design = self.root/'narrative/design'
        self.design.mkdir(parents=True)
        (self.design/'project.md').write_text(
            narrative_entity.front_matter('design','project','Project','','') + entry())
        self.notes = self.root/'notes'
        self.notes.mkdir()

    def rename(self):
        code, result = call(narrative_entity.main,'--series',str(self.root),
                            'rename','project','direction')
        self.assertEqual(code,0,result)
        return result

    def test_current_design_rename_follows_active_note_binding(self):
        p = self.notes/'moment.md'
        p.write_text('- **authorial_intent_refs**: [aim](../narrative/design/project.md#intent-i-focus)\n')
        result = self.rename()
        self.assertIn('notes/moment.md',result['rewritten'])
        report = reader.audit(self.root,['notes/moment.md'])
        self.assertTrue(report['ok'],report['errors'])
        self.assertEqual(report['links'][0]['intent_id'],'i-focus')
        self.assertEqual(report['links'][0]['declared_status'],'proposed')

    def test_continuation_links_change_but_prose_fences_and_comments_do_not(self):
        p = self.notes/'moment.md'
        address = '../narrative/design/project.md#intent-i-focus'
        p.write_text('- **authorial_intent_refs**:\n  [aim]('+address+')\n\n'
                     'A prose mention [aim]('+address+').\n'
                     '<!-- - **authorial_intent_refs**: [sample]('+address+') -->\n'
                     '```markdown\n- **authorial_intent_refs**: [sample]('+address+')\n```\n')
        self.rename()
        text = p.read_text()
        self.assertEqual(text.count('direction.md#intent-i-focus'),1)
        self.assertEqual(text.count('project.md#intent-i-focus'),3)
        self.assertTrue(reader.audit(self.root,['notes/moment.md'])['ok'])

    def test_renamed_record_retains_self_intent_references(self):
        p = self.design/'project.md'
        p.write_text(p.read_text()+'\n## Review\n- **authorial_intent_refs**: '
                     '[explicit](project.md#intent-i-focus) [local](#intent-i-focus)\n')
        self.rename()
        p = self.design/'direction.md'
        self.assertIn('(direction.md#intent-i-focus)',p.read_text())
        self.assertIn('(#intent-i-focus)',p.read_text())
        report = reader.audit(self.root,['narrative/design/direction.md'])
        self.assertTrue(report['ok'],report['errors'])
        self.assertEqual(len(report['links']),2)

    def test_same_basename_elsewhere_retains_its_distinct_owner(self):
        p = self.notes/'project.md';p.write_text(entry('i-other'))
        p = self.notes/'moment.md'
        original = '- **authorial_intent_refs**: [other](project.md#intent-i-other)\n'
        p.write_text(original)
        self.rename()
        self.assertEqual(p.read_text(),original)
        self.assertTrue(reader.audit(self.root,['notes/moment.md'])['ok'])


class CurrentAuthoringTests(unittest.TestCase):
    def test_full_persona_has_twenty_sections_and_scoped_identity(self):
        text=narrative_entity.persona_document('subject-a','Subject A','A','current')
        self.assertEqual(re.findall(r'^## (\d+)\.',text,re.M),[str(n) for n in range(20)])
        self.assertIn('## 2. PORTRAYAL IDENTITY',text)
        self.assertIn('### Core-to-Performance Bindings',text)
        self.assertIn('### Portrayal Continuity Review',text)

    def test_created_persona_keeps_response_and_voice_links_as_gaps(self):
        text=narrative_entity.persona_document('subject-a','Subject A','A','current')
        labels={x['label'] for x in narrative_index.placeholder_details(text)}
        for field in ('inner_core','authorial_intent_refs','identity_and_intent_binding','identity_realization'):
            self.assertIn(field,labels)

    def test_design_has_complete_current_register_slots(self):
        text=narrative_entity.design_document('project','Project')
        self.assertIn('## Authorial intent register',text)
        for field in reader.REQUIRED_FIELDS:
            self.assertIn('**'+field+'**:',text)

    def test_neutral_init_creates_register_without_a_cast(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'work'
            code,result=call(narrative_init.main,'--out',str(root),'--series-id','project',
                             '--title','Observation','--medium','prose')
            self.assertEqual(code,0,result)
            data=json.loads((root/'narrative/narrative.json').read_text())
            self.assertEqual(data['characters'],[])
            self.assertEqual(data['themes'],[])
            self.assertIn('## Authorial intent register',(root/'narrative/design/project.md').read_text())

    def test_add_current_persona_is_not_adoption(self):
        with tempfile.TemporaryDirectory() as tmp:
            code,result=call(narrative_entity.main,'--series',tmp,'add','persona','subject-a',
                             '--character','A','--name','Subject A','--phase','current')
            self.assertEqual(code,0,result)
            text=(Path(tmp)/'narrative/personas/subject-a.md').read_text()
            self.assertIn('**adoption_scope**:',text)
            self.assertIn('**authorial_intent_refs**:',text)
            self.assertIn('no adoption yet',text)

    def test_new_identity_fields_participate_in_literal_audit(self):
        text='- **inner_core**: Repeats a sufficiently long generic explanation for review.\n- **recognizable_portrayal**: Repeats a sufficiently long generic explanation for review.\n'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a.md';p.write_text(text)
            result=persona_expression_audit.audit([p])
        self.assertEqual(len(result['duplicate_groups']),1)
        self.assertEqual(result['semantic_quality'],'not_assessed')

    def test_example_three_independent_uses_resolve(self):
        root=ROOT/'examples/authorial-intent'
        result=reader.audit(root,['notes/landscape.md','notes/steady.md','notes/switch.md'])
        self.assertTrue(result['ok'],result['errors'])
        self.assertEqual(result['gaps'],[])
        self.assertEqual(len(result['links']),3)

    def test_router_and_method_reach_intent_authority(self):
        self.assertIn('(references/runtime/authorial-intent.md)',(ROOT/'SKILL.md').read_text())
        for path in ('references/runtime/narrative-development.md','references/runtime/character-performance.md'):
            self.assertIn('(authorial-intent.md)',(ROOT/path).read_text())

    def test_documented_scope_supports_non_agents_and_multiple_modes(self):
        text=(ROOT/'references/runtime/authorial-intent.md').read_text()
        for phrase in ('unpeopled landscape','Neither mode has to be a mask',
                       'An adopted exception does not erase the general rule',
                       'A local beat can fit while the accumulated portrayal loses its center',
                       'Labels such as', 'scope'):
            self.assertIn(phrase,text)

    def test_script_is_routed_and_current_test_is_registered(self):
        text=(ROOT/'references/narrative-authoring.md').read_text()
        self.assertIn('scripts/authorial_intent_audit.py',text)
        for path in ('CONTRIBUTING.md','references/release/validation.md','.github/workflows/ci.yml'):
            self.assertIn('scripts/authorial_intent_smoke_test.py',(ROOT/path).read_text())


if __name__=='__main__':
    unittest.main(verbosity=2)
