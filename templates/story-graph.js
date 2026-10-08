// The graph positions authored records and draws only their recorded relations.
// A layout cut is a display annotation, never a change to the ledger or resolver.
const storyGraph = (() => {
'use strict';
const LIMITS = Object.freeze({nodes:200, edges:800, list:40, sweeps:4});
const cmp=(a,b)=>a<b?-1:a>b?1:0;
const placed=n=>typeof n.timeline_id==='string'&&Number.isSafeInteger(n.start_order);
const positionKey=n=>JSON.stringify([n.timeline_id,n.start_order]);
const compareNodes=(a,b)=>cmp(a.timeline_id||'',b.timeline_id||'') || ((a.start_order??0)-(b.start_order??0)) || cmp(a.key,b.key);
function index(source){
 const nodes=new Map(source.nodes.map(n=>[n.key,n])), edges=[], adjacency=new Map(), undirected=new Map();
 for(const key of nodes.keys()){adjacency.set(key,[]);undirected.set(key,[]);}
 for(const [i,r] of source.relations.entries()){
  if(!['cause','revision'].includes(r.kind)||!nodes.has(r.source)||!nodes.has(r.target))continue;
  // Flow stores revisions as old -> new. Graph arrows show the author operation new -> old.
  const edge={id:'graph-link-'+i,kind:r.kind,from:r.kind==='revision'?r.target:r.source,
   to:r.kind==='revision'?r.source:r.target,record:r,cut:false};
  edges.push(edge);adjacency.get(edge.from).push(edge);undirected.get(edge.from).push(edge.to);undirected.get(edge.to).push(edge.from);
 }
 // Iterative DFS: mark feedback edges, retaining every exact edge in the result.
 // This can include a valid cause/revision loop; it is not a story-contradiction verdict.
 const color=new Map();
 for(const key of [...nodes.keys()].sort()){
  if(color.has(key))continue;
  color.set(key,1);const stack=[{key,next:0}];
  while(stack.length){
   const top=stack[stack.length-1],out=adjacency.get(top.key);
   if(top.next===out.length){color.set(top.key,2);stack.pop();continue;}
   const edge=out[top.next++],state=color.get(edge.to)||0;
   if(state===1)edge.cut=true;
   else if(state===0){color.set(edge.to,1);stack.push({key:edge.to,next:0});}
  }
 }
 const positions=new Map();
 for(const n of nodes.values())if(placed(n)){const key=positionKey(n);if(!positions.has(key))positions.set(key,[]);positions.get(key).push(n.key);}
 const ordered=[...positions.entries()].sort((a,b)=>compareNodes(nodes.get(a[1][0]),nodes.get(b[1][0])));
 const pathSets=(source.state_paths||[]).map(p=>new Set(p.event_keys.filter(k=>nodes.has(k))));
 return {nodes,edges,undirected,ordered,pathSets,statePaths:source.state_paths||[]};
}
function project(ix,matching,options={}){
 const limit=options.limit??LIMITS.nodes;
 if(!Number.isInteger(limit)||limit<1||limit>LIMITS.nodes)throw new Error('Invalid graph node window');
 const visible=new Set([...matching].filter(k=>ix.nodes.has(k))), relevant=new Set(visible), queue=[...visible];
 // Filtered records connected to the view remain explicit collapsed placeholders.
 for(let i=0;i<queue.length;i++)for(const key of ix.undirected.get(queue[i]))if(!relevant.has(key)){relevant.add(key);queue.push(key);}
 const groups=[],unplaced=[];
 for(const key of relevant)if(!placed(ix.nodes.get(key)))unplaced.push(key);
 unplaced.sort((a,b)=>compareNodes(ix.nodes.get(a),ix.nodes.get(b)));
 const relevantOrdered=ix.ordered.map(([key,keys])=>[key,keys.filter(k=>relevant.has(k))]).filter(x=>x[1].length);
 const expandedCount=relevantOrdered.reduce((sum,[_,keys])=>sum+keys.filter(k=>visible.has(k)).length+(keys.some(k=>!visible.has(k))?1:0),0);
 const condensed=expandedCount>limit;
 for(const [position,keys] of relevantOrdered){
  const n=ix.nodes.get(keys[0]),shown=keys.filter(k=>visible.has(k)),hidden=keys.filter(k=>!visible.has(k));
  if(condensed){groups.push({id:'position:'+position,position,timeline:n.timeline_id,order:n.start_order,keys,shown,hidden});}
  else{
   for(const key of shown)groups.push({id:key,position,timeline:n.timeline_id,order:n.start_order,keys:[key],shown:[key],hidden:[]});
   if(hidden.length)groups.push({id:'hidden:'+position,position,timeline:n.timeline_id,order:n.start_order,keys:hidden,shown:[],hidden});
  }
 }
 const pages=Math.max(1,Math.ceil(groups.length/limit)),page=Math.max(0,Math.min(options.page||0,pages-1));
 const window=groups.slice(page*limit,(page+1)*limit),keyToGroup=new Map();
 for(const g of window)for(const key of g.keys)keyToGroup.set(key,g.id);
 const groupedEdges=new Map(),incident=[],internal=new Map(),boundary=[];
 const relations=ix.edges.filter(e=>relevant.has(e.from)&&relevant.has(e.to));
 for(const e of relations){
  const from=keyToGroup.get(e.from),to=keyToGroup.get(e.to);
  if(from&&to){
   incident.push(e);
   if(from===to){if(!internal.has(from))internal.set(from,[]);internal.get(from).push(e);continue;}
   const id=JSON.stringify([from,to,e.kind,e.cut]);
   if(!groupedEdges.has(id))groupedEdges.set(id,{id,from,to,kind:e.kind,cut:e.cut,edges:[]});
   groupedEdges.get(id).edges.push(e);
  }else if(from||to)boundary.push(e);
 }
 const allEdges=[...groupedEdges.values()],edges=allEdges.slice(0,LIMITS.edges);
 return {groups:window,edges,allEdges,relations,incident,internal,boundary,unplaced,visible,relevant,
  condensed,page,pages,groupCount:groups.length,matching:visible.size,positions:relevantOrdered.length,
  omittedEdgeGroups:Math.max(0,allEdges.length-edges.length),cutCount:relations.filter(e=>e.cut).length,
  keyToGroup,allGroups:groups};
}
function layout(view){
 const width=238,height=142,column=306,row=174,padding=34,tracks=[],points=new Map();
 const timelines=new Map();for(const g of view.groups){if(!timelines.has(g.timeline))timelines.set(g.timeline,new Map());const map=timelines.get(g.timeline);if(!map.has(g.order))map.set(g.order,[]);map.get(g.order).push(g);}
 const peers=new Map(view.groups.map(g=>[g.id,[]]));
 for(const e of view.edges)if(!e.cut){peers.get(e.from).push(e.to);peers.get(e.to).push(e.from);}
 let top=54,totalWidth=700;
 for(const [timeline,map] of timelines){
  const layers=[...map.entries()].sort((a,b)=>a[0]-b[0]),rank=new Map();
  const setRanks=()=>{for(const [_,items] of layers)items.forEach((g,i)=>rank.set(g.id,i));};setRanks();
  // Fixed story columns; alternating barycentres only reorder within a position.
  for(let pass=0;pass<LIMITS.sweeps;pass++){
   const sweep=pass%2?[...layers].reverse():layers;
   for(const [_,items] of sweep){
    const weights=new Map(items.map(g=>{const values=peers.get(g.id).filter(k=>rank.has(k)).map(k=>rank.get(k));return[g.id,values.length?values.reduce((a,b)=>a+b,0)/values.length:rank.get(g.id)];}));
    items.sort((a,b)=>weights.get(a.id)-weights.get(b.id)||cmp(a.id,b.id));setRanks();
   }
  }
  const high=Math.max(...layers.map(x=>x[1].length)),trackHeight=high*row+110;
  const trackWidth=padding*2+Math.max(1,layers.length)*column;
  const reserved=58; // Top gutter carries reverse-time revisions above every card.
  layers.forEach(([order,items],col)=>{
   items.forEach((g,i)=>points.set(g.id,{x:padding+col*column,y:top+reserved+(high-items.length)*row/2+i*row,w:width,h:height,group:g}));
  });
  tracks.push({timeline,top,height:trackHeight,width:trackWidth,layers:layers.map(([order,items])=>({order,x:points.get(items[0].id).x}))});
  top+=trackHeight+46;totalWidth=Math.max(totalWidth,trackWidth);
 }
 return {points,tracks,width:totalWidth,height:Math.max(280,top),nodeWidth:width,nodeHeight:height};
}
function edgePath(edge,geometry,number){
 const a=geometry.points.get(edge.from),b=geometry.points.get(edge.to),right=b.x>a.x,same=a.x===b.x;
 const ay=a.y+a.h/2,by=b.y+b.h/2;
 if(same){const x=a.x+a.w+22+(number%4)*9;return `M ${a.x+a.w} ${ay} C ${x} ${ay}, ${x} ${by}, ${b.x+b.w} ${by}`;}
 const sign=right?1:-1,ax=right?a.x+a.w:a.x,bx=right?b.x:b.x+b.w;
 if(Math.abs(b.x-a.x)<400){const gap=Math.max(24,Math.abs(bx-ax)*.5);return `M ${ax} ${ay} C ${ax+sign*gap} ${ay}, ${bx-sign*gap} ${by}, ${bx} ${by}`;}
 // Long links use empty column gutters. They never pass through an intermediate card.
 const lane=geometry.tracks.find(t=>t.timeline===a.group.timeline);
 const upper=(lane?lane.top+35:Math.min(a.y,b.y)-26)-(number%3)*8;
 const outsideA=ax+sign*22,outsideB=bx-sign*22;
 return `M ${ax} ${ay} C ${outsideA} ${ay}, ${outsideA} ${upper}, ${outsideA} ${upper} L ${outsideB} ${upper} C ${outsideB} ${upper}, ${outsideB} ${by}, ${bx} ${by}`;
}
const ns='http://www.w3.org/2000/svg';
function svg(tag,attrs={},text){const e=document.createElementNS(ns,tag);for(const [key,value] of Object.entries(attrs))e.setAttribute(key,String(value));if(text!==undefined)e.textContent=text;return e;}
function element(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
let measureContext=null;
function lines(text,count=3,font='650 15px system-ui'){
 if(!measureContext)measureContext=document.createElement('canvas').getContext('2d');
 measureContext.font=font;
 const result=[],chars=Array.from(String(text)),width=208;
 while(chars.length&&result.length<count){
  let take=0;while(take<chars.length&&measureContext.measureText(chars.slice(0,take+1).join('')).width<=width)take++;
  take=Math.max(1,take);
  if(take<chars.length){const space=chars.slice(0,take).lastIndexOf(' ');if(space>take*.45)take=space+1;}
  let part=chars.splice(0,take).join('').trim();
  if(result.length===count-1&&chars.length){while(part.length&&measureContext.measureText(part+'\u2026').width>width)part=part.slice(0,-1);part+='\u2026';}
  result.push(part);
 }
 return result;
}
function mount(source,hooks){
 const ix=index(source),byId=id=>document.getElementById(id),frame=byId('graph-canvas'),container=byId('graph-scroll');
 let page=0,pathChoice='',zoom=1,signature=null,current=null,geometry=null,groupSelection=null,memberPage=0,relationPage=0;
 let matches=()=>true,selected=null,pinned=null,anchorAfterFilter=false;
 const title=key=>ix.nodes.get(key)?.title||key;
 const naming=key=>{const n=ix.nodes.get(key);return (n.event_id||n.scene_id||n.process_id||n.chapter_id||n.key)+': '+n.title;};
 const pathSelect=byId('graph-path');
 for(const [i,p] of ix.statePaths.entries()){const option=element('option',`${p.timeline_id||'?'} / ${p.entity_type}:${p.entity_id} ${p.path}`);option.value=String(i);pathSelect.append(option);}
 function members(group){groupSelection=group;memberPage=0;renderMembers();}
 function reading(key){hooks.select(key);if(window.matchMedia('(max-width:850px)').matches)byId('flow-detail').scrollIntoView({block:'start',behavior:'smooth'});}
 function renderMembers(){
  const box=byId('graph-members');box.replaceChildren();if(!groupSelection){box.hidden=true;return;}box.hidden=false;
  const keys=groupSelection.keys,total=Math.ceil(keys.length/LIMITS.list);memberPage=Math.max(0,Math.min(memberPage,total-1));
  box.append(element('h3',groupSelection.title||'Records at this position'));
  box.append(element('p','Group membership is a display grouping, not a new event or an implied causal connection.','meta'));
  const list=element('div',undefined,'graph-record-list');
  for(const key of keys.slice(memberPage*LIMITS.list,(memberPage+1)*LIMITS.list)){
   const n=ix.nodes.get(key),row=element('div',undefined,'graph-record-row'),open=element('button',naming(key));
   open.dataset.graphMember=key;open.onclick=()=>reading(key);row.append(open);
   if(!matches(n))row.append(element('span','Outside filters','badge'));
   const pin=element('button',pinned===key?'Unpin':'Pin comparison');pin.onclick=()=>hooks.pin(key);row.append(pin);list.append(row);
  }
  box.append(list);pagination(box,memberPage,total,n=>{memberPage=n;renderMembers();});
 }
 function pagination(box,which,pages,change){
  const bar=element('div',undefined,'graph-pager');
  const prev=element('button','Previous'),next=element('button','Next');prev.disabled=which<=0;next.disabled=which>=pages-1;
  prev.onclick=()=>change(which-1);next.onclick=()=>change(which+1);
  bar.append(prev,element('span',`Page ${which+1} of ${Math.max(1,pages)}`),next);box.append(bar);
 }
 function showLinkGroup(edges){members({keys:[...new Set(edges.flatMap(e=>[e.from,e.to]))],title:edges.length+' exact recorded relationship(s)'});}
 function renderRelations(){
  const box=byId('graph-relations-list');box.replaceChildren();
  const chosen=byId('graph-relations-selected').checked&&selected&&current.relations.some(e=>e.from===selected||e.to===selected);
  const rows=chosen?current.relations.filter(e=>e.from===selected||e.to===selected):current.relations;
  relationPage=Math.max(0,Math.min(relationPage,Math.ceil(rows.length/LIMITS.list)-1));
  byId('graph-relations-summary').textContent=`Recorded relationships (${rows.length}${chosen?' touching the selected record':''})`;
  for(const e of rows.slice(relationPage*LIMITS.list,(relationPage+1)*LIMITS.list)){
   const row=element('div',undefined,'graph-record-row');row.dataset.graphRelation=e.id;
   const from=element('button',naming(e.from)),to=element('button',naming(e.to));from.onclick=()=>reading(e.from);to.onclick=()=>reading(e.to);
   row.append(from,element('span',e.kind==='cause'?'causes':'revises',e.kind==='cause'?'graph-cause-label':'graph-revision-label'),to);
   if(e.cut)row.append(element('span','Cycle cut in layout; record retained','graph-cut-label'));
   if(!current.keyToGroup.has(e.from)||!current.keyToGroup.has(e.to))row.append(element('span','Endpoint outside this window or without a declared position','meta'));
   if(current.keyToGroup.get(e.from)===current.keyToGroup.get(e.to))row.append(element('span','Within one collapsed position','meta'));
   box.append(row);
  }
  if(!rows.length)box.append(element('p','No explicit cause or revision references are recorded for these records. Position alone creates no edge.','meta'));
  pagination(box,relationPage,Math.ceil(rows.length/LIMITS.list),n=>{relationPage=n;renderRelations();});
 }
 function renderUnplaced(){
  const box=byId('graph-unplaced');box.replaceChildren();
  const keys=current.unplaced.filter(k=>current.visible.has(k));
  box.hidden=!keys.length;if(!keys.length)return;
  box.append(element('h3',`Outside the time axis: ${keys.length} record(s)`),element('p','No complete timeline and story position is recorded. Chapter numbers, file dates and names are not used to invent a position.','meta'));
  const open=element('button','Inspect unplaced records');open.onclick=()=>members({keys,title:'Records without a declared story position'});box.append(open);
 }
 function pathMarks(){return pathChoice===''?null:ix.pathSets[Number(pathChoice)];}
 function applyHighlights(){
  const highlight=pathMarks();
  for(const node of frame.querySelectorAll('.graph-node')){
   const g=current.groups.find(g=>g.id===node.dataset.groupId);
   node.classList.toggle('selected',g.keys.includes(selected));node.classList.toggle('pinned',g.keys.includes(pinned));
   node.classList.toggle('path-match',!!highlight&&g.keys.some(k=>highlight.has(k)));
   node.setAttribute('aria-pressed',String(g.keys.includes(selected)));
  }
  const notice=byId('graph-path-note');
  notice.textContent=highlight?`${highlight.size} recorded event(s) on this exact entity/path are highlighted. Shared state paths add no causal edges; use Axis for applied state at a selected point.`:'Choose a state path to highlight its recorded events without adding causal edges.';
  const focus=byId('graph-focus');focus.disabled=!selected;byId('graph-path-records').disabled=!highlight;
 }
 function draw(){
  const previousScroll=container.scrollLeft;
  current=project(ix,nodesMatching(),{page});
  if(anchorAfterFilter){
   anchorAfterFilter=false;
   const anchor=current.visible.has(selected)?current.allGroups.findIndex(g=>g.shown.includes(selected)):current.allGroups.findIndex(g=>g.shown.length);
   if(anchor>=0&&Math.floor(anchor/LIMITS.nodes)!==current.page){page=Math.floor(anchor/LIMITS.nodes);current=project(ix,nodesMatching(),{page});}
  }
  page=current.page;geometry=layout(current);
  frame.replaceChildren();frame.setAttribute('viewBox',`0 0 ${geometry.width} ${geometry.height}`);frame.dataset.nodeCount=String(current.groups.length);
  frame.dataset.totalRecords=String(ix.nodes.size);frame.dataset.cycleCuts=String(current.cutCount);
  const defs=svg('defs');
  for(const kind of ['cause','revision']){const marker=svg('marker',{id:'graph-arrow-'+kind,viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:7,markerHeight:7,orient:'auto-start-reverse'});marker.append(svg('path',{d:'M 0 0 L 10 5 L 0 10 z',class:'graph-marker-'+kind}));defs.append(marker);}frame.append(defs);
  for(const t of geometry.tracks){
   frame.append(svg('rect',{x:5,y:t.top-40,width:geometry.width-10,height:t.height+23,rx:12,class:'graph-lane'}));
   frame.append(svg('text',{x:30,y:t.top-12,class:'graph-lane-title'},t.timeline));
   for(const layer of t.layers){frame.append(svg('text',{x:layer.x,y:t.top+18,class:'graph-order'},'Order '+layer.order));frame.append(svg('line',{x1:layer.x-12,x2:layer.x-12,y1:t.top+32,y2:t.top+t.height-25,class:'graph-column'}));}
  }
  for(const [number,e] of current.edges.entries()){
   const group=svg('g',{'class':`graph-edge ${e.kind}${e.cut?' cycle-cut':''}`,tabindex:0,role:'button','aria-label':`${e.edges.length} ${e.kind} link(s)${e.cut?', layout cycle cut':''}`});
   group.dataset.edgeKind=e.kind;group.dataset.edgeCount=String(e.edges.length);group.dataset.edgeIds=e.edges.map(x=>x.id).join(' ');
   group.dataset.source=e.edges[0].from;group.dataset.target=e.edges[0].to;
   group.append(svg('title',{},e.edges.slice(0,8).map(r=>naming(r.from)+' '+(r.kind==='cause'?'causes':'revises')+' '+naming(r.to)).join('\n')+(e.cut?'\nCycle cut for layout only. The recorded relationship is retained.':'')));
   const d=edgePath(e,geometry,number),path=svg('path',{d,class:'graph-edge-line','marker-end':'url(#graph-arrow-'+e.kind+')'});
   group.append(svg('path',{d,class:'graph-edge-hit'}),path);
   const select=()=>showLinkGroup(e.edges);group.addEventListener('click',select);group.addEventListener('keydown',ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();select();}});
   frame.append(group);
   // Break a layout feedback edge into two stubs while exposing the exact relation.
   if(e.cut){const length=path.getTotalLength(),mid=path.getPointAtLength(length*.5);
    const mask=svg('mask',{id:'graph-cut-mask-'+number,maskUnits:'userSpaceOnUse',x:0,y:0,width:geometry.width,height:geometry.height});mask.append(svg('rect',{width:geometry.width,height:geometry.height,fill:'white'}),svg('rect',{x:mid.x-39,y:mid.y-13,width:78,height:26,fill:'black'}));defs.append(mask);path.setAttribute('mask','url(#graph-cut-mask-'+number+')');
    group.append(svg('rect',{x:mid.x-35,y:mid.y-10,width:70,height:19,rx:3,class:'graph-cut-bg'}),svg('text',{x:mid.x,y:mid.y+4,class:'graph-cut-text','text-anchor':'middle'},'Cycle cut'));}
   else if(e.edges.length>1){const mid=path.getPointAtLength(path.getTotalLength()*.5);group.append(svg('text',{x:mid.x,y:mid.y-6,class:'graph-edge-count'},'x'+e.edges.length));}
  }
  for(const g of current.groups){
   const p=geometry.points.get(g.id),only=g.keys.length===1?ix.nodes.get(g.keys[0]):null;
   const hidden=g.shown.length===0;
   const titleText=hidden?`Via ${g.hidden.length} hidden record(s)`:only?only.title:`${g.keys.length} records at order ${g.order}`;
   const node=svg('g',{transform:`translate(${p.x} ${p.y})`,class:'graph-node'+(hidden?' hidden-records':'')+(!only?' collapsed-group':''),role:'button',tabindex:0,'aria-label':titleText});
   node.dataset.groupId=g.id;if(only)node.dataset.nodeKey=only.key;
   node.append(svg('rect',{width:p.w,height:p.h,rx:10,class:'graph-card'}));
   node.append(svg('text',{x:14,y:23,class:'graph-kicker'},lines(hidden?'HIDDEN BY FILTERS':only?hooks.label(only):'COLLAPSED POSITION',1,'700 10px system-ui')[0]));
   for(const [i,line] of lines(titleText,3).entries())node.append(svg('text',{x:14,y:48+i*19,class:'graph-title'},line));
   let sub=only?hooks.caption(only):`${g.shown.length} matching / ${g.hidden.length} hidden`;
   const internal=current.internal.get(g.id)?.length||0;if(internal)sub+=` | ${internal} internal link(s)`;
   node.append(svg('text',{x:14,y:112,class:'graph-caption'},lines(sub,1,'10px system-ui')[0]||''));
   const issues=g.keys.reduce((sum,k)=>sum+hooks.issues(ix.nodes.get(k)).length,0);
   const tail=issues?issues+' recorded diagnostic(s)':hidden?'Click to inspect hidden records':only?'Open passage / pin / compare':'Open member list; every source ID is retained';
   node.append(svg('text',{x:14,y:131,class:issues?'graph-issue':'graph-hint'},lines(tail,1,'9px system-ui')[0]||''));
   node.append(svg('title',{},titleText+'\n'+sub));
   const click=()=>only&&!hidden?reading(only.key):members({keys:g.keys,title:`${g.timeline} / order ${g.order}`});node.onclick=click;node.onkeydown=ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();click();}};
   frame.append(node);
  }
  const hiddenCount=[...current.relevant].filter(k=>!current.visible.has(k)).length;
  byId('graph-count').textContent=`${current.groups.length} displayed node(s) / ${current.matching} matching record(s) | ${hiddenCount} connected hidden record(s)${current.condensed?' | same-position groups collapsed':''}`;
  byId('graph-window').textContent=`Window ${page+1} of ${current.pages}`;byId('graph-previous').disabled=page===0;byId('graph-next').disabled=page===current.pages-1;
  const notes=byId('graph-notices');notes.replaceChildren();
  if(!current.matching)notes.append(element('p','No records match. Change the filters to inspect the source graph.','empty'));
  else if(!current.relations.length)notes.append(element('p','No explicit links recorded. These are positioned records, not an invented causal chain.','graph-notice'));
  if(current.cutCount)notes.append(element('p',`${current.cutCount} feedback edge(s) cut in the layout and retained in the relationship list. A layout cycle is not automatically a story contradiction.`,'graph-notice'));
  if(current.boundary.length)notes.append(element('p',`${current.boundary.length} recorded link(s) cross this window or reach unplaced records. Open the relationship list or use Focus selected to follow them.`,'graph-notice'));
  if(current.omittedEdgeGroups)notes.append(element('p',`${current.omittedEdgeGroups} additional link group(s) exceed the ${LIMITS.edges}-line display limit. All original links remain in the paged relationship list.`,'graph-notice'));
  if(current.condensed)notes.append(element('p',`The ${LIMITS.nodes}-node overview groups records only at the same timeline/order. Further positions use windows, never a false merged time. Click a group to inspect every member.`,'meta'));
  renderUnplaced();renderRelations();applyZoom();applyHighlights();container.scrollLeft=previousScroll;
 }
 function nodesMatching(){return new Set([...ix.nodes.values()].filter(matches).map(n=>n.key));}
 function applyZoom(){frame.style.width=Math.round(geometry.width*zoom)+'px';frame.style.height=Math.round(geometry.height*zoom)+'px';byId('graph-zoom-value').textContent=Math.round(zoom*100)+'%';}
 function render(match,selection,pin){
  matches=match;selected=selection;pinned=pin;
  const next=JSON.stringify([...nodesMatching()]);if(next!==signature){page=0;signature=next;groupSelection=null;relationPage=0;current=null;anchorAfterFilter=true;}
  if(!current)draw();else{applyHighlights();renderRelations();}
  renderMembers();return [...current.visible].sort((a,b)=>compareNodes(ix.nodes.get(a),ix.nodes.get(b)));
 }
 const move=n=>{page=n;current=null;groupSelection=null;relationPage=0;draw();renderMembers();container.scrollLeft=0;};
 byId('graph-previous').onclick=()=>move(page-1);byId('graph-next').onclick=()=>move(page+1);
 const fitZoom=()=>Math.min(1,Math.max(1,container.clientWidth)/geometry.width);
 byId('graph-zoom-in').onclick=()=>{zoom=Math.min(2,zoom+.15);applyZoom();};byId('graph-zoom-out').onclick=()=>{zoom=Math.max(fitZoom(),Math.max(zoom*.8,zoom-.15));applyZoom();};
 byId('graph-fit').onclick=()=>{zoom=fitZoom();applyZoom();container.scrollLeft=0;};
 byId('graph-focus').onclick=()=>{
  if(!selected)return;const target=current.allGroups.findIndex(g=>g.keys.includes(selected));
  if(target<0){members({keys:[selected],title:'Selected record is outside the declared-position graph'});return;}
  page=Math.floor(target/LIMITS.nodes);zoom=Math.max(.7,zoom);current=null;draw();const g=current.groups.find(g=>g.keys.includes(selected)),p=geometry.points.get(g.id);
  container.scrollLeft=Math.max(0,(p.x-20)*zoom);container.scrollTop=Math.max(0,(p.y-50)*zoom);
 };
 byId('graph-relations-selected').onchange=()=>{relationPage=0;renderRelations();};
 pathSelect.onchange=()=>{pathChoice=pathSelect.value;applyHighlights();};
 byId('graph-path-records').onclick=()=>{const keys=pathMarks();if(keys)members({keys:[...keys].sort((a,b)=>compareNodes(ix.nodes.get(a),ix.nodes.get(b))),title:'Recorded changes on this path; not a causal chain'});};
 return {render,index:ix,limits:LIMITS};
}
return {index,project,layout,edgePath,mount,LIMITS};
})();
