#!/usr/bin/env python3
"""Real browser round-trip of current artwork, candidate history and row controls."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHROMIUM = shutil.which('chromium') or shutil.which('google-chrome')
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


@unittest.skipUnless(CHROMIUM and sync_playwright, 'Optional browser check needs Playwright and a Chromium executable.')
class BrowserTests(unittest.TestCase):
    def test_readonly_artwork_roundtrip_and_single_row_actions(self):
        source = (ROOT / 'templates/character-sheet.template.html').read_text(encoding='utf-8')
        data = json.loads((ROOT / 'templates/character-sheet-data.blank.json').read_text(encoding='utf-8'))
        data['fields'].update({'identity.name':'Synthetic fixture', 'identity.species_domain':'declared structures'})
        artifact = {'artifact_id':'a'*64, 'image':{'path':'fixture/image.png','sha256':'b'*64,'width':32,'height':32,'media_type':'image/png'},
                    'provenance':{'kind':'generation','path':'fixture/provenance.json','sha256':'c'*64}}
        selection = {'artifact':artifact,'approval':{'decision_sha256':'d'*64,'decision_path':'fixture/decision.json',
                                                   'evidence_path':'fixture/evidence','evidence_sha256':'e'*64}}
        candidate = {**artifact,'artifact_id':'f'*64}
        data['slots']={'canon.primary':{'current':selection,'candidates':[candidate],'history':[selection],'fill_policy':'auto'}}
        js = r'''
const report={ok:false,checks:[]};
try {
 const fixture=FIXTURE;
 importData(fixture);
 const editor=document.querySelector('.slot[data-slot-id="canon.primary"]');
 if(![...editor.querySelectorAll('[data-slot-path]')].every(e=>e.readOnly))throw new Error('artwork fields are editable');
 report.checks.push('readonly artwork controls');
 const initialEdit=buildExportData();
 if(initialEdit.artifact_type!=='character-sheet-edit'||JSON.stringify(initialEdit.before)!==JSON.stringify(initialEdit.after)||'slots' in initialEdit.after)throw new Error('edit includes runtime data or creates unasked changes');
 report.checks.push('unchanged editor exports no runtime state or author changes');
 const policy=editor.querySelector('[data-fill-policy]');policy.value='keep';policy.dispatchEvent(new Event('change',{bubbles:true}));
 const changed=buildExportData();
 if(changed.after.fill_policies['canon.primary']!=='keep'||JSON.stringify(changed.after.fields)!==JSON.stringify(changed.before.fields)||JSON.stringify(changed.after.tables)!==JSON.stringify(changed.before.tables)||'slots' in changed.after)throw new Error('policy change modified other authoring');
 report.checks.push('policy-only change preserves all artwork');
 const table=document.getElementById('marks');
 const rows=()=>[...table.querySelectorAll('tr[data-row-id]')];const before=rows();
 document.querySelector('[data-add-row="marks"]').click();
 if(rows().length!==before.length+1)throw new Error('add did not create exactly one row');
 const added=rows().find(r=>!before.includes(r));added.querySelector('[data-remove-row]').click();
 if(rows().length!==before.length||before.some(r=>!rows().includes(r)))throw new Error('remove altered another row');
 report.checks.push('one row added and only selected row removed');
 report.ok=true;
} catch(e) {report.error=String(e.stack||e);}
const node=document.createElement('pre');node.id='cpb-browser-result';node.textContent=JSON.stringify(report);document.body.appendChild(node);
'''.replace('FIXTURE',json.dumps(data,ensure_ascii=True))
        # Injection exists only in this generated browser fixture, never in the shipped editor.
        source=source.replace('</body>','<script>'+js+'</script></body>')
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=CHROMIUM, headless=True, timeout=20000,
                args=['--disable-background-networking', '--no-first-run'])
            try:
                page_view = browser.new_page()
                # All content is the shipped standalone HTML; no service or external asset is needed.
                page_view.route('**/*', lambda route: route.abort())
                page_view.set_content(source, wait_until='domcontentloaded', timeout=15000)
                report = json.loads(page_view.locator('#cpb-browser-result').text_content(timeout=10000))
            finally:
                browser.close()
        self.assertTrue(report['ok'],report)
        self.assertEqual(len(report['checks']),4)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
