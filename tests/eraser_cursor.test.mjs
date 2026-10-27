import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';

const script = fs.readFileSync(new URL('../beamerplus/TabletEraserCursor.py', import.meta.url), 'utf8')
  .split('ERASER_CURSOR_SCRIPT = r"""')[1].split('"""')[0];
const protocol = fs.readFileSync(new URL('../beamerplus/PenProtocol.py', import.meta.url), 'utf8')
  .split('PEN_PROTOCOL_SCRIPT = r"""')[1].split('"""')[0];
const inputSource = fs.readFileSync(new URL('../beamerplus/TabletInput.py', import.meta.url), 'utf8');
const metrics = inputSource.slice(inputSource.indexOf('    function getNotebookEraserMetrics()'),
  inputSource.indexOf('    function eraseAt(pos)'));

function harness(userAgent = '') {
  const context = vm.createContext({});
  vm.runInContext(`
    class Surface {
      constructor() { this.listeners = {}; this.style = {}; this.hidden = true; }
      addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
      setAttribute(name, value) { this[name] = value; }
      getBoundingClientRect() {
        const r = this.rect || {left:0,top:0,width:1000,height:600};
        return {...r, right:r.left+r.width, bottom:r.top+r.height};
      }
    }
    const activeCanvas = new Surface(), stage = new Surface(), slideWrapper = new Surface();
    stage.rect = {left:0,top:0,width:3000,height:2200};
    // Deliberately keep client dimensions unchanged when the display is zoomed.
    slideWrapper.clientWidth = 1000; slideWrapper.clientHeight = 600;
    const elements = {'eraser-size':new Surface(), 'pen-button-mode':new Surface()};
    const overlays = [new Surface()];
    const document = new Surface();
    document.body = {appendChild(node) { elements[node.id] = node; }};
    document.createElement = () => new Surface();
    document.getElementById = id => elements[id];
    document.querySelector = () => overlays.find(o => !o.hidden) || null;
    document.querySelectorAll = () => overlays;
    const window = new Surface(); window.visualViewport = new Surface();
    let currentTool = 'eraser', toolSizes = {eraser:25}, penInRange = false;
    let penButtonMode = 'hold', inkTool = null, inkPointerId = null, ready = true;
    let penUIUpdates = 0, shortcutUpdates = 0;
    function canEditNotebook() { return ready; }
    function updatePenUI() { penUIUpdates++; return 'updated'; }
    function updatePenShortcutUI() { shortcutUpdates++; }
    function openOverlay() { overlays[0].hidden = false; }
    function openFavorites() { overlays[0].hidden = false; }
    const observers = [];
    class MutationObserver {
      constructor(callback) { this.callback = callback; observers.push(this); }
      observe() {}
    }
  ` + metrics + protocol + `
    const penProtocol = new PenProtocol(${JSON.stringify(userAgent)});
    let protocolReads = 0;
    const originalRead = penProtocol.read.bind(penProtocol);
    penProtocol.read = e => { protocolReads++; return originalRead(e); };
    // Model TabletInput's earlier listener sharing classification for the event.
    activeCanvas.addEventListener('pointermove', e => penProtocol.read(e));
  ` + script, context);
  const evaluate = code => vm.runInContext(code, context);
  function fire(type, overrides = {}, surface = 'activeCanvas') {
    const event = {type, pointerId:1, pointerType:'pen', clientX:250, clientY:200,
      pressure:0, button:-1, buttons:0, target:evaluate('activeCanvas'), ...overrides};
    for (const fn of evaluate(`${surface}.listeners[${JSON.stringify(type)}] || []`)) fn(event);
    return event;
  }
  const state = () => JSON.parse(evaluate(`JSON.stringify({
    hidden:elements['eraser-cursor'].hidden, style:elements['eraser-cursor'].style,
    protocolReads, penUIUpdates, shortcutUpdates
  })`));
  return {evaluate, fire, state};
}

test('circle stays the same screen size at 100%, 200% and 500% zoom', () => {
  const h = harness();
  h.fire('pointermove');
  assert.equal(h.state().style.width, '30px');
  h.evaluate('slideWrapper.rect = {left:0,top:0,width:2000,height:1200}; refreshEraserCursor()');
  assert.equal(h.state().style.width, '30px');
  assert.equal(h.state().style.height, '30px');
  assert.equal(h.evaluate('getNotebookEraserMetrics().pageRadius'), .0125);
  h.evaluate('slideWrapper.rect = {left:0,top:0,width:5000,height:3000}; refreshEraserCursor()');
  assert.equal(h.state().style.width, '30px');
  assert.equal(h.evaluate('getNotebookEraserMetrics().pageRadius'), .005);
  h.evaluate('slideWrapper.clientHeight = 1000; slideWrapper.rect = {left:0,top:0,width:600,height:1000}; refreshEraserCursor()');
  assert.equal(h.state().style.width, '50px');
  assert.equal(h.state().style.left, '250px');
  assert.equal(h.state().style.top, '200px');
  h.evaluate('slideWrapper.rect = {left:0,top:0,width:3000,height:5000}; refreshEraserCursor()');
  assert.equal(h.state().style.width, '50px');
});

test('minimum radius and integer size use the same rules as the server', () => {
  const h = harness();
  h.evaluate('toolSizes.eraser = 5');
  h.fire('pointermove');
  assert.equal(h.state().style.width, '9.6px');
  h.evaluate('toolSizes.eraser = 18.9');
  h.fire('input', {}, "elements['eraser-size']");
  assert.equal(Number.parseFloat(h.state().style.width), 21.6);
});

test('tool changes update the last hover and preserve existing UI updates', () => {
  const h = harness();
  h.fire('pointermove');
  assert.equal(h.state().hidden, false);
  h.evaluate("currentTool = 'pen'; updatePenUI()");
  assert.equal(h.state().hidden, true);
  assert.equal(h.state().penUIUpdates, 1);
  assert.equal(h.evaluate("currentTool = 'eraser'; updatePenUI()"), 'updated');
  assert.equal(h.state().hidden, false);
});

test('temporary barrel hover shows radius in hold mode and hides after release', () => {
  const h = harness();
  h.evaluate("currentTool = 'pen'");
  h.fire('pointermove', {buttons:2, button:2});
  assert.equal(h.state().hidden, false);
  h.fire('pointermove');
  assert.equal(h.state().hidden, true);
  h.evaluate("penButtonMode = 'toggle'");
  h.fire('pointermove', {buttons:2, button:2});
  assert.equal(h.state().hidden, true);
  h.fire('pointermove', {buttons:32, button:5});
  assert.equal(h.state().hidden, false);
});

test('Samsung pressure-free barrel hover stays a hover and cached refresh does not reclassify it', () => {
  const h = harness('Android SamsungBrowser/29.0');
  h.evaluate("currentTool = 'pen'");
  const event = h.fire('pointermove', {buttons:1, button:0, pressure:0});
  assert.equal(h.state().hidden, false);
  assert.equal(h.evaluate('penProtocol.contact'), false);
  const reads = h.state().protocolReads;
  h.evaluate('refreshEraserCursor(); updatePenShortcutUI(); observers[0].callback()');
  assert.equal(h.state().protocolReads, reads);
  assert.equal(h.state().shortcutUpdates, 1);
  assert.equal(h.evaluate('penProtocol.contact'), false);
  assert.equal(event.pressure, 0);
  h.fire('pointermove', {buttons:0, button:-1, pressure:0});
  assert.equal(h.state().hidden, true);
});

test('touch cursor appears only for the touch pointer actually erasing', () => {
  const h = harness();
  h.fire('pointerdown', {pointerType:'touch'});
  assert.equal(h.state().hidden, true);
  h.evaluate("inkTool = 'eraser'; inkPointerId = 1");
  h.fire('pointermove', {pointerType:'touch'});
  assert.equal(h.state().hidden, false);
  h.fire('pointerup', {pointerType:'touch'});
  assert.equal(h.state().hidden, true);
  h.fire('pointermove', {pointerType:'touch', pointerId:2});
  assert.equal(h.state().hidden, true);
});

test('palm events do not displace the hovering pen cursor', () => {
  const h = harness();
  h.evaluate('penInRange = true');
  h.fire('pointermove', {clientX:310});
  h.fire('pointerdown', {pointerType:'touch', pointerId:2, clientX:800});
  h.fire('pointercancel', {pointerType:'touch', pointerId:2});
  assert.equal(h.state().hidden, false);
  assert.equal(h.state().style.left, '310px');
});

test('leaving, cancellation and blur hide and forget the cursor position', () => {
  for (const event of ['pointerleave','pointercancel','lostpointercapture','blur']) {
    const h = harness();
    h.fire('pointermove');
    h.fire(event, {}, event === 'blur' ? 'window' : 'activeCanvas');
    assert.equal(h.state().hidden, true, event);
    h.evaluate('updatePenUI()');
    assert.equal(h.state().hidden, true, event);
  }
});

test('opening a menu hides the cursor immediately and direct overlay changes are observed', () => {
  for (const opener of ['openOverlay','openFavorites']) {
    const h = harness();
    h.fire('pointermove');
    h.evaluate(opener + '()');
    assert.equal(h.state().hidden, true);
    h.evaluate('overlays[0].hidden = true; observers[0].callback()');
    assert.equal(h.state().hidden, true);
  }
  const h = harness();
  h.fire('pointermove');
  h.evaluate('overlays[0].hidden = false; observers[0].callback()');
  assert.equal(h.state().hidden, true);
});

test('paper boundaries, stage clipping and disconnected state suppress the circle', () => {
  const h = harness();
  h.fire('pointermove', {clientX:1100});
  assert.equal(h.state().hidden, true);
  h.evaluate('stage.rect = {left:0,top:0,width:200,height:600}');
  h.fire('pointermove', {clientX:250});
  assert.equal(h.state().hidden, true);
  h.evaluate('stage.rect.width = 1000; ready = false');
  h.fire('pointermove');
  assert.equal(h.state().hidden, true);
});
