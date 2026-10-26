import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';

const source=fs.readFileSync(new URL('../beamerplus/TabletSelection.py',import.meta.url),'utf8');
const geometry=source.split('SELECTION_GEOMETRY_SCRIPT = r"""')[1].split('"""')[0];
const script=geometry+source.split('SELECTION_SCRIPT = SELECTION_GEOMETRY_SCRIPT + r"""')[1].split('"""')[0];

function harness(){
  const context=vm.createContext({structuredClone});
  vm.runInContext(`
    const elements=new Map(),frames=new Map(),timers=new Map();
    let nextFrame=0,nextTimer=0,canSend=true;
    const metrics={baseRenders:[],draws:[],resizes:0,contextTransforms:0,pointTransforms:0,rafRequests:0,rafRuns:0,viewResets:0};
    const sent=[],toasts=[];let baseVisible=[];
    function fakeContext(){return {strokes:[],clearRect(){this.strokes=[];},setTransform(){metrics.contextTransforms++;},setLineDash(){},beginPath(){},moveTo(){},lineTo(){},stroke(){},save(){},restore(){},drawImage(){},fillRect(){},resetTransform(){}};}
    class Element {
      constructor(tag='div',id=''){
        this.tagName=tag.toUpperCase();this.id=id;this.children=[];this.listeners={};this.attributes={};this.dataset={};this.captures=new Set();this.hidden=false;
        this.style={setProperty(name,value){this[name]=value;},removeProperty(name){delete this[name];}};
        this.classes=new Set();this.classList={toggle:(name,on)=>on?this.classes.add(name):this.classes.delete(name),add:(...names)=>names.forEach(name=>this.classes.add(name)),remove:(...names)=>names.forEach(name=>this.classes.delete(name))};
        this.clientWidth=1000;this.clientHeight=600;this.offsetWidth=540;this.offsetHeight=44;this.context=fakeContext();this._width=1000;this._height=600;
      }
      set id(id){this.elementId=id;if(id)elements.set(id,this);}
      get id(){return this.elementId;}
      set width(value){this._width=value;metrics.resizes++;}
      get width(){return this._width;}
      set height(value){this._height=value;metrics.resizes++;}
      get height(){return this._height;}
      set innerHTML(html){
        this.html=html;
        for(const match of html.matchAll(/id="([^"]+)"/g))if(!elements.has(match[1]))elements.set(match[1],new Element('input',match[1]));
        for(const match of html.matchAll(/<button[^>]*data-ink-action="([^"]+)"[^>]*>(.*?)<\\/button>/g)){const child=new Element('button');child.dataset.inkAction=match[1];child.textContent=match[2];this.appendChild(child);}
      }
      get innerHTML(){return this.html||'';}
      appendChild(child){child.parentElement=this;this.children.push(child);return child;}
      append(...children){for(const child of children)this.appendChild(child);}
      replaceChildren(...children){this.children=[];this.append(...children);}
      before(){}
      setAttribute(name,value){this.attributes[name]=value;}
      removeAttribute(name){delete this.attributes[name];}
      addEventListener(type,fn){(this.listeners[type]??=[]).push(fn);}
      dispatch(type,overrides={}){const event={type,pointerId:1,pointerType:'pen',button:0,buttons:1,pressure:.5,clientX:200,clientY:120,target:this,preventDefault(){},stopImmediatePropagation(){},...overrides};for(const fn of this.listeners[type]||[])fn(event);return event;}
      click(){this.dispatch('click');}
      setPointerCapture(id){this.captures.add(id);}
      hasPointerCapture(id){return this.captures.has(id);}
      releasePointerCapture(id){this.captures.delete(id);}
      getContext(){return this.context;}
      querySelectorAll(selector){return this.children.filter(child=>selector==='button'&&child.tagName==='BUTTON');}
      querySelector(selector){const action=selector.match(/data-ink-action="(.*?)"/);return action?this.children.find(child=>child.dataset.inkAction===action[1]):null;}
      getBoundingClientRect(){
        const number=(value,total,fallback)=>value===undefined?fallback:value.endsWith('%')?parseFloat(value)*total/100:parseFloat(value);
        const left=number(this.style.left,1000,0),top=number(this.style.top,600,0),width=number(this.style.width,1000,this.clientWidth),height=number(this.style.height,600,this.clientHeight);
        return {left,top,width,height,right:left+width,bottom:top+height};
      }
    }
    const $=id=>{if(!elements.has(id))elements.set(id,new Element('div',id));return elements.get(id);};
    const document=new Element();document.body=new Element('body');document.createElement=tag=>new Element(tag);document.getElementById=$;
    const window=new Element();window.devicePixelRatio=1;window.visualViewport=new Element();
    function requestAnimationFrame(fn){metrics.rafRequests++;const id=++nextFrame;frames.set(id,fn);return id;}
    function cancelAnimationFrame(id){frames.delete(id);}
    function flushFrames(){const callbacks=[...frames.values()];frames.clear();for(const fn of callbacks){metrics.rafRuns++;fn(16.7);}}
    window.requestAnimationFrame=requestAnimationFrame;window.cancelAnimationFrame=cancelAnimationFrame;
    function setTimeout(fn){const id=++nextTimer;timers.set(id,fn);return id;}
    function clearTimeout(id){timers.delete(id);}
    const activeCanvas=new Element('canvas','active-canvas'),committedCanvas=new Element('canvas','committed-canvas'),slideWrapper=new Element('div','slide-wrapper'),stage=new Element('div','stage');
    slideWrapper.appendChild(committedCanvas);slideWrapper.appendChild(activeCanvas);
    const notebookView={scale:1,reset(){metrics.viewResets++;}};
    let currentTool='lasso',currentDocumentId='notebook-1',notebookReady=true,isLineMode=false,paperAspect=1000/600;
    let noteMetadata={title:'Original title',paper:'plain',notes:[]};
    const penOnlyToggle={checked:true};
    let sketchbookStrokes=[
      {brush:'pen',color:'#202124',opacity:1,width_ratio:.004,points:[[.1,.1,.5],[.3,.3,.8]]},
      {brush:'pen',color:'#3478dc',opacity:1,width_ratio:.004,points:[[.7,.7,.4],[.8,.8,.6]]}
    ];
    const initialStrokes=structuredClone(sketchbookStrokes);
    function finishActiveInput(){}
    function showToast(message){toasts.push(message);}
    function getPointerNormPos(e){return {normX:e.clientX/1000,normY:e.clientY/600};}
    function isPenEraser(){return false;}
    function penHasContact(e){return e.pressure>0;}
    function onInkStart(){}
    function drawStroke(ctx,stroke){metrics.draws.push(structuredClone(stroke));ctx.strokes.push(structuredClone(stroke));}
    function renderAllStrokes(strokes){metrics.baseRenders.push(structuredClone(strokes));baseVisible=structuredClone(strokes);}
    function updatePenUI(){}
    function adjustLayout(){renderAllStrokes(sketchbookStrokes);}
    function refreshNotebookView(){}
    function closeOverlays(){}
    function updateAssistantConnection(){}
    function sendWS(message){if(!canSend)return false;sent.push(structuredClone(message));return true;}
    function handleServerMessage(msg){
      if(msg.type==='state_sync'){
        currentDocumentId=msg.documentId||'';sketchbookStrokes=structuredClone(msg.sketchbookStrokes||msg.strokes||[]);
        noteMetadata={title:msg.title??noteMetadata.title,paper:msg.paper??noteMetadata.paper,notes:structuredClone(msg.notes??noteMetadata.notes)};
        renderAllStrokes(sketchbookStrokes);
      }
      else if(msg.type==='strokes_updated'||msg.type==='stroke_undone'){sketchbookStrokes=structuredClone(msg.strokes||[]);renderAllStrokes(sketchbookStrokes);}
      else if(msg.type==='strokes_cleared'){sketchbookStrokes=[];renderAllStrokes([]);}
    }
  `,context);
  vm.runInContext(script,context);
  vm.runInContext(`
    const transformBeforeTest=InkSelectionGeometry.transform;
    InkSelectionGeometry.transform=function(...args){metrics.pointTransforms++;return transformBeforeTest.call(this,...args);};
    function resetMetrics(){metrics.baseRenders=[];metrics.draws=[];metrics.resizes=0;metrics.contextTransforms=0;metrics.pointTransforms=0;metrics.rafRequests=0;metrics.rafRuns=0;}
    function visibleInk(){
      const transform=selectionLayer.style.transform||'',values=transform.startsWith('matrix(')?transform.slice(7,-1).split(',').map(Number):[1,0,0,1,0,0];
      const [a,b,c,d,e,f]=values;
      const selected=selectionCanvas.context.strokes.filter(stroke=>stroke.color!=='#80b8ee').map(stroke=>({...stroke,points:stroke.points.map(([x,y,...rest])=>[(a*x*1000+c*y*600+e)/1000,(b*x*1000+d*y*600+f)/600,...rest])}));
      return [...baseVisible,...selected];
    }
    selectedInk=[0];renderInkSelection();resetMetrics();
  `,context);
  const run=code=>vm.runInContext(code,context);
  const read=code=>JSON.parse(run(`JSON.stringify((${code})??null)`));
  function event(type,x=.2,y=.2,extra={}){return {type,pointerId:1,pointerType:'pen',button:0,buttons:type==='pointerup'?0:1,pressure:type==='pointerup'?0:.5,clientX:x*1000,clientY:y*600,target:run('selectionBox'),preventDefault(){},stopImmediatePropagation(){},...extra};}
  function start({handle='move',x=.2,y=.2}={}){
    const target=handle==='move'?run('selectionBox'):run(`selectionBox.children.find(child=>child.dataset.selectionHandle===${JSON.stringify(handle)})`);
    run('selectionBox.dispatch.bind(selectionBox)')('pointerdown',{clientX:x*1000,clientY:y*600,target});run('resetMetrics()');
  }
  function move(x,y){const e=event('pointermove',x,y);run('dragSelection')(e);}
  function finish(x,y,cancelled=false){const e=event('pointerup',x,y);run('finishSelectionDrag')(e,cancelled);}
  function message(msg){run('handleServerMessage')(msg);}
  function changedSnapshot(dx=.2,dy=.1){const snapshot=read('initialStrokes');snapshot[0].points=snapshot[0].points.map(([x,y,...tail])=>[x+dx,y+dy,...tail]);return snapshot;}
  const latestRequest=()=>read("sent.findLast(message=>message.type==='note_ink_edit')");
  function ack(ok=true,extra={}){message({type:'note_ink_edit_result',requestId:latestRequest().requestId,documentId:'notebook-1',inkRevision:1,indices:[0],ok,...extra});}
  return {run,read,event,start,move,finish,message,changedSnapshot,latestRequest,ack,flush:()=>run('flushFrames()')};
}

function assertPoint(actual,expected){assert.equal(actual.length,expected.length);actual.forEach((value,i)=>assert.ok(Math.abs(value-expected[i])<1e-9,`point component ${i}: ${value} != ${expected[i]}`));}
function assertUntransformed(h){
  const layer=h.read("typeof selectionLayer!=='undefined'?selectionLayer.style.transform:null");
  assert.ok(layer===null||layer===undefined||layer===''||layer==='none'||/^matrix\(1,\s*0,\s*0,\s*1,\s*0,\s*0\)$/.test(layer),`lingering drag transform: ${layer}`);
}
function assertBackgroundRestored(h){
  assertVisibleInk(h,[.1,.1,.5]);
}
function assertVisibleInk(h,point,color='#202124'){
  const visible=h.read('visibleInk()');assert.equal(visible.length,2,'background and selected layer should show each stroke once');
  const selected=visible.filter(stroke=>stroke.color===color);assert.equal(selected.length,1,'selected stroke should be visible once without a ghost');assertPoint(selected[0].points[0],point);
}

test('many pointermoves coalesce to one compositor frame without redrawing ink or transforming points',()=>{
  const h=harness();h.start();
  for(let i=1;i<=100;i++)h.move(.2+i*.001,.2+i*.0005);
  const before=h.read('metrics');
  assert.equal(before.baseRenders.length,0);assert.equal(before.draws.length,0);
  assert.equal(before.resizes,0);assert.equal(before.contextTransforms,0);assert.equal(before.pointTransforms,0);
  assert.equal(h.read('frames.size'),1);assert.equal(before.rafRequests,1);
  h.flush();
  const after=h.read('metrics');assert.equal(after.rafRuns,1);assert.equal(after.baseRenders.length,0);assert.equal(after.draws.length,0);assert.equal(after.resizes,0);assert.equal(after.pointTransforms,0);
  assert.match(h.read('selectionLayer.style.transform'),/^matrix\(/);
});

test('pointerup uses final coordinates before the scheduled frame and paints transformed local ink immediately',()=>{
  const h=harness();h.start();h.move(.24,.23);h.finish(.4,.3);
  const request=h.latestRequest();assert.equal(request.action,'transform');assertPoint(request.matrix,[1,0,0,1,.2,.1]);
  assertPoint(h.read('sketchbookStrokes[0].points[0]'),[.3,.2,.5]);
  assertVisibleInk(h,[.3,.2,.5]);
  assert.equal(h.read('frames.size'),0);assert.equal(h.read('selectionDrag'),null);
});

test('old or duplicate server snapshots cannot snap an optimistic selection back before ACK',()=>{
  const h=harness();h.start();h.finish(.4,.3);
  const original=h.read('initialStrokes');
  for(let i=0;i<3;i++)h.message({type:'strokes_updated',documentId:'notebook-1',inkRevision:0,strokes:original});
  assertPoint(h.read('sketchbookStrokes[0].points[0]'),[.3,.2,.5]);
  assertVisibleInk(h,[.3,.2,.5]);
  assert.notEqual(h.read('selectionRequest'),null);
});

test('matching ACK adopts the buffered server snapshot without transforming it a second time',()=>{
  const h=harness();h.start();h.finish(.4,.3);
  h.message({type:'strokes_updated',documentId:'notebook-1',inkRevision:1,strokes:h.changedSnapshot()});h.ack();
  assertPoint(h.read('sketchbookStrokes[0].points[0]'),[.3,.2,.5]);
  assertVisibleInk(h,[.3,.2,.5]);
  assert.equal(h.read('selectionRequest'),null);assert.equal(h.read("typeof selectionPending!=='undefined'?selectionPending:null"),null);
  assert.deepEqual(h.read('selectedInk'),[0]);assertUntransformed(h);
});

test('rejected optimistic edit restores the latest authoritative snapshot',()=>{
  const h=harness();h.start();h.finish(.4,.3);
  const latest=h.read('initialStrokes');latest[0].color='#ef5350';
  h.message({type:'strokes_updated',documentId:'notebook-1',inkRevision:2,strokes:latest});h.ack(false,{inkRevision:2});
  assertPoint(h.read('sketchbookStrokes[0].points[0]'),[.1,.1,.5]);assert.equal(h.read('sketchbookStrokes[0].color'),'#ef5350');
  assert.equal(h.read('metrics.baseRenders.at(-1)[0].color'),'#ef5350');assert.equal(h.read('selectionRequest'),null);assertUntransformed(h);
});

test('pointer cancellation restores selected background and clears pending compositor work',()=>{
  const h=harness();h.start();h.move(.4,.3);h.flush();h.finish(.4,.3,true);
  assert.equal(h.read('sent.length'),0);assert.equal(h.read('selectionDrag'),null);assert.equal(h.read('frames.size'),0);
  assertPoint(h.read('sketchbookStrokes[0].points[0]'),[.1,.1,.5]);assertBackgroundRestored(h);assertUntransformed(h);
});

for(const [reason,reset] of [
  ['mode change',"currentTool='pen';updatePenUI()"],
  ['window blur',"window.dispatch('blur')"],
  ['layout change','adjustLayout()'],
])test(`${reason} cancels a drag, clears CSS transforms, and restores hidden selected ink`,()=>{
  const h=harness();h.start();h.move(.4,.3);h.flush();h.run(reset);
  assert.equal(h.read('selectionDrag'),null);assert.equal(h.read('frames.size'),0);assert.equal(h.read('sent.length'),0);
  assertBackgroundRestored(h);assertUntransformed(h);
});

test('switching to pen before ACK keeps the pen active and selection dismissed',()=>{
  const h=harness();h.start();h.finish(.4,.3);h.run("currentTool='pen';updatePenUI()");
  h.message({type:'strokes_updated',documentId:'notebook-1',inkRevision:1,strokes:h.changedSnapshot()});h.ack();
  assert.equal(h.read('currentTool'),'pen');assert.deepEqual(h.read('selectedInk'),[]);assert.equal(h.read('selectionBox.hidden'),true);
  assertPoint(h.read('sketchbookStrokes[0].points[0]'),[.3,.2,.5]);assertUntransformed(h);
});

test('failed request sends no edit and leaves original ink visible',()=>{
  const h=harness();h.run('canSend=false');h.start();h.finish(.4,.3);
  assert.equal(h.read('selectionRequest'),null);assert.equal(h.read('sent.length'),0);assertPoint(h.read('sketchbookStrokes[0].points[0]'),[.1,.1,.5]);
  assertBackgroundRestored(h);assertUntransformed(h);
});

test('stale snapshots received after ACK do not restore the old position',()=>{
  const h=harness();h.start();h.finish(.4,.3);
  h.message({type:'strokes_updated',documentId:'notebook-1',inkRevision:1,strokes:h.changedSnapshot()});h.ack();
  h.message({type:'strokes_updated',documentId:'notebook-1',inkRevision:0,strokes:h.read('initialStrokes')});
  h.message({type:'strokes_updated',documentId:'notebook-1',inkRevision:1,strokes:h.read('initialStrokes')});
  assertPoint(h.read('sketchbookStrokes[0].points[0]'),[.3,.2,.5]);assertVisibleInk(h,[.3,.2,.5]);
});

test('new ink drawn while transform is pending survives its older ACK',()=>{
  const h=harness();h.start();h.finish(.4,.3);
  h.run(`
    currentTool='pen';updatePenUI();sendWS({type:'stroke_start',normX:.4,normY:.5});
  `);
  assert.equal(h.read('selectionPending.localMutation'),false);
  h.run(`
    sketchbookStrokes.push({brush:'pen',color:'#ef5350',opacity:1,width_ratio:.004,points:[[.4,.5,.6],[.6,.6,.7]]});
    renderAllStrokes(sketchbookStrokes);sendWS({type:'stroke_end'});
  `);
  assert.equal(h.read('selectionPending.localMutation'),true);
  h.message({type:'strokes_updated',documentId:'notebook-1',inkRevision:1,strokes:h.changedSnapshot()});h.ack();
  assert.equal(h.read('currentTool'),'pen');assert.equal(h.read('sketchbookStrokes.length'),3);
  assertPoint(h.read('sketchbookStrokes[2].points[0]'),[.4,.5,.6]);assert.equal(h.read('visibleInk().length'),3);
  assert.deepEqual(h.read('selectedInk'),[]);assert.equal(h.read('selectionRequest'),null);assertUntransformed(h);
});

test('authoritative state_sync before rejection restores the current note',()=>{
  const h=harness();h.start();h.finish(.4,.3);
  const strokes=h.read('initialStrokes');strokes[0].color='#ef5350';
  h.message({type:'state_sync',documentId:'notebook-1',inkRevision:2,sketchbookStrokes:strokes});h.ack(false,{inkRevision:2});
  assert.equal(h.read('currentDocumentId'),'notebook-1');assert.equal(h.read('selectionRequest'),null);
  assertVisibleInk(h,[.1,.1,.5],'#ef5350');assertUntransformed(h);
});

test('no-op eraser while transform is pending still allows rejection to restore authority',()=>{
  const h=harness();h.start();h.finish(.4,.3);
  h.run("currentTool='eraser';updatePenUI();sendWS({type:'erase',normX:.98,normY:.02})");
  assert.equal(h.read('selectionPending.localMutation'),false);
  h.message({type:'state_sync',documentId:'notebook-1',inkRevision:2,sketchbookStrokes:h.read('initialStrokes')});h.ack(false,{inkRevision:2});
  assert.equal(h.read('selectionRequest'),null);assert.equal(h.read('currentTool'),'eraser');
  assertPoint(h.read('sketchbookStrokes[0].points[0]'),[.1,.1,.5]);assertVisibleInk(h,[.1,.1,.5]);assertUntransformed(h);
});

test('state_sync forwards title, paper and notebook list while preserving optimistic ink',()=>{
  const h=harness();h.start();h.finish(.4,.3);
  const notes=[{id:'notebook-1',title:'Renamed notebook'},{id:'notebook-2',title:'Another notebook'}];
  h.message({type:'state_sync',documentId:'notebook-1',inkRevision:0,sketchbookStrokes:h.read('initialStrokes'),title:'Renamed notebook',paper:'grid',notes});
  assert.deepEqual(h.read('noteMetadata'),{title:'Renamed notebook',paper:'grid',notes});
  assert.notEqual(h.read('selectionRequest'),null);assertPoint(h.read('sketchbookStrokes[0].points[0]'),[.3,.2,.5]);assertVisibleInk(h,[.3,.2,.5]);
  h.message({type:'strokes_updated',documentId:'notebook-1',inkRevision:1,strokes:h.changedSnapshot()});h.ack();
  assert.deepEqual(h.read('noteMetadata'),{title:'Renamed notebook',paper:'grid',notes});assertVisibleInk(h,[.3,.2,.5]);
});

test('corner scaling uses the cached layer and commits the same geometry and width',()=>{
  const h=harness();h.start({handle:'se',x:.3,y:.3});h.move(.5,.5);h.flush();
  assert.equal(h.read('metrics.pointTransforms'),0);assert.equal(h.read('metrics.baseRenders.length'),0);
  const preview=h.read("visibleInk().find(stroke=>stroke.color==='#202124')");assertPoint(preview.points[1],[.5,.5,.8]);
  h.finish(.5,.5);
  assertPoint(h.latestRequest().matrix,[2,0,0,2,-.1,-.1]);assert.ok(Math.abs(h.latestRequest().widthScale-2)<1e-9);
  assertPoint(h.read('sketchbookStrokes[0].points[1]'),[.5,.5,.8]);assert.ok(Math.abs(h.read('sketchbookStrokes[0].width_ratio')-.008)<1e-9);
  assertPoint(h.read("visibleInk().find(stroke=>stroke.color==='#202124').points[1]"),[.5,.5,.8]);
});

test('rotation compositor matches normalized model geometry on a landscape page',()=>{
  const h=harness();h.start({handle:'rotate',x:.2,y:.05});h.move(.29,.2);h.flush();
  assert.equal(h.read('metrics.pointTransforms'),0);assert.equal(h.read('metrics.baseRenders.length'),0);
  const expected=[.26,1/30,.5];assertVisibleInk(h,expected);
  h.finish(.29,.2);
  assertPoint(h.read('sketchbookStrokes[0].points[0]'),expected);assertVisibleInk(h,expected);
  h.run('clearInkSelection()');
  assertUntransformed(h);assert.equal(h.read('visibleInk().length'),2);assertPoint(h.read('baseVisible[0].points[0]'),expected);
});
