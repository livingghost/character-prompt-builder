#!/usr/bin/env python3
"""Offline structural regressions, not an evaluation of fictional individuality.

    python scripts/character_performance_smoke_test.py

Tests literal hygiene, full/custom persona creation and routed ownership contracts.
No network, images, persistent pack state, existing project edits or approval.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import persona_expression_audit as audit_module  # noqa: E402
import narrative_entity  # noqa: E402
import narrative_index  # noqa: E402
import narrative_init  # noqa: E402

LONG = 'Checks the current task, explains one reason, and waits for a specific answer.'


def invoke(function, *args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = function(list(args))
    return code, json.loads(stream.getvalue())


class FieldExtractionTests(unittest.TestCase):
    def fields(self, text):
        return audit_module.authored_fields(text)[0]

    def test_inline_fields_and_locations(self):
        fields = self.fields('# Voice\n\n- **rhythm**: ' + LONG + '\n')
        self.assertEqual(fields[0]['line'], 3)
        self.assertEqual(fields[0]['heading'], 'Voice')
        self.assertEqual(fields[0]['normalized_text'], LONG)

    def test_multiline_value(self):
        fields = self.fields('- **rhythm**:\n  Answers after one beat\n  and asks a precise follow-up.\n')
        self.assertEqual(fields[0]['normalized_text'], 'Answers after one beat and asks a precise follow-up.')

    def test_comments_do_not_become_content_or_shift_lines(self):
        fields = self.fields('<!-- example\n- **voice**: false\n-->\n- **rhythm**: ' + LONG)
        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0]['line'], 4)

    def test_multiline_inline_comment_is_masked(self):
        fields = self.fields('- **voice**: quiet <!-- not\na character fact --> and measured\n')
        self.assertEqual(fields[0]['normalized_text'], 'quiet and measured')

    def test_nested_fields_container_not_compared(self):
        fields = self.fields('- **speech_style**:\n  - **rhythm**: ' + LONG + '\n')
        self.assertEqual([f['field'] for f in fields], ['rhythm'])

    def test_nested_field_stops_at_sibling(self):
        fields = self.fields('- **mode**:\n  - **rhythm**: measured\n  - **speech_style**: precise\n')
        self.assertEqual([f['normalized_text'] for f in fields], ['measured', 'precise'])

    def test_nested_field_stops_at_parent_prose(self):
        fields = self.fields('  - **rhythm**: measured\nParent commentary.\n')
        self.assertEqual(fields[0]['normalized_text'], 'measured')

    def test_fenced_and_blockquoted_samples_are_not_fields(self):
        for fence in ('```', '~~~', '````'):
            text = f'{fence}text\n- **voice**: {LONG}\n{fence}\n> - **rhythm**: {LONG}\n'
            self.assertEqual(self.fields(text), [])

    def test_a_different_or_shorter_fence_does_not_close(self):
        text = '````text\n```\n- **voice**: false\n~~~\n````\n- **voice**: true\n'
        self.assertEqual([f['normalized_text'] for f in self.fields(text)], ['true'])

    def test_quoted_fence_does_not_hide_later_fields(self):
        text = '> ```\n> quoted\n> ```\n- **voice**: ' + LONG
        self.assertEqual(len(self.fields(text)), 1)

    def test_unclosed_comment_is_reported(self):
        fields, notes = audit_module.authored_fields('Intro\n<!--\n- **voice**: ' + LONG)
        self.assertEqual(fields, [])
        self.assertEqual(notes, [{'line': 2, 'kind': 'unclosed-comment'}])

    def test_unclosed_fence_is_reported(self):
        fields, notes = audit_module.authored_fields('Intro\n```\n- **voice**: ' + LONG)
        self.assertEqual(fields, [])
        self.assertEqual(notes, [{'line': 2, 'kind': 'unclosed-fence'}])

    def test_metadata_does_not_become_field(self):
        text = '---\n- **voice**: not portrayal\n---\n- **voice**: ' + LONG
        self.assertEqual(self.fields(text)[0]['normalized_text'], LONG)

    def test_unclosed_metadata_is_reported(self):
        fields, notes = audit_module.authored_fields('---\n- **voice**: ' + LONG)
        self.assertEqual(fields, [])
        self.assertEqual(notes[0]['kind'], 'unclosed-front-matter')

    def test_unknown_state_is_not_duplicate_evidence(self):
        for value in ('unknown', 'Unknown', 'n/a', 'not applicable', 'none', 'undecided'):
            self.assertEqual(self.fields('- **voice**: ' + value), [])

    def test_exact_language_forms_are_preserved(self):
        fields = self.fields('- **sentence_endings**: keeps 「습니다」 in public\n')
        self.assertEqual(fields[0]['normalized_text'], 'keeps 「습니다」 in public')

    def test_unknown_custom_fields_and_tables_are_not_inferred(self):
        self.assertEqual(self.fields('- **custom_mode**: '+ LONG + '\n| voice | ' + LONG + ' |'), [])

    def test_blank_and_instruction_only_values_are_not_filled(self):
        self.assertEqual(self.fields('- **voice**:\n<!-- long guidance is not content -->\n'), [])

    def test_only_whitespace_is_normalized(self):
        fields = self.fields('- **voice**: Answer.\n- **rhythm**: answer.\n')
        self.assertNotEqual(fields[0]['normalized_text'], fields[1]['normalized_text'])


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cpb-expression-audit-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def file(self, name='one.md', text=None):
        p = self.root / name
        p.write_text(text if text is not None else '- **voice**: ' + LONG + '\n', encoding='utf-8')
        return p

    def test_single_file_does_not_require_second_person(self):
        result = audit_module.audit([self.file()])
        self.assertTrue(result['ok'])
        self.assertEqual(result['duplicate_groups'], [])
        self.assertEqual(result['semantic_quality'], 'not_assessed')

    def test_duplicates_within_file_are_advisory(self):
        p = self.file(text='- **voice**: '+LONG+'\n- **rhythm**: '+LONG+'\n')
        code, result = invoke(audit_module.main, str(p))
        self.assertEqual(code, 0)
        self.assertTrue(result['duplicate_groups'][0]['advisory'])
        self.assertEqual(result['duplicate_groups'][0]['scope'], 'within-file')
        self.assertEqual([loc['line'] for loc in result['duplicate_groups'][0]['locations']], [1, 2])

    def test_cross_file_duplicate_keeps_both_locations(self):
        result = audit_module.audit([self.file(), self.file('two.md')])
        self.assertEqual(result['duplicate_groups'][0]['scope'], 'across-files')
        self.assertEqual(len(result['duplicate_groups'][0]['locations']), 2)

    def test_whitespace_only_variation_compares_equal(self):
        result = audit_module.audit([self.file(), self.file('two.md', '- **voice**: ' + LONG.replace(' ', '  '))])
        self.assertEqual(len(result['duplicate_groups']), 1)

    def test_case_and_punctuation_do_not_compare_equal(self):
        result = audit_module.audit([self.file(), self.file('two.md', '- **voice**: ' + LONG.lower())])
        self.assertEqual(result['duplicate_groups'], [])

    def test_unicode_threshold_counts_characters_not_bytes(self):
        text = '한글中文かな漢字'
        a = self.file(text='- **voice**: '+text)
        b = self.file('two.md', '- **voice**: '+text)
        self.assertEqual(audit_module.audit([a,b], min_chars=len(text)+1)['duplicate_groups'], [])
        self.assertEqual(len(audit_module.audit([a,b], min_chars=len(text))['duplicate_groups']), 1)

    def test_short_shared_form_is_not_a_default_warning(self):
        result = audit_module.audit([self.file(text='- **sentence_endings**: です\n- **voice**: です\n')])
        self.assertEqual(result['duplicate_groups'], [])

    def test_same_file_is_not_compared_to_itself_twice(self):
        p = self.file()
        result = audit_module.audit([p, p.parent / '.' / p.name])
        self.assertEqual(len(result['files']), 1)
        self.assertEqual(result['duplicate_groups'], [])

    def test_blank_is_a_draft_gap_not_an_input_failure(self):
        p = self.file(text='- **rhythm**:\n')
        code, report = invoke(audit_module.main, str(p))
        self.assertEqual(code, 0)
        self.assertTrue(report['ok'])
        self.assertEqual(report['files'][0]['unfilled'][0]['line'], 1)
        code, report = invoke(audit_module.main, str(p), '--fail-on-unfilled')
        self.assertEqual(code, 2)
        self.assertTrue(report['ok'])

    def test_repeated_text_is_not_error_with_fail_on_unfilled(self):
        p = self.file(text='- **voice**: '+LONG+'\n- **rhythm**: '+LONG+'\n')
        code, _ = invoke(audit_module.main, str(p), '--fail-on-unfilled')
        self.assertEqual(code, 0)

    def test_missing_and_good_inputs_return_partial_report(self):
        code, report = invoke(audit_module.main, str(self.file()), str(self.root/'missing.md'))
        self.assertEqual(code, 1)
        self.assertEqual(len(report['files']), 1)
        self.assertEqual(len(report['errors']), 1)

    def test_non_markdown_is_rejected(self):
        self.assertFalse(audit_module.audit([self.file('one.txt')])['ok'])

    def test_directory_is_rejected(self):
        p = self.root / 'directory.md'
        p.mkdir()
        self.assertFalse(audit_module.audit([p])['ok'])

    def test_invalid_utf8_is_reported(self):
        p = self.root / 'bad.md'
        p.write_bytes(b'\xff\xfe')
        self.assertFalse(audit_module.audit([p])['ok'])

    def test_operator_budget_is_reported_without_discarding_input(self):
        p = self.file(text='x'*11)
        self.assertFalse(audit_module.audit([p], max_bytes=10)['ok'])
        self.assertEqual(p.read_text(encoding='utf-8'), 'x'*11)
        self.assertTrue(audit_module.audit([p])['ok'])

    def test_utf8_bom_and_crlf(self):
        p = self.root / 'bom.md'
        p.write_bytes(('\ufeff---\r\nkind: persona\r\n---\r\n- **voice**: '+LONG+'\r\n').encode())
        report = audit_module.audit([p])
        self.assertTrue(report['ok'])
        self.assertEqual(report['files'][0]['recognized_fields'], 1)
        self.assertEqual(report['files'][0]['parse_notes'], [])

    def test_input_is_unchanged_hash_matches(self):
        p = self.file()
        before = p.read_bytes()
        report = audit_module.audit([p])
        self.assertEqual(p.read_bytes(), before)
        self.assertEqual(report['files'][0]['sha256'], hashlib.sha256(before).hexdigest())
        self.assertFalse(report['mutates_files'])
        self.assertEqual(report['adoption'], 'not_assessed')

    def test_arbitrary_count_of_files_no_cast_grid(self):
        paths = [self.file(f'c{i}.md') for i in range(7)]
        report = audit_module.audit(paths)
        self.assertEqual(len(report['files']), 7)
        self.assertEqual(len(report['duplicate_groups']), 1)

    def test_invalid_threshold_is_an_argument_error(self):
        with self.assertRaises(ValueError):
            audit_module.audit([], min_chars=0)
        for value in ('0', '-1', 'word'):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                audit_module.main(['one.md', '--min-chars', value])
            self.assertEqual(raised.exception.code, 2)

    def test_cli_runs_from_other_working_directory(self):
        p = self.file()
        result = subprocess.run([sys.executable, str(ROOT/'scripts/persona_expression_audit.py'), str(p)],
                                cwd=self.root, text=True, encoding="utf-8", capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['ok'])

    def test_help_documents_non_semantic_purpose(self):
        result = subprocess.run([sys.executable, str(ROOT/'scripts/persona_expression_audit.py'), '--help'],
                                text=True, encoding="utf-8", capture_output=True, check=False)
        self.assertEqual(result.returncode, 0)
        self.assertIn('--fail-on-unfilled', result.stdout)
        self.assertIn('never a rating', result.stdout)


class AuthoringContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cpb-performance-form-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_full_form_still_has_twenty_sections(self):
        text = (ROOT/'templates/narrative/personas/persona-template.md').read_text(encoding='utf-8')
        self.assertEqual(re.findall(r'^## (\d+)\.', text, re.M), [str(i) for i in range(20)])

    def test_added_persona_carries_field_local_rules(self):
        text = narrative_entity.persona_document('c1', 'Example', 'C1', 'current')
        self.assertNotIn('# Persona Template', text)
        for heading in ('### Conditional Response Rules', '### Contextual Voice Modes',
                        '### Performance and Context Probes'):
            self.assertIn(heading, text)
        self.assertIn('No global relationship/emotion priority', text)
        self.assertIn('No automatic agreement or visible leakage', text)

    def test_address_inventory_is_not_a_second_switching_table(self):
        text = (ROOT/'templates/narrative/personas/persona-template.md').read_text(encoding='utf-8')
        self.assertIn('IDENTITY lists the self/address forms and compact scope.', text)
        self.assertIn('Do not duplicate the form registry.', text)

    def test_new_fields_are_visible_as_drafting_gaps(self):
        text = narrative_entity.persona_document('c1', 'Example', 'C1', 'current')
        labels = {f['label'] for f in narrative_index.placeholder_details(text)}
        for label in ('embodied_baseline_context', 'speech_delta', 'listening_delta',
                      'overlap_resolution', 'switch_release_and_repair',
                      'probe_findings_and_revision'):
            self.assertIn(label, labels)

    def test_template_instructions_do_not_become_duplicate_personality(self):
        p = ROOT/'templates/narrative/personas/persona-template.md'
        report = audit_module.audit([p])
        self.assertEqual(report['duplicate_groups'], [])
        self.assertTrue(report['files'][0]['unfilled'])

    def test_created_profile_exposes_identity_and_response_binding(self):
        text = narrative_entity.persona_document('c1', 'Example', 'C1', 'current')
        for field in ('identity_and_intent_binding', 'identity_realization', 'authorial_intent_refs'):
            self.assertIn('**'+field+'**:', text)

    def test_neutral_seed_adds_no_person_or_expression_defaults(self):
        series = self.root/'neutral'
        code, report = invoke(narrative_init.main, '--out', str(series), '--series-id', 'demo',
                              '--title', 'Example', '--medium', 'prose')
        self.assertEqual(code, 0, report)
        data = json.loads((series/'narrative/narrative.json').read_text(encoding='utf-8'))
        self.assertEqual(data['characters'], [])
        self.assertEqual(data['themes'], [])
        self.assertFalse((series/'narrative/personas/c01.md').exists())
        copied = (series/'narrative/personas/persona-template.md').read_text(encoding='utf-8')
        self.assertIn('### Contextual Voice Modes', copied)

    def test_example_seed_uses_updated_full_form(self):
        series = self.root/'example'
        code, report = invoke(narrative_init.main, '--out', str(series), '--series-id', 'demo',
                              '--title', 'Example', '--medium', 'prose', '--seed', 'example')
        self.assertEqual(code, 0, report)
        text = (series/'narrative/personas/c01.md').read_text(encoding='utf-8')
        self.assertIn('### Performance and Context Probes', text)
        self.assertIn('**relationship_conditions_and_audience**:', text)

    def test_routed_documents_are_linked(self):
        skill = (ROOT/'SKILL.md').read_text(encoding='utf-8')
        self.assertIn('(references/runtime/character-performance.md)', skill)
        method = (ROOT/'references/runtime/narrative-development.md').read_text(encoding='utf-8')
        self.assertIn('(character-performance.md)', method)
        performance = (ROOT/'references/performance-language-specification.md').read_text(encoding='utf-8')
        self.assertIn('(runtime/character-performance.md)', performance)
        route = (ROOT/'references/runtime/character-performance.md').read_text(encoding='utf-8')
        self.assertIn('(character-performance-probes.md)', route)

    def test_runtime_keeps_world_scope_and_approval_boundary(self):
        route = (ROOT/'references/runtime/character-performance.md').read_text(encoding='utf-8')
        for phrase in ('No cast size', 'No expressive signal is mandatory',
                       'no universal rule', 'not by a global ranking',
                       'do not invalidate JSON approval automatically',
                       'a new situation', 'single image'):
            self.assertIn(phrase.lower(), " ".join(route.lower().split()))

    def test_runtime_instruction_documents_are_english(self):
        from validate import check_english_content, non_english_characters
        self.assertEqual(check_english_content(ROOT), [])
        probes = (ROOT/'references/runtime/character-performance-probes.md').read_text(encoding='utf-8')
        self.assertEqual(non_english_characters(probes), {})

    def test_visual_route_has_no_fixed_cue_count_or_anatomy_inheritance(self):
        text = (ROOT/'references/performance-language-specification.md').read_text(encoding='utf-8')
        self.assertNotIn('Select three to six cues across at least two channels', text)
        self.assertIn('Only declared structures and capabilities activate a channel.', text)
        self.assertIn('not a dialogue-mode schema', text)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
