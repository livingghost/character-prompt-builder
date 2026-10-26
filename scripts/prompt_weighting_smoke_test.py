#!/usr/bin/env python3
"""Synthetic prompt syntax, clause inspection and recommendation-scope checks."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest

import prompt_weighting as w
import check_tag_prompt as checker
from model_contract import apply_prompt_recommendations, validate_recommendation_audit
from check_tag_prompt_smoke_test import DICTIONARY, DIALECTS


def terms(parsed, clause=0):
    return [tag['text'] for tag in parsed['clauses'][clause]['tags']]


class SyntaxTests(unittest.TestCase):
    def test_literal_never_infers_weighting(self):
        self.assertEqual(terms(w.parse('(grey fur)1.2, [yellow eyes]')), ['(grey fur)1.2', '[yellow eyes]'])
        self.assertEqual(w.selected({}), 'literal')

    def test_explicit_native_selection(self):
        for syntax in ('sdEmbeds','compel'):
            self.assertEqual(w.selected({'promptWeighting':syntax}),syntax)
        for value in (None,True,'COMPEL','literal','automatic'):
            with self.subTest(value=value),self.assertRaises(ValueError):w.selected({'promptWeighting':value})

    def test_plus_minus_word_weights(self):
        value=w.parse('cat++, dog--','compel')
        self.assertEqual(terms(value),['cat','dog'])
        self.assertAlmostEqual(value['clauses'][0]['tags'][0]['weights'][0],1.1**2)
        self.assertAlmostEqual(value['clauses'][0]['tags'][1]['weights'][0],.9**2)

    def test_numeric_group_and_unicode(self):
        text='(蒼い瞳)1.25, (long hair)0.8'
        value=w.parse(text,'compel')
        self.assertEqual(terms(value),['蒼い瞳','long hair'])
        for tag in value['clauses'][0]['tags']:
            self.assertIn(tag['text'],text[tag['range']['start']:tag['range']['end']])

    def test_group_commas_are_not_operators(self):
        value=w.parse('(grey fur, yellow eyes)1.3','compel')
        self.assertEqual(terms(value),['grey fur','yellow eyes'])
        self.assertEqual([t['weights'] for t in value['clauses'][0]['tags']],[[1.3],[1.3]])

    def test_nested_weights_multiply(self):
        value=w.parse('(grey fur, (yellow eyes)1.3)++','compel')
        self.assertAlmostEqual(value['clauses'][0]['tags'][0]['weights'][0],1.21)
        self.assertAlmostEqual(value['clauses'][0]['tags'][1]['weights'][0],1.573)

    def test_unweighted_compel_parentheses_do_not_add_sd_emphasis(self):
        self.assertEqual(w.parse('(grey fur)','compel')['clauses'][0]['tags'][0]['weights'],[1.0])
        self.assertEqual(w.parse('(grey fur)','sdEmbeds')['clauses'][0]['tags'][0]['weights'],[1.1])

    def test_compel_deemphasis_is_not_reciprocal_sd_emphasis(self):
        a=w.parse('(grey fur)-','compel')['clauses'][0]['tags'][0]['weights'][0]
        b=w.parse('[grey fur]','sdEmbeds')['clauses'][0]['tags'][0]['weights'][0]
        self.assertEqual(a,.9);self.assertNotEqual(a,b)

    def test_quotes_and_escaped_parentheses(self):
        self.assertEqual(terms(w.parse(r'person \(fiction\), "grey fur"+','compel')),['person (fiction)','grey fur'])
        self.assertEqual(terms(w.parse(r'person \(fiction\), plain-text','sdEmbeds')),['person (fiction)','plain-text'])

    def test_escaped_comma_does_not_split_a_dictionary_term(self):
        self.assertEqual(terms(w.parse(r'one\, two, three','compel')),['one, two','three'])

    def test_signs_inside_words_are_literal(self):
        self.assertEqual(terms(w.parse('close-up, x-ray, upper-body','compel')),['close-up','x-ray','upper-body'])
        self.assertEqual(terms(w.parse(r'C\+\+, A\-','compel')),['C++','A-'])

    def test_blend_preserves_clauses_and_raw_coefficients(self):
        value=w.parse('("solo, grey fur", "solo, yellow eyes").blend(1, 0.8)','compel')
        self.assertEqual((value['operator'],value['normalize']),('blend',True))
        self.assertEqual([row['weight'] for row in value['clauses']],[1,.8])
        self.assertEqual(terms(value,0),['solo','grey fur']);self.assertEqual(terms(value,1),['solo','yellow eyes'])

    def test_and_default_and_explicit_coefficients(self):
        for suffix,weights in [('.and()',[1,1]),('.and(1,0.5)',[1,.5]),('.add(1,0.5)',[1,.5])]:
            value=w.parse('("solo", "grey fur")'+suffix,'compel')
            self.assertEqual(value['operator'],'and');self.assertEqual([row['weight'] for row in value['clauses']],weights)

    def test_explicit_attend(self):
        value=w.parse('grey.attend(1.2) fur, (yellow eyes).attend(++)','compel')
        self.assertEqual(terms(value),['grey fur','yellow eyes'])
        self.assertAlmostEqual(value['clauses'][0]['tags'][1]['weights'][0],1.21)

    def test_signed_blend_and_no_normalize(self):
        value=w.parse('("a", "b").blend(-1, 2)','compel')
        self.assertEqual([row['weight'] for row in value['clauses']],[-1,2])
        value=w.parse('("a", "b").blend(0, 0, no_normalize)','compel')
        self.assertFalse(value['normalize'])

    def test_zero_sum_normalized_blend_is_rejected(self):
        for text in ['("a", "b").blend(0,0)','("a", "b").blend(-1,1)']:
            with self.subTest(text=text),self.assertRaises(w.SyntaxError):w.parse(text,'compel')

    def test_compound_arity_checked(self):
        for text in ['("a", "b").blend(1)','("a", "b").and(1,2,3)']:
            with self.subTest(text=text),self.assertRaises(w.SyntaxError):w.parse(text,'compel')

    def test_compound_cannot_ignore_trailing_prompt(self):
        for text in ['("a", "b").and() appended', 'prefix ("a", "b").blend(1,1)']:
            with self.subTest(text=text),self.assertRaises(w.SyntaxError):w.parse(text,'compel')

    def test_empty_conditioning_is_distinct_from_missing_clause(self):
        self.assertEqual(terms(w.parse('("", "grey fur").blend(1,1)','compel'),0),[])
        with self.assertRaises(w.SyntaxError):w.parse('("a",).blend()','compel')

    def test_sdembeds_suffix_and_escaped_colon(self):
        result=w.parse(r'(grey fur:1.3), [yellow eyes], clock\:12','sdEmbeds')
        self.assertEqual(terms(result),['grey fur','yellow eyes','clock:12'])
        self.assertEqual(result['clauses'][0]['tags'][0]['weights'],[1.3])

    def test_mixed_syntax_is_not_translated(self):
        for text,syntax in [('(grey fur:1.2)','compel'),('[grey fur]','compel'),('(grey fur)1.2','sdEmbeds'),('("a", "b").and()','sdEmbeds')]:
            with self.subTest(text=text),self.assertRaises(w.SyntaxError):w.parse(text,syntax)

    def test_sdembeds_break_is_not_a_compel_operator(self):
        a=w.parse('solo BREAK grey fur','sdEmbeds');b=w.parse('solo BREAK grey fur','compel')
        self.assertEqual([t['chunk'] for t in a['clauses'][0]['tags']],[0,1])
        self.assertEqual(terms(b),['solo BREAK grey fur'])

    def test_malformed_and_unknown_operators_are_located(self):
        for text in ['(a','"a','(a]','a\\','a.swap(b)','useLora(test)','a.unknown(1)','(a)++--']:
            result=w.inspect_pair(text,'','compel')
            self.assertEqual(len(result['findings']),1,text)
            self.assertEqual(result['findings'][0]['channel'],'positive')
            self.assertIn('range',result['findings'][0])

    def test_nonfinite_weights_do_not_escape_json(self):
        for text in ['(a)1e999','("a", "b").blend(NaN,1)','(a).attend(inf)']:
            with self.subTest(text=text),self.assertRaises(w.SyntaxError):w.parse(text,'compel')

    def test_nesting_bound_is_explicit(self):
        with self.assertRaisesRegex(w.SyntaxError,'depth'):w.parse('('*70+'a'+')'*70,'compel')

    def test_top_level_comma_slices_preserve_nested_text(self):
        text='quality, (grey fur, yellow eyes)1.2, "a,b"'
        self.assertEqual([text[a:b].strip() for a,b in w.split_top_level(text)],['quality','(grey fur, yellow eyes)1.2','"a,b"'])

    def test_normalization_overflow_is_a_bounded_diagnostic(self):
        findings = w.inspect_pair('("a", "b").blend(1e308, 1e308)', '', 'compel')['findings']
        self.assertEqual(findings[0]['check'], 'blend normalization')

    def test_compound_multiword_operand_needs_explicit_group(self):
        with self.assertRaisesRegex(ValueError, 'quote or parenthesize'):
            w.parse('(blue eyes, green eyes).and()', 'compel')
        self.assertEqual(w.parse('((blue eyes), (green eyes)).and()', 'compel')['operator'], 'and')


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        path=Path(self.tmp.name)/'v.json';path.write_text(json.dumps(DICTIONARY), encoding='utf-8')
        self.vocabulary=checker.load_vocabulary(path);self.dialect=DIALECTS['dialects'][0]

    def report(self,text,negative='',syntax='compel'):
        return checker.inspect(text,negative,self.vocabulary,None,self.dialect,syntax=syntax)

    def test_shared_terms_across_and_are_not_duplicates(self):
        report=self.report('("solo, grey fur", "solo, yellow eyes").and()')
        self.assertFalse(any(x['severity']=='problem' for x in report['findings']))
        self.assertEqual(len(report['channels']['positive']['clauses']),2)

    def test_opposed_blend_terms_are_separate_not_a_false_contradiction(self):
        report=self.report('("close-up", "full body").blend(1,1)')
        self.assertFalse(any(x['severity']=='problem' for x in report['findings']))
        self.assertTrue(any(x['check']=='conditioning clauses' for x in report['findings']))

    def test_repeated_terms_inside_one_clause_preserve_authored_weights(self):
        report=self.report('("grey fur+, grey fur", "yellow eyes").and()')
        tags=report['channels']['positive']['clauses'][0]['tags']
        self.assertEqual([tag['text'] for tag in tags], ['grey fur', 'grey fur'])
        self.assertEqual([tag['weights'] for tag in tags], [[1.0, 1.1], [1.0]])
        self.assertFalse(any(x['severity']=='problem' for x in report['findings']))

    def test_weighted_group_is_not_split_into_syntax_tokens(self):
        self.assertEqual(self.report('(grey fur, yellow eyes)1.2')['findings'],[])

    def test_negative_compel_is_inspected_with_same_grammar(self):
        report=self.report('grey fur','(grey fur)0.5')
        self.assertEqual(report['findings'], [])
        self.assertEqual(report['channels']['negative']['clauses'][0]['tags'][0]['weights'], [0.5])
        error=self.report('grey fur','(yellow eyes:1.2)')['findings'][0]
        self.assertEqual(error['channel'],'negative')

    def test_zero_weight_does_not_assert_active_conflict(self):
        report=self.report('(close-up)0, full body')
        self.assertFalse(any(x['severity']=='problem' for x in report['findings']))

    def test_literal_brackets_remain_dictionary_text(self):
        report=self.report('(grey fur)',syntax='literal')
        self.assertEqual(report['unmatched_terms'], [{'channel':'positive','clause':0,'term':'(grey fur)'}])

    def test_non_tag_models_still_get_grammar_validation(self):
        result=checker.inspect('("a", "b").blend(1)','',None,None,syntax='compel')
        self.assertEqual(result['findings'][0]['check'],'clause weights')

    def test_family_guidance_is_complete_for_compound_and_single_prompts(self):
        result=self.report('("general, solo", "explicit, solo").blend(1,1)')
        single=self.report('general, explicit, solo')
        self.assertEqual(result['dialect_guidance'], self.dialect)
        self.assertEqual(single['dialect_guidance'], self.dialect)
        self.assertEqual(single['findings'], [])

    def test_literal_break_is_a_visible_note(self):
        self.assertTrue(any(x['check']=='literal BREAK' for x in self.report('solo BREAK grey fur')['findings']))

    def test_explicit_attend_can_follow_whitespace_but_postfix_numbers_cannot(self):
        data = w.parse('grey .attend(1.2) fur, (yellow eyes) .attend(-)', 'compel')
        self.assertIn(1.2, data['clauses'][0]['tags'][0]['weights'])
        self.assertEqual(data['clauses'][0]['tags'][1]['weights'], [0.9])
        plain = w.parse('(grey fur) 1.2', 'compel')
        self.assertEqual(terms(plain), ['grey fur 1.2'])
        self.assertEqual(plain['weights'], [])

    def test_signed_blend_is_reported_without_claiming_simple_positive_negative_conflict(self):
        result = self.report('("grey fur", "yellow eyes").blend(-1,2)', 'grey fur')
        self.assertFalse(any(row['severity'] == 'problem' for row in result['findings']), result['findings'])
        self.assertTrue(any(row['check'] == 'signed conditioning' for row in result['findings']))


class RecommendationTests(unittest.TestCase):
    def test_compound_authored_bytes_are_unchanged_and_advice_is_reported(self):
        text='  ("solo, grey fur", "solo, yellow eyes").and()\n'
        for mode in ('tag-list','prefix'):
            p,n,a=apply_prompt_recommendations({'recommendation_merge_mode':mode,'recommended_positive_prompt':'masterpiece'},prompt=text,negative_prompt='',weighting='compel')
            self.assertEqual(p,text);self.assertFalse(a['positive']['applied']);self.assertIn('clauses-preserved',a['positive']['reason'])
            validate_recommendation_audit(a['positive'],p,weighting='compel')

    def test_compound_recommendation_is_not_prefixed_into_plain_prompt(self):
        p,n,a=apply_prompt_recommendations({'recommendation_merge_mode':'tag-list','recommended_positive_prompt':'("masterpiece","best quality").and()'},prompt='solo',negative_prompt='',weighting='compel')
        self.assertEqual(p,'solo');self.assertFalse(a['positive']['applied'])

    def test_simple_weighted_group_is_preserved_when_recommendation_is_added(self):
        text=' (grey fur, yellow eyes)1.2 '
        p,n,a=apply_prompt_recommendations({'recommendation_merge_mode':'tag-list','recommended_positive_prompt':'masterpiece'},prompt=text,negative_prompt='',weighting='compel')
        self.assertTrue(p.endswith(text));self.assertEqual(terms(w.parse(p,'compel')),['masterpiece','grey fur','yellow eyes'])
        self.assertEqual(a['positive']['segments'][-1]['text'],text)

    def test_model_recommendation_never_deduplicates_authored_group_contents(self):
        text='(grey fur, grey fur)1.2'
        p,n,a=apply_prompt_recommendations({'recommendation_merge_mode':'tag-list','recommended_positive_prompt':'best quality'},prompt=text,negative_prompt='',weighting='compel')
        self.assertIn(text,p)

    def test_recommendation_audit_is_bound_to_weighting_selection(self):
        p,n,a=apply_prompt_recommendations({'recommendation_merge_mode':'advisory-only'},prompt='grey fur+',negative_prompt='',weighting='compel')
        with self.assertRaises(ValueError):validate_recommendation_audit(a['positive'],p,weighting='sdEmbeds')

    def test_plain_negative_recommendations_are_not_lost_when_positive_is_compound(self):
        p,n,a=apply_prompt_recommendations({'recommendation_merge_mode':'tag-list','recommended_positive_prompt':'quality','recommended_negative_prompt':'blur'},prompt='("a", "b").and()',negative_prompt='noise',weighting='compel')
        self.assertEqual(n,'blur, noise');self.assertTrue(a['negative']['applied']);self.assertFalse(a['positive']['applied'])


class ExampleTests(unittest.TestCase):
    def test_committed_example_matches_a_fresh_non_network_projection(self):
        import subprocess, sys
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, str(root/'examples/prompt-weighting/build_example.py'), '--check'],
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(json.loads(result.stdout)['network'])


class CrossSyntaxRecommendationTests(unittest.TestCase):
    def test_sdembeds_recommendation_is_advice_not_conversion_in_compel(self):
        from model_contract import apply_prompt_recommendations, validate_recommendation_audit
        prompt, negative, audit = apply_prompt_recommendations(
            {'recommendation_merge_mode': 'tag-list', 'recommended_negative_prompt': '(lettering:1.2)'},
            prompt='grey fur+', negative_prompt='watermark+', weighting='compel')
        self.assertEqual((prompt, negative), ('grey fur+', 'watermark+'))
        self.assertFalse(audit['negative']['applied'])
        self.assertEqual(audit['negative']['recommended_text'], '(lettering:1.2)')
        self.assertEqual(audit['negative']['reason'], 'recommendation-syntax-mismatch; author supplies matching grammar')
        validate_recommendation_audit(audit['negative'], negative, weighting='compel')

    def test_optional_recommendation_never_hides_invalid_authored_expression(self):
        from model_contract import apply_prompt_recommendations
        with self.assertRaises(ValueError):
            apply_prompt_recommendations(
                {'recommendation_merge_mode': 'tag-list', 'recommended_negative_prompt': '(lettering:1.2)'},
                prompt='grey fur+', negative_prompt='(watermark:1.2)', weighting='compel')


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
