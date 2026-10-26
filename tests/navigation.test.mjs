import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';

function script(file, assignment) {
  return fs.readFileSync(new URL('../beamerplus/' + file, import.meta.url), 'utf8')
    .split(assignment + ' = ')[1].split('r"""')[1].split('"""')[0];
}

const inputScript = script('PenProtocol.py', 'PEN_PROTOCOL_SCRIPT')
  + script('TabletInput.py', 'INPUT_SCRIPT');
const navigationScript = script('TabletNavigation.py', 'VIEW_MODEL_SCRIPT')
  + script('TabletNavigation.py', 'NAVIGATION_SCRIPT');

// Load the production input and navigation scripts together. Events take their
// browser propagation route, so a navigation capture handler must actually stop
// the canvas's ink handlers rather than relying on a test-only ink stub.
function harness() {
  const context = vm.createContext({});
  vm.runInContext(`
    const ids = new Map(), sent = [], rendered = [], resolutions = [], swipeEnds = [];
    class Surface {
      constructor(tagName='div') {
        this.tagName=tagName; this.listeners={}; this.captures=new Set(); this.children=[];
        this.clientWidth=1000; this.clientHeight=600; this.width=1000; this.height=600;
        this.style={setProperty(name,value){this[name]=value;}};
        this.ctx={clearRect(){},setTransform(...args){resolutions.push(args);}};
      }
      addEventListener(type,handler,options={}) {
        (this.listeners[type] ||= []).push({handler,capture:options===true||!!options.capture});
      }
      appendChild(child) {this.children.push(child);child.parent=this;return child;}
      setAttribute(name,value) {this[name]=value;}
      set innerHTML(value) {
        for(const match of value.matchAll(/<button[^>]*id="([^"]+)"/g)) {
          const child=new Surface('button');child.id=match[1];ids.set(child.id,child);this.appendChild(child);
        }
      }
      getBoundingClientRect(){return {left:0,top:0,width:this.clientWidth,height:this.clientHeight};}
      setPointerCapture(id){this.captures.add(id);}
      hasPointerCapture(id){return this.captures.has(id);}
      releasePointerCapture(id){this.captures.delete(id);}
      getContext(){return this.ctx;}
      closest(selector) {
        if(selector.split(',').some(part => part.trim()===this.tagName))return this;
        if(this.id==='selection-box'&&selector.includes('#selection-box'))return this;
        if(this.selectionHandle&&selector.includes('[data-selection-handle]'))return this;
        return this.parent?.closest(selector)||null;
      }
    }
    const stage=new Surface(), activeCanvas=new Surface('canvas'), committedCanvas=new Surface('canvas');
    const slideWrapper=new Surface(); stage.appendChild(slideWrapper);slideWrapper.appendChild(activeCanvas);
    const activeCtx=activeCanvas.ctx,committedCtx=committedCanvas.ctx;
    const window=new Surface();window.PointerEvent=true;window.devicePixelRatio=2;
    const document={createElement:tag=>new Surface(tag)};
    const navigator={userAgent:'SamsungBrowser/29.0 Android'};
    const penOnlyToggle={checked:true};
    let currentTool='pen',currentColor='#202124',isDrawing=false,isLineMode=false,isSketchbook=true,isTrackingSwipe=false;
    let currentStrokePoints=[],sketchbookStrokes=[],slideStrokes=[];
    let eraserMode='stroke',toolSizes={eraser:25},selectionBusy=false,layoutCount=0;
    const $=id=>ids.get(id);
    function getToolOpacity(){return 1;}
    function getCurrentWidthRatio(){return .005;}
    function getPointerNormPos(e){return {normX:e.clientX/1000,normY:e.clientY/600};}
    function drawStroke(ctx,stroke){rendered.push(stroke);}
    function renderAllStrokes(strokes){rendered.push(strokes);}
    function sendWS(message){sent.push(message);}
    function startSwipe(){isTrackingSwipe=true;}
    function checkSwipe(point){swipeEnds.push(point);isTrackingSwipe=false;}
    function selectTool(tool){finishActiveInput();currentTool=tool;}
    function selectionPointerActive(){return selectionBusy;}
    function adjustLayout(){layoutCount++;}
  `, context);
  vm.runInContext(inputScript + navigationScript, context);
  const evaluate = code => vm.runInContext(code, context);
  const state = () => JSON.parse(evaluate(`JSON.stringify({
    view:{scale:notebookView.scale,x:notebookView.x,y:notebookView.y},
    touches:[...viewTouches.keys()],baseline:pinchBaseline,sent,sketchbookStrokes,
    isDrawing,inkPointerId,penInRange,stageCaptures:[...stage.captures],
    inkCaptures:[...activeCanvas.captures],resolutionCount:resolutions.length
  })`));
  const fire = (type, overrides = {}, targetName = 'activeCanvas') => {
    let target = evaluate(targetName);
    const pointerId = overrides.pointerId ?? 1;
    if (!overrides.ignoreCapture && evaluate(`stage.hasPointerCapture(${pointerId})`)) target = evaluate('stage');
    else if (!overrides.ignoreCapture && evaluate(`activeCanvas.hasPointerCapture(${pointerId})`)) target = evaluate('activeCanvas');
    const ended = /up|cancel|lost/.test(type);
    const event = {type,pointerId,pointerType:'touch',clientX:400,clientY:300,
      button:type==='pointermove' ? -1 : 0,buttons:ended ? 0 : 1,pressure:ended ? 0 : .5,target,
      prevented:false,stopped:false,
      preventDefault(){this.prevented=true;},
      stopImmediatePropagation(){this.stopped=true;},...overrides};
    const run = (surface, capture) => {
      for (const listener of surface.listeners[type] || []) {
        if (listener.capture === capture) listener.handler(event);
        if (event.stopped) break;
      }
    };
    const stage = evaluate('stage');
    run(stage, true);
    if (!event.stopped && target !== stage) run(target, true);
    if (!event.stopped && target !== stage) run(target, false);
    if (!event.stopped) run(stage, false);
    return event;
  };
  const blur = () => {
    for (const {handler} of evaluate('window.listeners.blur || []')) handler({type:'blur'});
  };
  return {evaluate,state,fire,blur};
}

function pinch(h) {
  h.fire('pointerdown',{pointerId:1,clientX:400});
  h.fire('pointerdown',{pointerId:2,clientX:600});
  h.fire('pointermove',{pointerId:2,clientX:800});
}

test('two fingers pinch through production handlers without creating ink or a swipe',()=>{
  const h=harness();
  pinch(h);
  let state=h.state();
  assert.equal(state.view.scale,2);
  assert.deepEqual(state.touches,[1,2]);
  assert.deepEqual(state.stageCaptures,[1,2]);
  assert.equal(state.sent.length,0);
  assert.equal(state.sketchbookStrokes.length,0);
  assert.equal(state.inkPointerId,null);
  h.fire('pointerup',{pointerId:1});h.fire('pointerup',{pointerId:2});
  state=h.state();
  assert.deepEqual(state.touches,[]);
  assert.deepEqual(state.stageCaptures,[]);
  assert.equal(state.baseline,null);
  assert.ok(state.resolutionCount>0);
  assert.equal(h.evaluate('swipeEnds.length'),0);
});

test('one finger pans an already enlarged page while its ink coordinates stay unchanged',()=>{
  const h=harness();
  h.evaluate('sketchbookStrokes=[{points:[[.2,.3,.8]],width_ratio:.005}];zoomNotebook(2)');
  h.fire('pointerdown',{clientX:350,clientY:200});
  h.fire('pointermove',{clientX:430,clientY:250});
  const state=h.state();
  assert.deepEqual(state.view,{scale:2,x:80,y:50});
  assert.deepEqual(state.sketchbookStrokes[0].points,[[.2,.3,.8]]);
  assert.equal(state.sent.length,0);
  h.fire('pointerup');
  assert.deepEqual(h.state().stageCaptures,[]);
});

test('a cancelled pinch releases both pointers and orphan moves cannot resume it',()=>{
  const h=harness();pinch(h);
  h.fire('pointercancel',{pointerId:1});h.fire('pointercancel',{pointerId:2});
  const before=h.state();
  assert.deepEqual(before.touches,[]);
  assert.deepEqual(before.stageCaptures,[]);
  assert.equal(before.baseline,null);
  h.fire('pointermove',{pointerId:2,clientX:900,clientY:500});
  assert.deepEqual(h.state().view,before.view);
  assert.equal(h.state().sent.length,0);
});

test('lost pointer capture removes a navigation pointer and resets its pinch baseline',()=>{
  const h=harness();pinch(h);
  h.evaluate('stage.releasePointerCapture(2)');
  h.fire('lostpointercapture',{pointerId:2},'stage');
  assert.deepEqual(h.state().touches,[1]);
  assert.equal(h.state().baseline.distance,undefined);
  h.evaluate('stage.releasePointerCapture(1)');
  h.fire('lostpointercapture',{pointerId:1},'stage');
  assert.equal(h.state().baseline,null);
  assert.deepEqual(h.state().touches,[]);
});

test('S Pen contact arriving on pointermove takes over a pinch and releases its captures',()=>{
  const h=harness();
  // Samsung can send a barrel-button pointerdown while the tip still hovers.
  h.fire('pointerdown',{pointerId:9,pointerType:'pen',pressure:0,buttons:1});
  assert.equal(h.state().isDrawing,false);
  pinch(h);
  h.fire('pointermove',{pointerId:9,pointerType:'pen',pressure:.6,buttons:1,clientX:500});
  const state=h.state();
  assert.deepEqual(state.touches,[]);
  assert.deepEqual(state.stageCaptures,[]);
  assert.equal(state.baseline,null);
  assert.equal(state.isDrawing,true);
  assert.equal(state.inkPointerId,9);
  assert.equal(state.sent.filter(message=>message.type==='stroke_start').length,1);
  h.fire('pointerup',{pointerId:9,pointerType:'pen'});
  assert.equal(h.state().sketchbookStrokes.length,1);
});

test('palm touches during an active pen stroke cannot move the page or interrupt ink',()=>{
  const h=harness();h.evaluate('zoomNotebook(2)');
  h.fire('pointerdown',{pointerId:9,pointerType:'pen'});
  const before=h.state().view;
  h.fire('pointerdown',{pointerId:1});h.fire('pointerdown',{pointerId:2,clientX:600});
  h.fire('pointermove',{pointerId:2,clientX:900});h.fire('pointerup',{pointerId:1});
  assert.deepEqual(h.state().touches,[]);
  assert.deepEqual(h.state().view,before);
  assert.equal(h.state().isDrawing,true);
  assert.equal(h.state().inkPointerId,9);
  h.fire('pointermove',{pointerId:9,pointerType:'pen',clientX:700});
  h.fire('pointerup',{pointerId:9,pointerType:'pen',clientX:700});
  assert.equal(h.state().sketchbookStrokes.length,1);
  assert.equal(h.state().sent.filter(message=>message.type==='stroke_end').length,1);
});

test('touching zoom controls or selection handles never starts a navigation gesture',()=>{
  const h=harness();
  const buttonEvent=h.fire('pointerdown',{ignoreCapture:true},"$('zoom-in')");
  assert.equal(buttonEvent.prevented,false);
  assert.deepEqual(h.state().touches,[]);
  assert.deepEqual(h.state().view,{scale:1,x:0,y:0});
  h.evaluate("const handle=new Surface();handle.selectionHandle=true;stage.appendChild(handle)");
  h.fire('pointerdown',{ignoreCapture:true},'handle');
  assert.deepEqual(h.state().touches,[]);
  assert.equal(h.state().sent.length,0);
  h.fire('click',{ignoreCapture:true},"$('zoom-in')");
  assert.equal(h.state().view.scale,1.35);
  assert.deepEqual(h.state().touches,[]);
});

test('an active lasso gesture prevents finger navigation from stealing its pointer',()=>{
  const h=harness();h.evaluate("currentTool='lasso';selectionBusy=true;zoomNotebook(2)");
  h.fire('pointerdown');h.fire('pointermove',{clientX:800});
  assert.deepEqual(h.state().touches,[]);
  assert.deepEqual(h.state().view,{scale:2,x:0,y:0});
  assert.equal(h.state().sent.length,0);
});

test('one finger is ignored as a palm during pen hover while two fingers can still pinch',()=>{
  const h=harness();h.evaluate('zoomNotebook(2)');
  h.fire('pointerenter',{pointerId:9,pointerType:'pen',pressure:0,buttons:0,button:-1});
  h.fire('pointerdown',{clientX:400});h.fire('pointermove',{clientX:450});
  assert.deepEqual(h.state().view,{scale:2,x:0,y:0});
  h.fire('pointerdown',{pointerId:2,clientX:600});
  h.fire('pointermove',{pointerId:2,clientX:750});
  assert.equal(h.state().view.scale,4);
  assert.equal(h.state().sent.length,0);
});

test('blur cancels navigation and pen state so old movement cannot resume either',()=>{
  const h=harness();pinch(h);
  h.blur();
  const before=h.state();
  assert.deepEqual(before.touches,[]);
  assert.equal(before.baseline,null);
  assert.equal(before.inkPointerId,null);
  h.fire('pointermove',{pointerId:2,clientX:950,clientY:550});
  assert.deepEqual(h.state().view,before.view);
  assert.equal(h.state().sent.length,0);

  const pen=harness();
  pen.fire('pointerdown',{pointerId:9,pointerType:'pen'});
  pen.blur();
  pen.fire('pointermove',{pointerId:9,pointerType:'pen',clientX:900});
  assert.equal(pen.state().isDrawing,false);
  assert.equal(pen.state().penInRange,false);
  assert.equal(pen.state().sketchbookStrokes.length,1);
  assert.equal(pen.state().sent.filter(message=>message.type==='stroke_start').length,1);
  assert.equal(pen.state().sent.filter(message=>message.type==='stroke_end').length,1);
});
