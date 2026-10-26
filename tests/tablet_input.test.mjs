import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';

const protocolScript = fs.readFileSync(new URL('../beamerplus/PenProtocol.py', import.meta.url), 'utf8')
  .split('PEN_PROTOCOL_SCRIPT = r"""')[1].split('"""')[0];
const inputScript = protocolScript + fs.readFileSync(new URL('../beamerplus/TabletInput.py', import.meta.url), 'utf8')
  .split('INPUT_SCRIPT = PEN_PROTOCOL_SCRIPT + r"""')[1].split('"""')[0];

function harness(modern = true, userAgent = '') {
  const context = vm.createContext({});
  vm.runInContext(`
    const sent = [], rendered = [], swipeEnds = [];
    class Surface {
      constructor() { this.listeners = {}; this.captures = new Set(); this.width = 1000; this.height = 600; }
      addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); }
      setPointerCapture(id) { this.captures.add(id); }
      hasPointerCapture(id) { return this.captures.has(id); }
      releasePointerCapture(id) { this.captures.delete(id); }
    }
    const activeCanvas = new Surface(), stage = new Surface();
    const window = new Surface(); window.PointerEvent = ${modern};
    const navigator = {userAgent:${JSON.stringify(userAgent)}};
    const slideWrapper = {clientWidth:1000, clientHeight:600};
    const activeCtx = {clearRect() {}}, committedCtx = {};
    const penOnlyToggle = {checked:true};
    let currentTool = 'pen', currentColor = '#123456', isDrawing = false;
    let isLineMode = false, isSketchbook = false, isTrackingSwipe = false;
    let currentStrokePoints = [], slideStrokes = [], sketchbookStrokes = [];
    let eraserMode = 'partial', toolSizes = {eraser:25};
    function getToolOpacity() { return 0.85; }
    function getCurrentWidthRatio() { return 0.005; }
    function getPointerNormPos(e) {
      return {normX:Math.max(0, Math.min(1, e.clientX/1000)), normY:Math.max(0, Math.min(1, e.clientY/600))};
    }
    function drawStroke(ctx, stroke) { rendered.push(stroke); }
    function sendWS(message) { sent.push(message); }
    function startSwipe(point) { isTrackingSwipe = true; }
    function checkSwipe(point) { swipeEnds.push(point); isTrackingSwipe = false; }
    function selectTool(tool) {
      finishActiveInput();
      currentTool = tool;
      if (tool === 'eraser') isLineMode = false;
    }
  `, context);
  vm.runInContext(inputScript, context);
  const evaluate = code => vm.runInContext(code, context);
  const state = () => JSON.parse(evaluate('JSON.stringify({sent, slideStrokes, sketchbookStrokes, swipeEnds, isDrawing, inkPointerId, penEraserActive})'));
  const fire = (type, overrides = {}) => {
    const ended = /up|cancel|lost/.test(type);
    const event = {type, pointerId:1, pointerType:'pen', clientX:100, clientY:100, button:0,
      buttons:ended ? 0 : 1, pressure:ended ? 0 : 0.5,
      preventDefault() {}, ...overrides};
    for (const handler of evaluate(`activeCanvas.listeners[${JSON.stringify(type)}] || []`)) handler(event);
  };
  return {evaluate, state, fire};
}

test('S Pen writes with pen-only enabled and finishes exactly once', () => {
  const h = harness();
  h.fire('pointerdown');
  h.fire('pointermove', {clientX:400, clientY:200});
  h.fire('pointerup', {clientX:450, clientY:250});
  h.fire('lostpointercapture');
  const state = h.state();
  assert.equal(state.slideStrokes.length, 1);
  assert.equal(state.sent.filter(m => m.type === 'stroke_start').length, 1);
  assert.equal(state.sent.filter(m => m.type === 'stroke_end').length, 1);
  assert.equal(state.isDrawing, false);
  assert.equal(state.inkPointerId, null);
});

test('finger touches do not draw in pen-only mode, but can swipe', () => {
  const h = harness();
  h.fire('pointerdown', {pointerType:'touch'});
  h.fire('pointerup', {pointerType:'touch', clientX:400});
  assert.equal(h.state().slideStrokes.length, 0);
  assert.equal(h.state().swipeEnds.length, 1);
});

test('palm and unrelated pointer-up cannot interrupt a pen stroke or swipe the page', () => {
  const h = harness();
  h.fire('pointerdown');
  h.fire('pointerdown', {pointerId:2, pointerType:'touch'});
  h.fire('pointerup', {pointerId:2, pointerType:'touch'});
  assert.equal(h.state().isDrawing, true);
  h.fire('pointermove', {clientX:400});
  h.fire('pointerup', {clientX:400});
  assert.equal(h.state().slideStrokes.length, 1);
  assert.equal(h.state().swipeEnds.length, 0);
});

test('a hovering pen rejects palm contact', () => {
  const h = harness();
  h.fire('pointerenter');
  h.fire('pointerdown', {pointerId:2, pointerType:'touch'});
  h.fire('pointerup', {pointerId:2, pointerType:'touch'});
  assert.equal(h.state().swipeEnds.length, 0);
  assert.equal(h.state().inkPointerId, null);
});

test('pen can take over a finger swipe without mixing pointers', () => {
  const h = harness();
  h.fire('pointerdown', {pointerId:2, pointerType:'touch'});
  h.fire('pointerdown');
  h.fire('pointerup', {pointerId:2, pointerType:'touch'});
  h.fire('pointerup', {clientX:300});
  assert.equal(h.state().slideStrokes.length, 1);
  assert.equal(h.state().swipeEnds.length, 0);
});

test('pointer cancellation preserves drawn ink without a phantom endpoint', () => {
  const h = harness();
  h.fire('pointerdown');
  h.fire('pointermove', {clientX:300});
  h.fire('pointercancel', {clientX:0, clientY:0});
  const points = h.state().slideStrokes[0].points;
  assert.equal(points.length, 2);
  assert.equal(points.at(-1)[0], 0.3);
  assert.equal(h.state().isDrawing, false);
});

test('finishing before a page or layout change commits ink and releases capture', () => {
  const h = harness();
  h.fire('pointerdown');
  h.evaluate('finishActiveInput()');
  h.fire('pointermove', {clientX:700});
  assert.equal(h.state().slideStrokes.length, 1);
  assert.equal(h.state().slideStrokes[0].points.length, 1);
  assert.equal(h.evaluate('activeCanvas.captures.size'), 0);
});

test('line drawing still snaps to horizontal', () => {
  const h = harness();
  h.evaluate('isLineMode = true');
  h.fire('pointerdown', {clientY:300});
  h.fire('pointerup', {clientX:500, clientY:305});
  const points = h.state().slideStrokes[0].points;
  assert.equal(points[0][1], points[1][1]);
  assert.equal(h.state().sent.find(m => m.type === 'line_update').normY, 0.5);
});

test('eraser sends erasing operations without creating a stroke', () => {
  const h = harness();
  h.evaluate("currentTool = 'eraser'");
  h.fire('pointerdown');
  h.fire('pointermove', {clientX:400});
  h.fire('pointerup');
  assert.equal(h.state().sent.filter(m => m.type === 'erase').length, 2);
  assert.equal(h.state().slideStrokes.length, 0);
});

test('mouse can draw, but right-click cannot', () => {
  const h = harness();
  h.fire('pointerdown', {pointerType:'mouse', button:2});
  assert.equal(h.state().inkPointerId, null);
  h.fire('pointerdown', {pointerType:'mouse'});
  h.fire('pointerup', {pointerType:'mouse'});
  assert.equal(h.state().slideStrokes.length, 1);
});

test('modern browsers register no duplicate touch drawing handlers', () => {
  const h = harness();
  assert.equal(h.evaluate('activeCanvas.listeners.touchstart'), undefined);
});

test('older Safari Touch Events still accept Apple Pencil', () => {
  const h = harness(false);
  h.fire('touchstart', {changedTouches:[{identifier:9, touchType:'stylus', clientX:100, clientY:100}]});
  h.fire('touchend', {changedTouches:[{identifier:9, touchType:'stylus', clientX:300, clientY:100}]});
  assert.equal(h.state().slideStrokes.length, 1);
  assert.equal(h.evaluate('activeCanvas.listeners.pointerdown'), undefined);
});

test('barrel button erases temporarily and preserves highlighter and line settings', () => {
  const h = harness();
  h.evaluate("currentTool = 'highlighter'; isLineMode = true");
  h.fire('pointerdown', {buttons:3});
  h.fire('pointermove', {buttons:3, clientX:300});
  h.fire('pointerup');
  assert.equal(h.state().sent.filter(m => m.type === 'erase').length, 2);
  assert.equal(h.state().slideStrokes.length, 0);
  assert.equal(h.evaluate('currentTool'), 'highlighter');
  assert.equal(h.evaluate('isLineMode'), true);
  assert.equal(h.state().penEraserActive, false);
  h.fire('pointerdown');
  h.fire('pointerup', {clientX:500});
  assert.equal(h.state().sent.find(m => m.type === 'stroke_start').tool, 'highlighter');
  assert.equal(h.state().sent.find(m => m.type === 'stroke_start').isLine, true);
});

test('hovering with the barrel button never erases, contact can start on pointermove', () => {
  const h = harness();
  h.fire('pointerdown', {buttons:2, pressure:0});
  h.fire('pointermove', {buttons:2, pressure:0, clientX:200});
  assert.equal(h.state().sent.length, 0);
  h.fire('pointermove', {buttons:3, clientX:300});
  assert.equal(h.state().sent.filter(m => m.type === 'erase').length, 1);
  h.fire('pointermove', {buttons:2, pressure:0, clientX:500});
  assert.equal(h.state().sent.filter(m => m.type === 'erase').length, 1);
  h.fire('pointermove', {buttons:3, clientX:600});
  assert.equal(h.state().sent.filter(m => m.type === 'erase').length, 2);
  h.fire('pointerup');
  assert.equal(h.state().inkPointerId, null);
});

test('pressing and releasing the button during contact splits ink at the erasing gap', () => {
  const h = harness();
  h.fire('pointerdown');
  h.fire('pointermove', {clientX:200});
  h.fire('pointermove', {buttons:3, clientX:300});
  h.fire('pointermove', {buttons:3, clientX:400});
  h.fire('pointermove', {buttons:1, clientX:500});
  h.fire('pointerup', {clientX:600});
  const s = h.state();
  assert.equal(s.slideStrokes.length, 2);
  assert.equal(s.slideStrokes[0].points.at(-1)[0], 0.2);
  assert.equal(s.slideStrokes[1].points[0][0], 0.5);
  assert.equal(s.sent.filter(m => m.type === 'stroke_end').length, 2);
  assert.equal(s.sent.filter(m => m.type === 'erase').length, 2);
  assert.equal(h.evaluate('activeCanvas.captures.size'), 0);
});

test('eraser tip and barrel shortcut work even when no drawing tool is selected', () => {
  const h = harness();
  h.evaluate('currentTool = null');
  h.fire('pointerdown', {buttons:32, button:5});
  h.fire('pointerup');
  assert.equal(h.state().sent.filter(m => m.type === 'erase').length, 1);
  assert.equal(h.state().swipeEnds.length, 0);
  assert.equal(h.evaluate('currentTool'), null);
});

test('cancellation or focus loss clears temporary erasing', () => {
  for (const cancel of ['pointercancel', 'blur']) {
    const h = harness();
    h.fire('pointerdown', {buttons:3});
    if (cancel === 'blur') h.evaluate("window.listeners.blur[0]()");
    else h.fire(cancel);
    assert.equal(h.state().penEraserActive, false);
    assert.equal(h.state().inkPointerId, null);
  }
});

test('mouse right button is not treated as a pen shortcut', () => {
  const h = harness();
  h.fire('pointerdown', {pointerType:'mouse', buttons:2, button:2});
  h.fire('pointermove', {pointerType:'mouse', buttons:2, button:2});
  assert.equal(h.state().sent.length, 0);
  assert.equal(h.state().penEraserActive, false);
});

test('historical samples cannot undo a barrel button transition', () => {
  const h = harness();
  h.fire('pointerdown');
  h.fire('pointermove', {buttons:3, clientX:400, getCoalescedEvents:() => [
    {pointerId:1, pointerType:'pen', buttons:1, pressure:0.5, clientX:300, clientY:100, preventDefault() {}}
  ]});
  assert.equal(h.state().sent.at(-1).type, 'erase');
  assert.equal(h.state().penEraserActive, true);
});

test('Android Chrome selects click-to-toggle; Samsung Internet retains hold-to-erase', () => {
  assert.equal(harness(true, 'Android Chrome/140.0').evaluate('penButtonMode'), 'toggle');
  assert.equal(harness(true, 'Android Chrome/140.0 SamsungBrowser/28.0').evaluate('penButtonMode'), 'hold');
  assert.equal(harness(true, 'Windows Chrome/140.0').evaluate('penButtonMode'), 'hold');
});

test('Chrome hover click toggles eraser once, release then contact erases normally', () => {
  const h = harness(true, 'Android Chrome/140.0');
  h.evaluate("currentTool = 'highlighter'; isLineMode = true");
  h.fire('pointerdown', {buttons:2, pressure:0});
  h.fire('pointermove', {buttons:2, pressure:0, clientX:200});
  h.fire('pointermove', {buttons:2, pressure:0, clientX:300});
  assert.equal(h.evaluate('currentTool'), 'eraser');
  assert.equal(h.state().sent.length, 0);
  h.fire('pointerup');
  assert.equal(h.evaluate('currentTool'), 'eraser');
  h.fire('pointerdown');
  h.fire('pointermove', {clientX:400});
  h.fire('pointerup');
  assert.equal(h.state().sent.filter(m => m.type === 'erase').length, 2);
  assert.equal(h.state().slideStrokes.length, 0);
  h.fire('pointerdown', {buttons:2, pressure:0});
  assert.equal(h.evaluate('currentTool'), 'highlighter');
  assert.equal(h.evaluate('isLineMode'), true);
});

test('Chrome recognizes a hover button transition on pointermove without pointerdown', () => {
  const h = harness(true, 'Android Chrome/140.0');
  h.fire('pointerenter', {buttons:0, pressure:0});
  h.fire('pointermove', {buttons:2, pressure:0});
  assert.equal(h.evaluate('currentTool'), 'eraser');
  h.fire('pointermove', {buttons:0, pressure:0});
  h.fire('pointermove', {buttons:2, pressure:0});
  assert.equal(h.evaluate('currentTool'), 'pen');
});

test('Chrome mode never toggles for mouse right click or ordinary pen contact', () => {
  const h = harness(true, 'Android Chrome/140.0');
  h.fire('pointerdown', {pointerType:'mouse', button:2, buttons:2});
  assert.equal(h.evaluate('currentTool'), 'pen');
  h.fire('pointerdown');
  h.fire('pointerup');
  assert.equal(h.evaluate('currentTool'), 'pen');
  assert.equal(h.state().slideStrokes.length, 1);
});

const samsungAgent = 'Android Chrome/140.0 SamsungBrowser/28.0';

test('measured Samsung hover button event never deposits ink', () => {
  const h = harness(true, samsungAgent);
  h.fire('pointerenter', {button:-1, buttons:0, pressure:0});
  h.fire('pointermove', {button:0, buttons:1, pressure:0});
  h.fire('pointermove', {button:0, buttons:1, pressure:0, clientX:400});
  assert.equal(h.state().penEraserActive, true);
  assert.equal(h.state().isDrawing, false);
  assert.equal(h.state().sent.length, 0);
  assert.equal(h.state().slideStrokes.length, 0);
});

test('measured Samsung barrel-held contact erases; release restores ordinary ink', () => {
  const h = harness(true, samsungAgent);
  h.fire('pointermove', {button:0, buttons:1, pressure:0});
  h.fire('pointerdown', {button:0, buttons:1, pressure:0.45});
  h.fire('pointermove', {button:0, buttons:1, pressure:0.51, clientX:300});
  h.fire('pointerup');
  assert.equal(h.state().sent.filter(m => m.type === 'erase').length, 2);
  assert.equal(h.state().slideStrokes.length, 0);
  h.fire('pointermove', {button:-1, buttons:0, pressure:0});
  h.fire('pointerdown');
  h.fire('pointermove', {button:-1, clientX:500});
  h.fire('pointerup', {clientX:600});
  assert.equal(h.state().slideStrokes.length, 1);
});

test('Samsung button can change during contact without connecting across an erasing gap', () => {
  const h = harness(true, samsungAgent);
  h.fire('pointerdown');
  h.fire('pointermove', {button:-1, clientX:200});
  h.fire('pointermove', {button:0, clientX:300});
  h.fire('pointermove', {button:-1, clientX:500});
  h.fire('pointerup', {clientX:600});
  assert.equal(h.state().sent.filter(m => m.type === 'erase').length, 1);
  assert.equal(h.state().slideStrokes.length, 2);
  assert.equal(h.state().slideStrokes[0].points.at(-1)[0], 0.2);
  assert.equal(h.state().slideStrokes[1].points[0][0], 0.5);
});

test('Samsung synthetic tip-up and re-entry while held do not toggle twice', () => {
  const h = harness(true, samsungAgent);
  h.evaluate("penButtonMode = 'toggle'");
  h.fire('pointermove', {button:0, buttons:1, pressure:0});
  assert.equal(h.evaluate('currentTool'), 'eraser');
  h.fire('pointerdown');
  h.fire('pointermove', {button:0, clientX:300});
  h.fire('pointerup');
  h.fire('pointerleave', {buttons:0, pressure:0});
  h.fire('pointerenter', {button:0, buttons:1, pressure:0});
  h.fire('pointermove', {button:0, buttons:1, pressure:0});
  assert.equal(h.evaluate('currentTool'), 'eraser');
  h.fire('pointermove', {button:-1, buttons:0, pressure:0});
  h.fire('pointermove', {button:0, buttons:1, pressure:0});
  assert.equal(h.evaluate('currentTool'), 'pen');
});

test('Samsung normal tip-down with zero initial pressure waits for contact', () => {
  const h = harness(true, samsungAgent);
  h.fire('pointerdown', {pressure:0});
  assert.equal(h.state().sent.length, 0);
  h.fire('pointermove', {button:-1, pressure:0.2, clientX:200});
  h.fire('pointerup', {clientX:300});
  assert.equal(h.state().slideStrokes.length, 1);
  assert.equal(h.state().sent.filter(m => m.type === 'erase').length, 0);
});

test('Samsung coalesced samples inherit the actual button state', () => {
  const h = harness(true, samsungAgent);
  h.fire('pointermove', {button:0, buttons:1, pressure:0});
  h.fire('pointerdown');
  h.fire('pointermove', {button:0, clientX:500, getCoalescedEvents:() => [
    {type:'pointermove',pointerId:1,pointerType:'pen',button:-1,buttons:1,pressure:0.5,clientX:400,clientY:100,preventDefault(){}}
  ]});
  assert.equal(h.state().slideStrokes.length, 0);
  assert.equal(h.state().sent.at(-1).type, 'erase');
  assert.equal(h.state().penEraserActive, true);
});

test('Samsung button state cannot stick across focus loss or cancellation', () => {
  for (const cancel of ['blur','pointercancel']) {
    const h = harness(true, samsungAgent);
    h.fire('pointermove', {button:0, buttons:1, pressure:0});
    if (cancel === 'blur') h.evaluate('window.listeners.blur[0]()');
    else h.fire(cancel);
    h.fire('pointerdown');
    h.fire('pointerup');
    assert.equal(h.state().slideStrokes.length, 1);
    assert.equal(h.state().sent.filter(m => m.type === 'erase').length, 0);
  }
});

test('two short hover clicks open favorites only on the second release', () => {
  const h = harness(true, samsungAgent);
  h.evaluate(`const shortcut = new PenShortcutGesture(); let shortcutTime = 0, opened = 0;
    function handlePenButtonGesture(e, signal) { if (shortcut.update(signal, shortcutTime)) { opened++; return true; } return false; }`);
  for (let click=0;click<2;click++) {
    h.evaluate(`shortcutTime = ${click*150}`);
    h.fire('pointermove', {button:0, buttons:1, pressure:0});
    assert.equal(h.evaluate('opened'), 0);
    h.evaluate(`shortcutTime = ${click*150+50}`);
    h.fire('pointermove', {button:-1, buttons:0, pressure:0});
  }
  assert.equal(h.evaluate('opened'), 1);
  assert.equal(h.state().slideStrokes.length, 0);
});

test('holding or erasing cannot be mistaken for double clicking favorites', () => {
  const h = harness();
  h.evaluate('const shortcut = new PenShortcutGesture()');
  const result = h.evaluate(`[
    shortcut.update({barrel:true,contact:false},0),
    shortcut.update({barrel:false,contact:false},500),
    shortcut.update({barrel:true,contact:false},550),
    shortcut.update({barrel:true,contact:true},600),
    shortcut.update({barrel:false,contact:false},650),
    shortcut.update({barrel:true,contact:false},700),
    shortcut.update({barrel:false,contact:false},750)
  ].some(Boolean)`);
  assert.equal(result, false);
});

test('brush, opacity and actual pressure travel with a stroke', () => {
  const h = harness();
  h.evaluate("function getCurrentBrush() { return 'fountain'; }");
  h.fire('pointerdown', {pressure:.2});
  h.fire('pointermove', {clientX:400,pressure:.8});
  h.fire('pointerup', {clientX:500});
  const stroke = h.state().slideStrokes[0];
  assert.equal(stroke.brush, 'fountain');
  assert.equal(stroke.opacity, .85);
  assert.equal(stroke.points[0][2], .2);
  assert.equal(stroke.points.at(-1)[2], .8);
  assert.equal(h.state().sent.find(e=>e.type==='stroke_start').brush, 'fountain');
});
