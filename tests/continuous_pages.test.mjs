import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';

const source=fs.readFileSync(new URL('../beamerplus/TabletContinuous.py',import.meta.url),'utf8').split('CONTINUOUS_SCRIPT = r"""')[1].split('"""')[0];
function section(start,end){return source.slice(source.indexOf(start),source.indexOf(end));}
const geometry=section('notebookView.zoomAt=function','function continuousRow');
const wheel=section('function scrollNotebookWheel','function sidebarPaperVisible');
const queue=section('function queuedPaperPoint','stage.addEventListener(\'pointerdown\',event=>{const row');

function harness(){
  const context=vm.createContext({});
  vm.runInContext(`
    const sent=[],painted=[],replayed=[],toasts=[],timers=new Map();let timerId=0;
    const notebookView={scale:1,x:0,y:0},continuousWidth=600,continuousHeight=2500;
    const row={id:'second',top:820,height:800,meta:{aspect:.75},node:{dataset:{pageId:'second'},getBoundingClientRect:()=>({left:20,top:100,width:600,height:800})}};
    const continuousPages=new Map([['first',{id:'first',top:0,height:800}],['second',row],['third',{id:'third',top:1640,height:800}]]);
    const stage={clientHeight:600,clientWidth:640,getBoundingClientRect:()=>({left:0,top:0,width:640,height:600}),captures:new Set(),setPointerCapture(id){this.captures.add(id);},hasPointerCapture(id){return this.captures.has(id);},releasePointerCapture(id){this.captures.delete(id);}};
    const activeCanvas={setPointerCapture(id){stage.captures.delete(id);}};
    const penOnlyToggle={checked:true},viewTouches=new Map();
    let notebookReady=true,isDrawing=false,selectionRequest=null,currentDocumentId='first',currentNotebookId='book',notebookPagePending=null,continuousSettleTimer=null,continuousAutoSelect=false,continuousInkQueue=null;
    let penInRange=false,inkPointerId=null,penContactArmed=false,currentTool='pen',currentColor='#202124',selectedBrush='fountain',isLineMode=false;
    const toolSizes={pen:4,highlighter:22},toolOpacities={pen:1,highlighter:.3};
    function clearTimeout(id){timers.delete(id);}function setTimeout(fn){timers.set(++timerId,fn);return timerId;}
    function finishActiveInput(){replayed.push('finish');}
    function refreshNotebookView(){notebookView.constrain(stage.clientWidth,stage.clientHeight);painted.push({...notebookView});}
    function continuousRow(id){return continuousPages.get(id);}
    function paintContinuousRow(row){painted.push(row.id);}
    function selectionPointerActive(){return false;}
    function requestNotebookPage(action,pageId){sent.push({action,pageId,auto:continuousAutoSelect});notebookPagePending={action,pageId};return true;}
    function inputPressure(e){return e.pressure||1;}
    function penHasContact(e){return e.pressure>0;}
    function isPenEraser(e){return e.buttons===2;}
    function getCurrentWidthRatio(){return .004;}function getToolOpacity(){return .8;}function getCurrentBrush(){return 'fountain';}
    function currentPreset(){return {brush:selectedBrush,color:currentColor,size:toolSizes.pen,opacity:toolOpacities.pen};}
    function beginInkAt(pos,tool,pressure){isDrawing=true;replayed.push({phase:'start',pos,tool,pressure});}
    function moveInkTo(pos,pressure){replayed.push({phase:'move',pos,pressure});}
    function finishInkStroke(){isDrawing=false;replayed.push({phase:'end'});}
    function renderInkSelection(){}function showToast(message){toasts.push(message);}
  `+geometry+wheel+queue,context);
  const run=code=>vm.runInContext(code,context);
  const read=code=>JSON.parse(run(`JSON.stringify((${code})??null)`));
  const event=(overrides={})=>({target:run('row.node'),pointerType:'pen',pointerId:12,clientX:320,clientY:500,pressure:.6,buttons:1,button:0,preventDefault(){this.prevented=true;},stopImmediatePropagation(){this.stopped=true;},...overrides});
  run('row.node.closest=()=>row.node');
  return {run,read,event};
}

test('a wheel scroll at 100% moves the continuous papers locally without zooming or switching immediately',()=>{
  const h=harness();const event=h.event({deltaY:480,deltaX:0,deltaMode:0});h.run('scrollNotebookWheel')(event);
  assert.equal(event.prevented,true);assert.deepEqual(h.read('notebookView'),{scale:1,x:0,y:-480});assert.deepEqual(h.read('sent'),[]);
  h.run('[...timers.values()][0]()');assert.deepEqual(h.read('sent'),[]);
});

test('settled scrolling selects the paper at the viewport center while preserving local scroll position',()=>{
  const h=harness();h.run('notebookView.y=-950;settleNotebookScroll();[...timers.values()][0]()');
  assert.deepEqual(h.read('sent'),[{action:'select',pageId:'second',auto:true}]);assert.equal(h.read('notebookView.y'),-950);
});

test('fingers still down or pending pen edits prevent background page activation',()=>{
  for(const busy of ['viewTouches.set(1,{})','isDrawing=true','selectionRequest="edit"']){const h=harness();h.run('notebookView.y=-950;'+busy+';settleNotebookScroll();[...timers.values()][0]()');assert.deepEqual(h.read('sent'),[]);}
});

test('pinch zoom keeps the same paper point under the gesture and clamps the full stack',()=>{
  const h=harness();h.run('notebookView.y=-900;notebookView.zoomAt(2,{x:320,y:300})');
  assert.deepEqual(h.read('notebookView'),{scale:2,x:0,y:-2080});
  h.run('notebookView.zoomAt(1,{x:320,y:300})');assert.equal(h.read('notebookView.y'),-900,'100% must not jump to the first page');
  h.run('notebookView.y=-99999;notebookView.constrain(640,600)');assert.equal(h.read('notebookView.y'),-1940);
});

test('the first stroke on an inactive paper is buffered with pressure and original normalized coordinates',()=>{
  const h=harness(),event=h.event();assert.equal(h.run('queuePendingPaperInput')(event),true);assert.equal(event.stopped,true);
  assert.deepEqual(h.read('continuousInkQueue.stroke.points'),[[.5,.5,.6]]);assert.deepEqual(h.read('sent'),[{action:'select',pageId:'second',auto:true}]);assert.deepEqual(h.read('replayed'),[]);
  h.run('continuousInkQueue.stroke.points.push([.6,.55,.9]);continuousInkQueue.ended=true;replayPendingPaperInput()');assert.deepEqual(h.read('replayed'),[],'wait for matching target and successful activation');
  h.run('currentDocumentId="second";notebookPagePending=null;replayPendingPaperInput()');
  assert.deepEqual(h.read('replayed'),[{phase:'start',pos:{normX:.5,normY:.5},tool:'pen',pressure:.6},{phase:'move',pos:{normX:.6,normY:.55},pressure:.9},{phase:'end'}]);assert.equal(h.read('continuousInkQueue'),null);
});

test('a still-down pen transfers to the live canvas after buffered samples are replayed',()=>{
  const h=harness();h.run('queuePendingPaperInput')(h.event());h.run('currentDocumentId="second";notebookPagePending=null;replayPendingPaperInput()');
  assert.equal(h.read('inkPointerId'),12);assert.equal(h.read('penContactArmed'),true);assert.equal(h.read('isDrawing'),true);
});

test('finger navigation, hover clicks and an unrelated pending page cannot create queued ink',()=>{
  const h=harness();assert.equal(h.run('queuePendingPaperInput')(h.event({pointerType:'touch'})),false);assert.equal(h.run('queuePendingPaperInput')(h.event({pressure:0})),false);
  h.run('notebookPagePending={pageId:"third"}');assert.equal(h.run('queuePendingPaperInput')(h.event()),false);assert.deepEqual(h.read('sent'),[]);
});

test('a page queued in another notebook never replays into the current notebook',()=>{
  const h=harness();h.run('queuePendingPaperInput')(h.event());h.run('currentDocumentId="second";currentNotebookId="different";notebookPagePending=null;replayPendingPaperInput()');assert.deepEqual(h.read('replayed'),[]);assert.notEqual(h.read('continuousInkQueue'),null);
});
