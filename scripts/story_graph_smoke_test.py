#!/usr/bin/env python3
"""Recorded edges, bounded graph projection and fixed story-column layout."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import execution_contract as c
import story_timeline as timeline
from story_flow_fixtures import graph_setup, setup as story_setup
from story_timeline_fixtures import event, write_events

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which('node')

# A fixed set of named algorithm checks; the expressions are part of the test,
# not input assembled per call.
CHECKS = {
    'edge-endpoints': "return ix.edges.map(e=>({kind:e.kind,from:ix.nodes.get(e.from).event_id,to:ix.nodes.get(e.to).event_id}));",
    'layout-points': "const p=storyGraph.project(ix,ix.nodes.keys()),g=storyGraph.layout(p);return [...g.points].map(([k,p])=>({id:ix.nodes.get(p.group.keys[0]).event_id,x:p.x,y:p.y,w:p.w,h:p.h}));",
    'projection-summary': "const p=storyGraph.project(ix,ix.nodes.keys());return {edges:p.edges.length,nodes:p.groups.length};",
    'filtered-projection': "const p=storyGraph.project(ix,['N00000','N00003']);return {hidden:p.groups.filter(g=>!g.shown.length).map(g=>g.keys),edges:p.edges.map(e=>[e.edges[0].from,e.edges[0].to])};",
    'cycle-cuts': "return {edges:ix.edges.length,cuts:ix.edges.filter(e=>e.cut).length};",
    'condensation': "const p=storyGraph.project(ix,ix.nodes.keys());return {groups:p.groups.length,members:p.groups[0].keys.length,condensed:p.condensed};",
    'windowing': "const a=storyGraph.project(ix,ix.nodes.keys()),b=storyGraph.project(ix,ix.nodes.keys(),{page:2});return {first:a.groups.length,pages:a.pages,last:b.groups.length,lastOrder:b.groups.at(-1).order};",
    'unplaced': "const p=storyGraph.project(ix,ix.nodes.keys());return {groups:p.groups.length,unplaced:p.unplaced};",
    'timeline-groups': "const p=storyGraph.project(ix,ix.nodes.keys());return p.groups.map(g=>[g.timeline,g.keys.length]);",
    'window-boundary': "const p=storyGraph.project(ix,ix.nodes.keys());return {edges:p.edges.length,boundary:p.boundary.length};",
    'edge-bounds': "const p=storyGraph.project(ix,ix.nodes.keys());return {drawn:p.edges.length,retained:p.relations.length,omitted:p.omittedEdgeGroups};",
    'layout-purity': "const before=JSON.stringify(input);storyGraph.layout(storyGraph.project(ix,ix.nodes.keys()));return before===JSON.stringify(input);",
    'invalid-limit-rejected': "try{storyGraph.project(ix,ix.nodes.keys(),{limit:0});return false;}catch(e){return true;}",
    'sparse-orders': "const g=storyGraph.layout(storyGraph.project(ix,ix.nodes.keys()));return {orders:g.tracks[0].layers.map(x=>x.order),width:g.width};",
}


def evaluate(source: dict, check: str):
    expression = CHECKS[check]
    script = (ROOT / 'templates/story-graph.js').read_text(encoding='utf-8')
    script += "\nconst input=JSON.parse(require('fs').readFileSync(0,'utf8'));const ix=storyGraph.index(input);\n"
    script += "console.log(JSON.stringify((()=>{" + expression + "})()));"
    result = subprocess.run([NODE, '-e', script], input=json.dumps(source), text=True,
                            capture_output=True, encoding='utf-8', timeout=30)
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def synthetic_nodes(count: int, *, same_order: bool = False) -> dict:
    return {'nodes': [{'key': f'N{i:05}', 'title': f'Synthetic record {i}', 'timeline_id': 'main',
                      'start_order': 1 if same_order else i, 'kind': 'event'} for i in range(count)],
            'relations': [], 'state_paths': []}


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'studio'; self.fixture = graph_setup(self.root)

    def model(self):
        return timeline.build_model(self.root, self.root / timeline.OUTPUT)[0]

    def test_branch_fixture_has_two_resolved_cause_links_and_one_revision(self):
        data = self.model(); self.assertTrue(data['ok'])
        relations = data['flow']['relations']
        self.assertEqual([r['kind'] for r in relations].count('cause'), 2)
        self.assertEqual([r['kind'] for r in relations].count('revision'), 1)
        events = {n['key']: n['event_id'] for n in data['flow']['nodes']}
        self.assertEqual({(events[r['source']], events[r['target']]) for r in relations if r['kind']=='cause'}, {('A','B'),('A','C')})

    def test_generated_html_contains_inline_graph_assets_and_preserves_input(self):
        original = (self.root / 'state/events.jsonl').read_bytes()
        model = self.model(); html = timeline.render_html(model, '2000-01-01T00:00:00Z')
        for text in ['id="mode-graph"', 'id="graph-canvas"', 'const storyGraph', '.graph-edge.revision']:
            self.assertIn(text, html)
        self.assertNotIn('/*CPB_GRAPH_', html); self.assertNotIn('<script src=', html)
        self.assertEqual((self.root / 'state/events.jsonl').read_bytes(), original)

    def test_graph_is_the_opening_mode_with_all_modes_reachable_by_hash(self):
        html = timeline.render_html(self.model(), '2000-01-01T00:00:00Z')
        self.assertIn('<button id="mode-graph" aria-pressed="true">', html)
        self.assertLess(html.index('id="mode-graph"'), html.index('id="mode-flow"'))
        self.assertLess(html.index('id="mode-flow"'), html.index('id="mode-axis"'))
        self.assertIn("['#flow','#axis','#graph'].includes(location.hash)", html)
        self.assertIn("mode='graph'", html)
        self.assertIn('<section id="graph-panel" class="graph-panel" aria-label="Story relationship graph">', html)
        self.assertIn('id="flow-list-column" hidden', html)

    def test_graph_assets_participate_in_projection_identity(self):
        first = self.model()['renderer_sha256']
        from unittest.mock import patch
        original = c.sha256_file
        def changed(path):
            return '0'*64 if Path(path).name == 'story-graph.js' else original(path)
        with patch.object(c, 'sha256_file', side_effect=changed):
            second = self.model()['renderer_sha256']
        self.assertNotEqual(first, second)

    def test_declared_cause_cycle_stays_recorded_for_layout_annotation(self):
        rows = self.fixture['events']; rows[0]['cause'] = {'type':'event','reference':'C'}
        write_events(self.root, rows); data = self.model()
        self.assertEqual(sum(r['kind']=='cause' for r in data['flow']['relations']), 3)
        self.assertTrue(data['ok'])  # Graph cycles are not a new resolver verdict.


@unittest.skipUnless(NODE, 'Graph algorithm checks need Node.js; runtime HTML has no Node dependency.')
class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name) / 'studio'; graph_setup(root)
        self.source = timeline.build_model(root, root/timeline.OUTPUT)[0]['flow']

    def test_revision_arrow_runs_from_new_record_to_old(self):
        edges = evaluate(self.source, 'edge-endpoints')
        self.assertIn({'kind':'revision','from':'D','to':'B'}, edges)
        self.assertIn({'kind':'cause','from':'A','to':'B'}, edges)

    def test_branch_and_same_order_peers_are_placed_without_overlap(self):
        rows = evaluate(self.source, 'layout-points')
        d = {r['id']:r for r in rows}
        self.assertEqual(d['B']['x'],d['C']['x']); self.assertGreater(abs(d['B']['y']-d['C']['y']), d['B']['h'])
        self.assertLess(d['A']['x'],d['B']['x']); self.assertLess(d['B']['x'],d['D']['x'])

    def test_empty_relations_do_not_invent_a_chain_from_order_or_state_path(self):
        source = synthetic_nodes(4); source['state_paths']=[{'event_keys':[n['key'] for n in source['nodes']]}]
        result=evaluate(source,'projection-summary')
        self.assertEqual(result,{'edges':0,'nodes':4})

    def test_filter_keeps_exact_edges_through_hidden_placeholders(self):
        source=synthetic_nodes(4);source['relations']=[{'kind':'cause','source':source['nodes'][i]['key'],'target':source['nodes'][i+1]['key']} for i in range(3)]
        result=evaluate(source,'filtered-projection')
        self.assertEqual(result['hidden'],[['N00001'],['N00002']]);self.assertEqual(len(result['edges']),3)
        self.assertNotIn(['N00000','N00003'],result['edges'])

    def test_cycle_cut_is_finite_and_keeps_every_original_edge(self):
        source=synthetic_nodes(3);source['relations']=[{'kind':'cause','source':f'N{i:05}','target':f'N{(i+1)%3:05}'} for i in range(3)]
        result=evaluate(source,'cycle-cuts')
        self.assertEqual(result,{'edges':3,'cuts':1})

    def test_long_cause_chain_uses_no_recursive_walk(self):
        source=synthetic_nodes(6000);source['relations']=[{'kind':'cause','source':f'N{i:05}','target':f'N{i+1:05}'} for i in range(5999)]
        self.assertEqual(evaluate(source,'cycle-cuts'),{'edges':5999,'cuts':0})

    def test_one_large_equal_position_group_is_not_truncated(self):
        result=evaluate(synthetic_nodes(501,same_order=True),'condensation')
        self.assertEqual(result,{'groups':1,'members':501,'condensed':True})

    def test_many_distinct_positions_use_windows_not_false_time_merging(self):
        result=evaluate(synthetic_nodes(501),'windowing')
        self.assertEqual(result,{'first':200,'pages':3,'last':101,'lastOrder':500})

    def test_unplaced_nodes_stay_outside_the_story_axis(self):
        source=synthetic_nodes(3);source['nodes'][1]['start_order']=None;source['nodes'][2]['timeline_id']=None
        result=evaluate(source,'unplaced')
        self.assertEqual(result,{'groups':1,'unplaced':['N00002','N00001']})

    def test_separate_timelines_do_not_share_a_position_group(self):
        source=synthetic_nodes(201,same_order=True);source['nodes'][-1]['timeline_id']='other'
        result=evaluate(source,'timeline-groups')
        self.assertEqual(result,[['main',200],['other',1]])

    def test_links_across_window_are_reported(self):
        source=synthetic_nodes(250);source['relations']=[{'kind':'cause','source':'N00000','target':'N00249'}]
        self.assertEqual(evaluate(source,'window-boundary'),{'edges':0,'boundary':1})

    def test_dense_graph_bounds_drawn_edges_but_retains_relationships(self):
        source=synthetic_nodes(200);source['relations']=[{'kind':'cause','source':f'N{i:05}','target':f'N{j:05}'} for i in range(30) for j in range(150,200)]
        result=evaluate(source,'edge-bounds')
        self.assertEqual(result,{'drawn':800,'retained':1500,'omitted':700})

    def test_source_data_is_not_modified_by_layout(self):
        self.assertTrue(evaluate(self.source,'layout-purity'))

    def test_invalid_window_size_is_rejected(self):
        self.assertTrue(evaluate(self.source,'invalid-limit-rejected'))

    def test_negative_and_sparse_orders_remain_exact_without_large_numeric_spacing(self):
        source=synthetic_nodes(3)
        for n,order in zip(source['nodes'],[-100,0,1000000000]):n['start_order']=order
        result=evaluate(source,'sparse-orders')
        self.assertEqual(result['orders'],[-100,0,1000000000]);self.assertLess(result['width'],2000)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
