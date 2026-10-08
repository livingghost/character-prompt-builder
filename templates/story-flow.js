
// A reading surface, not a second resolver or an authoring/approval tool.
const flow=(()=>{
const source=data.flow, nodes=source.nodes, nodeMap=new Map(nodes.map(n=>[n.key,n]));
const eventMap=new Map(cards.map(c=>[c.anchor,c]));
const eventNodes=new Map();for(const n of nodes)if(n.kind==='event'&&!eventNodes.has(n.event_id))eventNodes.set(n.event_id,n.key);
const scenes=new Map(nodes.filter(n=>n.kind==='scene').map(n=>[n.key,n]));
const relationIndex=new Map();
for(const r of source.relations)for(const key of [r.source,r.target]){if(!relationIndex.has(key))relationIndex.set(key,[]);relationIndex.get(key).push(r);}
const flowIssues=new Map();
for(const d of source.diagnostics)if(d.flow_node){if(!flowIssues.has(d.flow_node))flowIssues.set(d.flow_node,[]);flowIssues.get(d.flow_node).push(d);}
let selected=null,pinned=null,flowPage=0,threadLimit=30,visibleNodes=[],traceView=null,traceIndex=new Map(),mode='graph',graph=null;
const size=24, names=source.names;
const person=id=>Object.prototype.hasOwnProperty.call(names,id)?names[id]:String(id);
const record=n=>n.kind==='event'?(eventMap.get(n.event_anchor)?.event||{}):n.scene_record||n.process_record||n.chapter_record||{};
const strings=x=>asArray(x).filter(v=>typeof v==='string');
const objects=x=>asArray(x).filter(v=>v&&typeof v==='object'&&!Array.isArray(v));
const plain=x=>x===undefined?'not recorded':typeof x==='string'?x:JSON.stringify(x);
const textSearch=new Map(nodes.map(n=>[n.key,JSON.stringify({node:n,record:record(n),names:n.participants.map(person),
linked_events:n.event_keys.map(key=>record(nodeMap.get(key)))}).toLowerCase()]));
const label=n=>n.kind==='scene'?'Scene '+n.scene_id:n.kind==='event'?'Event '+n.event_id:n.kind==='process'?'Process '+n.process_id:'Chapter '+n.chapter_id;
const chapterMap=new Map(objects(source.narrative?.chapters).filter(c=>typeof c.id==='string').map(c=>[c.id,c]));
function issueList(n){return [...(flowIssues.get(n.key)||[]),...(n.kind==='event'?(diagnosticIndex.get(n.event_id)||[]):n.event_keys.flatMap(k=>diagnosticIndex.get(nodeMap.get(k)?.event_id)||[]))];}
function isRevised(n){return n.kind==='event'&&['revised-at-selected-order','recorded-superseded'].includes(stateOf(eventMap.get(n.event_anchor)));}
function matches(n){
 const t=$('timeline-filter').value,e=$('entity-filter').value,s=$('scene-filter').value,q=$('search').value.toLowerCase(),who=$('participant-filter').value;
 return (!t||n.timeline_id===t)&&(!e||n.entity_types.includes(e)||n.event_keys.some(k=>nodeMap.get(k).entity_types.includes(e)))&&(!s||n.scene_context_id===s)&&(!who||n.participants.includes(who)||n.event_keys.some(k=>nodeMap.get(k).participants.includes(who)))&&(!q||textSearch.get(n.key).includes(q))&&($('revisions').checked||!isRevised(n))&&(!$('issues-only').checked||issueList(n).length);
}
function raw(parent,name,value){const d=el('details',undefined,'flow-raw');d.append(el('summary',name),el('pre',json(value)));parent.append(d);}
function para(parent,value,cls){if(value!==undefined&&value!==null&&value!=='')parent.append(el('p',plain(value),cls));}
function heading(parent,text){parent.append(el('h4',text));}
function authoredList(parent,values,getText){const list=el('ol');for(const value of values)list.append(el('li',getText(value)));parent.append(list);}
function briefChanges(n){
 const r=record(n);
 if(n.kind==='scene')return [...objects(r.state_changes).map(c=>plain(c.target)+': '+plain(c.change)),
  ...objects(r.relationship_delta).map(c=>asArray(c.between).map(person).join(' / ')+': '+plain(c.change))];
 if(n.kind==='event')return objects(r.changes).map(c=>person(c.entity_id)+' | '+c.path+' | '+c.operation+(Object.hasOwn(c,'value')?' '+plain(c.value):''));
 if(n.kind==='process')return objects(r.milestones).map(m=>'Offset '+m.offset+': '+plain(m.state));
 return [];
}
function position(n){if(n.timeline_id===null||n.start_order===null)return 'Story coordinate not recorded';return n.timeline_id+' / order '+n.start_order+(n.end_order!=null&&n.end_order!==n.start_order?' to '+n.end_order:'')+(n.scene_context_id?' / '+n.scene_context_id:'');}
function approval(n){
 const r=record(n);
 if(n.kind==='scene')return !n.report?.ok?'invalid draft':n.messages.some(s=>s.includes('different narrative revision'))?'source revision changed':n.report.approved?'scene approval recorded':'scene not approved';
 return r.canon_status||r.status||'declared chapter';
}
function relatedButton(parent,key,prefix){const other=nodeMap.get(key);if(!other)return;const b=el('button',prefix+other.title,'flow-relation');b.addEventListener('click',()=>select(key,true));parent.append(b);}
function drawCard(n){
 const a=el('article',undefined,'flow-card');a.dataset.nodeKey=n.key;if(n.key===selected)a.classList.add('selected');if(n.key===pinned)a.classList.add('pinned');
 const r=record(n);a.append(el('div',label(n),'flow-kicker'),badge(approval(n)));
 if(n.kind==='event')a.append(badge(stateOf(eventMap.get(n.event_anchor))));
 const title=el('button',n.title,'flow-title');title.type='button';title.addEventListener('click',()=>select(n.key));a.append(title);
 para(a,n.participants.length?n.participants.map(person).join(' / '):'No participants declared','flow-cast');
 if(n.kind==='scene'){
  para(a,[r.setting?.location,r.setting?.where,r.setting?.time_of_day].filter(Boolean).join(' | '),'meta');
  const preview=el('div',undefined,'flow-snippet');for(const beat of objects(r.beats).slice(0,2))para(preview,beat.beat);
  if(objects(r.beats).length>2)para(preview,(objects(r.beats).length-2)+' more recorded beats; open the scene to read all.','meta');
  a.append(preview);
 }else if(n.kind==='event'){
  const notes=strings(r.notes);for(const note of notes.slice(1,3))para(a,note);
  if(!notes.length)para(a,'No narrative description recorded. This heading quotes the cause/reference, not an inferred action.','meta');
 }else if(n.kind==='chapter'){for(const note of strings(r.depicts).slice(0,2))para(a,note);}
 else para(a,'Declared milestone process. Actual application follows lifecycle events in the shared resolver.','meta');
 const consequences=briefChanges(n);
 if(consequences.length){const box=el('div',undefined,'flow-outcome');box.append(el('strong',n.kind==='process'?'Declared milestones':n.kind==='scene'?'What this scene leaves behind':'Recorded changes'));
 for(const value of consequences.slice(0,2))para(box,value);
 if(consequences.length>2)para(box,(consequences.length-2)+' more recorded changes.','meta');a.append(box);}
 if(n.messages.length)para(a,n.messages[0],'warning');
 const issues=issueList(n);if(issues.length)para(a,issues.length+' source/structural diagnostic(s); not an automatic story verdict.','warning');
 const links=relationIndex.get(n.key)||[];if(links.length)para(a,links.length+' recorded cause/revision link(s). Open to trace.','meta');
 const actions=el('div',undefined,'flow-actions'),open=el('button','Read scene / event'),pin=el('button',n.key===pinned?'Unpin comparison':'Pin for comparison');
 open.addEventListener('click',()=>select(n.key));pin.addEventListener('click',()=>{pinned=pinned===n.key?null:n.key;if(!selected)selected=n.key;render();});
 actions.append(open,pin);a.append(actions);return a;
}
function renderTracks(){
 const order=$('flow-order').value,tracks=order==='presentation'?source.presentation_tracks:source.story_tracks;
 $('flow-board').replaceChildren();visibleNodes=[];
 const prepared=tracks.map(track=>({...track,groups:track.groups.map((g,index)=>({...g,originalIndex:index,allCount:g.keys.length,keys:g.keys.filter(k=>matches(nodeMap.get(k)))})).filter(g=>g.keys.length)}));
 for(const track of prepared)for(const group of track.groups)visibleNodes.push(...group.keys);
 flowPage=Math.max(0,Math.min(flowPage,Math.ceil(visibleNodes.length/size)-1));
 const pageKeys=new Set(visibleNodes.slice(flowPage*size,(flowPage+1)*size));
 for(const track of prepared){
  const groups=track.groups.map(g=>({...g,keys:g.keys.filter(k=>pageKeys.has(k))})).filter(g=>g.keys.length);if(!groups.length)continue;
  const section=el('section',undefined,'flow-track');section.dataset.track=track.key;
  const head=el('div',undefined,'flow-track-head');head.append(el('div',track.kind==='presentation'?'Declared presentation order':track.kind==='story'?'Story order (not causal arrows)':'Unplaced source records','flow-kicker'),el('h3',track.label));
  if(track.record)for(const line of strings(track.record.depicts))para(head,line);
  if(track.kind==='unplaced')para(head,'No order is inferred between these records.','meta');section.append(head);
  let last=null;
  for(const group of groups){
   const gap=last===null?group.originalIndex:group.originalIndex-last-1;
   if(gap>0)para(section,gap+' earlier/intervening recorded position(s) outside this page or these filters.','flow-gap');
   const step=el('div',undefined,'flow-step');step.append(el('div',group.position===null?'No declared relative position':(track.kind==='presentation'?'Scene position ':'Story order ')+group.position+(group.allCount>1?' | '+group.allCount+' records at this position; no within-position causal order asserted':''),'flow-position'));
   if(group.keys.length<group.allCount)para(step,(group.allCount-group.keys.length)+' peer record(s) not shown by this page/filter.','meta');
   const box=el('div',undefined,'flow-cards');for(const key of group.keys)box.append(drawCard(nodeMap.get(key)));step.append(box);section.append(step);last=group.originalIndex;
  }
  $('flow-board').append(section);
 }
 if(!visibleNodes.length)para($('flow-board'),'No recorded scene or event matches these filters. Sources have not been discarded.','empty');
 $('flow-count').textContent=visibleNodes.length?'Records '+(flowPage*size+1)+'-'+Math.min((flowPage+1)*size,visibleNodes.length)+' of '+visibleNodes.length:'0 matching records';
 $('flow-prev-page').disabled=flowPage===0;$('flow-next-page').disabled=(flowPage+1)*size>=visibleNodes.length;
}
function content(parent,n,{compact=false}={}){
 const r=record(n);parent.append(el('div',label(n)+' | '+approval(n),'flow-kicker'),el('h3',n.title));
 para(parent,n.participants.length?n.participants.map(person).join(' / '):'No participants declared','flow-cast');
 para(parent,position(n),'meta');
 if(n.kind==='scene'){
  heading(parent,'Situation and purpose');
  para(parent,[r.setting?.location,r.setting?.where,r.setting?.time_of_day,r.setting?.season,r.setting?.weather].filter(Boolean).join(' | '));
  para(parent,r.scene_function);para(parent,r.delivery_role);
  heading(parent,'What happens');
  authoredList(parent,objects(r.beats),b=>plain(b.beat)+' ['+plain(b.visibility)+']'+(asArray(b.teaches).length?' | teaches: '+b.teaches.map(person).join(', '):''));
  if(!objects(r.beats).length)para(parent,'No scene beats are recorded.','empty');
  if(!compact&&objects(r.exchanges).length){heading(parent,'What is said / accomplished');for(const e of objects(r.exchanges)){para(parent,asArray(e.between).map(person).join(' / '));para(parent,e.about);para(parent,e.achieves);}}
  if(r.turn){heading(parent,'Declared turn');para(parent,plain(r.turn.from)+' -> '+plain(r.turn.to));if(r.turn.note)para(parent,r.turn.note);}
  if(!compact&&objects(r.must_preserve).length){heading(parent,'Conditions to preserve');for(const q of objects(r.must_preserve))para(parent,q.statement);}
 }else if(n.kind==='event'){
  heading(parent,'Recorded account');
  if(!strings(r.notes).length)para(parent,'No narrative account is recorded for this event. The display does not fill the explanation.','empty');
  else for(const note of strings(r.notes))para(parent,note);
  heading(parent,'Why / what it refers to');para(parent,r.cause?.reference||'No cause/reference recorded.');para(parent,'Reference type: '+(r.cause?.type||'not recorded'),'meta');
  if(objects(r.preconditions).length){heading(parent,'Recorded preconditions');for(const q of objects(r.preconditions))para(parent,person(q.entity_id)+' | '+q.path+' '+q.operator+(Object.hasOwn(q,'value')?' '+plain(q.value):''),'flow-precondition');}
 }else if(n.kind==='process'){
  heading(parent,'Declared process');for(const note of strings(r.notes))para(parent,note);
  para(parent,'Starts at order '+r.started_order+'; interruption policy: '+r.interruption_policy+'. These milestones are declarations, not newly inferred events.','meta');
 }else{for(const line of strings(r.depicts))para(parent,line);para(parent,'No scene source is currently recorded for this chapter.','empty');}
 const effects=briefChanges(n);heading(parent,n.kind==='process'?'Declared milestones':'Consequences recorded by the author');
 if(effects.length)for(const effect of effects)para(parent,effect);else para(parent,'No lasting consequence is declared here. This may be intentional.','empty');
 if(n.kind==='event'&&!compact)for(const q of objects(r.changes))para(parent,'Persistence: '+q.persistence+(q.persistence==='scene-local'?' | only scene '+n.scene_context_id:'')+(q.expires_at_order!==undefined?' | expires at '+q.expires_at_order:''),'meta');
 if(!compact){
  for(const message of n.messages)para(parent,message,'warning');
  for(const d of issueList(n))para(parent,d.code+': '+d.message,d.severity==='error'?'error':'warning');
  if(n.source?.href)parent.append(link('Open original: '+n.source.path,n.source.href));
  if(n.source?.line)para(parent,'Original JSONL line '+n.source.line,'meta');
  if(n.source?.sha256)para(parent,'Source hash '+n.source.sha256,'meta');
  if(n.context_source?.href)parent.append(link('Explicit scene/state context',n.context_source.href));
 }
}
function renderCompare(){
 const box=$('flow-comparison');box.replaceChildren();box.hidden=!pinned||!selected||pinned===selected;if(box.hidden)return;
 const a=nodeMap.get(pinned),b=nodeMap.get(selected);if(!a||!b)return;
 const head=el('div',undefined,'flow-comparison-head'),close=el('button','Clear comparison');
 head.append(el('h2','Read the two passages together'),close);close.onclick=()=>{pinned=null;render();};box.append(head);
 para(box,'A comparison is not an asserted causal link. Check what connects these situations, what each person knows, and what explains the change.','flow-review-prompt');
 if(!matches(a)||!matches(b))para(box,'One pinned passage is outside the current filters; it remains explicitly visible for comparison.','flow-gap');
 const columns=el('div',undefined,'flow-comparison-columns');for(const n of [a,b]){const article=el('article');article.dataset.comparedKey=n.key;content(article,n,{compact:true});columns.append(article);}box.append(columns);
}
function renderResolved(parent,n){
 if(traceView!==view){traceView=view;traceIndex=new Map();for(const t of view?.trace||[]){const key=t.kind+':'+(t.kind==='process'?t.process_id:t.source_id);if(!traceIndex.has(key))traceIndex.set(key,[]);traceIndex.get(key).push(t);}}
 const keys=n.kind==='event'?['event:'+n.event_id]:n.kind==='process'?['process:'+n.process_id]:n.event_keys.map(k=>'event:'+nodeMap.get(k)?.event_id);
 const entries=keys.flatMap(id=>traceIndex.get(id)||[]);
 const d=el('details',undefined,'flow-section');d.append(el('summary','Shared resolver evidence at the selected point'));
 if(!view)para(d,'No state viewpoint has been generated. The source account above is still readable.','meta');
 else{
  para(d,'Selected point: '+view.view.label+' | '+view.view.timeline_id+' order '+view.view.story_order+' | '+(view.view.scene_context_id||'shared state'),'meta');
  if(!view.ok)para(d,'This viewpoint could not be resolved; no current state is asserted.','error');
  else if(!entries.length)para(d,'No applied operation from this passage appears in this selected replay. It may belong to another point, scope, revision or source.','meta');
  else{for(const t of entries.slice(0,40)){const item=el('div',undefined,'trace-entry');item.append(el('code',t.path),el('pre',json({before:t.before,after:t.after})));d.append(item);}if(entries.length>40)para(d,'More operations are available in the Axis state inspector.','meta');}
 }
 const button=el('button','Open Axis state inspector');button.addEventListener('click',()=>switchMode('axis'));d.append(button);parent.append(d);
}
function renderImages(parent,n){
 const matches=data.scene_artwork.filter(a=>a.timeline_id===n.timeline_id&&a.scene_context_id===n.scene_context_id);
 if(!matches.length)return;
 heading(parent,'Adopted scene artwork');const wrap=el('div',undefined,'flow-small-images');
 for(const row of matches){const fig=el('figure');if(row.href){const a=link('',row.href),im=el('img');im.loading='lazy';im.src=row.href;im.alt=row.label;im.addEventListener('error',()=>{im.remove();para(fig,'Image is unavailable; sync to update this record.','warning');});a.append(im);fig.append(a);}fig.append(el('figcaption',row.label+' | '+row.status));wrap.append(fig);}parent.append(wrap);
}
function renderInspector(){
 const body=$('flow-detail');body.replaceChildren();const n=nodeMap.get(selected);
 if(!n){para(body,'Open a scene or event to read its complete account. Pin one passage, then open another to compare.','empty');return;}
 if(!matches(n))para(body,'This selected passage is outside the current filters. The selection is retained, not reinterpreted.','flow-gap');
 content(body,n);
 const actions=el('div',undefined,'flow-actions'),pin=el('button',pinned===n.key?'Unpin this passage':'Pin this passage for comparison');pin.onclick=()=>{pinned=pinned===n.key?null:n.key;render();};actions.append(pin);body.append(actions);
 if(n.kind==='scene'&&n.event_keys.length){heading(body,'Events explicitly linked to this scene');for(const key of n.event_keys)relatedButton(body,key,'Recorded event: ');}
 if(n.kind==='event'&&n.scene_keys.length){heading(body,'Read its scene');for(const key of n.scene_keys)relatedButton(body,key,'Scene: ');}
 const relations=relationIndex.get(n.key)||[];
 if(relations.length){heading(body,'Explicit recorded relationships');for(const r of relations){const incoming=r.target===n.key;relatedButton(body,incoming?r.source:r.target,r.kind==='revision'?(incoming?'Revises whole event: ':'Later revision: '):(incoming?'Cause reference: ':'Named as a cause by: '));}}
 renderImages(body,n);renderResolved(body,n);
 if(n.kind==='event'){
  const refs=eventMap.get(n.event_anchor)?.references||[];
  if(refs.length){const d=el('details');d.append(el('summary','Source evidence'));for(const ref of refs){if(ref.href)d.append(link('Open recorded evidence',ref.href));para(d,ref.status,'meta');raw(d,'Recorded evidence fields',ref.record);}body.append(d);}
 }
 raw(body,'Inspect original structured record',record(n));
 const prompt=el('div',undefined,'flow-human-note');prompt.append(el('b','Human story review'));
 para(prompt,'Does the next action follow from what was shown? Who knows what here? Is a reaction, discovery or transition missing, or intentionally withheld?');
 para(prompt,'These are reading questions, not machine findings. The page records no acceptance or new story fact.','meta');body.append(prompt);
 const index=visibleNodes.indexOf(n.key);$('flow-back').disabled=index<=0;$('flow-forward').disabled=index<0||index>=visibleNodes.length-1;
 $('flow-selection-count').textContent=index>=0?'Selected '+(index+1)+' of '+visibleNodes.length+' filtered records':'Selected reference outside reading sequence';
}
function renderThreads(){
 const host=$('flow-threads');host.replaceChildren();
 const narrative=source.narrative;if(!narrative)return;
 const summary=el('summary','Story threads, questions and knowledge (author records)'),contentBox=el('div');host.append(summary,contentBox);
 para(contentBox,'Open threads are not automatically defects. Their declared statuses and chapter links are shown without semantic judgment.','meta');
 let count=0;const selectedNode=nodeMap.get(selected),who=$('participant-filter').value;
 for(const [field,headingText]of [['arcs','Organizing threads'],['promises','Promises / setups'],['questions','Questions'],['knowledge','Who knows what']]){
  const items=objects(narrative[field]).filter(r=>!who||asArray(r.characters).includes(who)||asArray(r.known_by).includes(who)||(!r.characters&&!r.known_by));
  if(!items.length)continue;contentBox.append(el('h3',headingText));
  for(const item of items.slice(0,threadLimit)){count++;const row=el('div',undefined,'flow-thread-item');row.append(badge(item.status||'declared'),el('b',item.name||item.id));
   para(row,item.statement||item.fact);if(item.want)para(row,'Want: '+item.want);if(item.need)para(row,'Need: '+item.need);
   if(item.known_by)para(row,'Known by: '+asArray(item.known_by).map(person).join(', '));
   for(const key of ['introduced','resolved','planted','payoff','learned_in'])if(item[key])para(row,key+': '+(chapterMap.get(item[key])?.title||item[key]),'meta');
   if(selectedNode?.chapter_id&&Object.values(item).includes(selectedNode.chapter_id))para(row,'This record explicitly names the selected chapter.','meta');
   raw(row,'Full thread record',item);contentBox.append(row);}
  if(items.length>threadLimit){const more=el('button','Read more '+headingText.toLowerCase());more.onclick=()=>{threadLimit+=30;renderThreads();};contentBox.append(more);}
 }
 if(!count)para(contentBox,'No matching story threads are declared.','empty');
 if(source.narrative_source.href)contentBox.append(link('Open full narrative',source.narrative_source.href));
}
function render(){
 if(mode==='axis')return;
 if(mode==='graph'){
  if(!graph)graph=storyGraph.mount(source,{select:key=>select(key,true),pin:key=>{pinned=pinned===key?null:key;render();},label,caption:n=>n.participants.length?n.participants.map(person).join(' / '):position(n),issues:issueList});
  visibleNodes=graph.render(matches,selected,pinned);
 }else renderTracks();
 if(!selected&&visibleNodes.length){selected=visibleNodes[0];if(mode==='graph')graph.render(matches,selected,pinned);}
 renderInspector();renderCompare();renderThreads();
 $('flow-ledger-state').textContent=data.ok?'Structural ledger checks passed. Story meaning still needs human review.':'Structural diagnostics are present. Read affected records without treating their state as resolved.';
 $('flow-ledger-state').className=data.ok?'flow-view-state':'error';
 $('flow-view-context').textContent=view?'Selected state evidence: '+view.view.label+' / '+view.view.timeline_id+' / order '+view.view.story_order:'No resolved state point. The story account remains readable.';
}
function select(key,fromLink=false){
 if(!nodeMap.has(key))return;
 selected=key;if(fromLink){const i=visibleNodes.indexOf(key);if(i>=0)flowPage=Math.floor(i/size);}
 render();
}
function switchMode(next){
 mode=next;$('flow-view').hidden=mode==='axis';$('axis-grid').hidden=mode!=='axis';
 $('graph-panel').hidden=mode!=='graph';$('flow-list-column').hidden=mode==='graph';$('flow-order-control').hidden=mode==='graph';$('flow-view').classList.toggle('graph-active',mode==='graph');
 for(const id of ['flow','axis','graph'])$('mode-'+id).setAttribute('aria-pressed',String(mode===id));
 if(mode!=='axis')render();
 else window.requestAnimationFrame(()=>$('axis-grid').scrollIntoView({block:'start'}));
}
$('flow-order').value=source.default_order;
$('flow-order').addEventListener('change',()=>{flowPage=0;render();});
$('mode-flow').onclick=()=>switchMode('flow');$('mode-axis').onclick=()=>switchMode('axis');$('mode-graph').onclick=()=>switchMode('graph');
$('flow-prev-page').onclick=()=>{flowPage--;render();};$('flow-next-page').onclick=()=>{flowPage++;render();};
$('flow-back').onclick=()=>{const i=visibleNodes.indexOf(selected);if(i>0){selected=visibleNodes[i-1];flowPage=Math.floor((i-1)/size);render();}};
$('flow-forward').onclick=()=>{const i=visibleNodes.indexOf(selected);if(i>=0&&i<visibleNodes.length-1){selected=visibleNodes[i+1];flowPage=Math.floor((i+1)/size);render();}};
$('flow-base').textContent=json(data.base);
if(data.source_links.base)$('flow-base-source').append(link('Open exact world-state-base',data.source_links.base));
else para($('flow-base-source'),'No world-state-base is recorded. An empty object here is not an authored initial state.','meta');
if(source.diagnostics.length){const d=el('details');d.append(el('summary','Story source notices ('+source.diagnostics.length+')'));
 for(const issue of source.diagnostics.slice(0,60))para(d,issue.source_path+': '+issue.message,'warning');
 if(source.diagnostics.length>60)para(d,'Additional notices remain in the projection JSON.','meta');$('flow-source-notices').append(d);}
if(['#flow','#axis','#graph'].includes(location.hash))switchMode(location.hash.slice(1));
return {render,changed:()=>{flowPage=0;render();},focusEvent:id=>{const key=eventNodes.get(id);if(key){if(mode==='axis')switchMode('flow');select(key,true);}},active:()=>mode!=='axis'};
})();
