import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';

const source=fs.readFileSync(new URL('../beamerplus/TabletFavorites.py',import.meta.url),'utf8');
const model=source.split('FAVORITES_MODEL_SCRIPT = r"""')[1].split('"""')[0];
const script=model+source.split('FAVORITES_SCRIPT = FAVORITES_MODEL_SCRIPT + r"""')[1].split('"""')[0];

function modelHarness(){
  const context=vm.createContext({});
  vm.runInContext(model+`
    const original=[{brush:'pen',color:'#202124',size:4,opacity:1},{brush:'highlighter',color:'#ffcf59',size:22,opacity:.3}];
    const draft=new FavoritePenDraft();
  `,context);
  return code=>JSON.parse(vm.runInContext(`JSON.stringify((${code})??null)`,context));
}

test('editing replaces the chosen favorite without changing the source or adding a slot',()=>{
  const run=modelHarness();
  run("draft.begin(1,original[1])");run("draft.update({brush:'fountain',color:'#3478dc',size:9,opacity:.7})");
  const updated=run('draft.commit(original)');
  assert.equal(updated.length,2);
  assert.deepEqual(updated[0],run('original[0]'));
  assert.deepEqual(updated[1],{brush:'fountain',color:'#3478dc',size:9,opacity:.7});
  assert.equal(run('original[1].color'),'#ffcf59');
  assert.equal(run('draft.index'),-1);
});

test('cancel discards changes and keeps the original favorite',()=>{
  const run=modelHarness();run('draft.begin(0,original[0])');run("draft.update({color:'#ef5350',size:15})");run('draft.cancel()');
  assert.equal(run('draft.commit(original)'),null);
  assert.deepEqual(run('original[0]'),{brush:'pen',color:'#202124',size:4,opacity:1});
});

test('invalid preset changes cannot be saved',()=>{
  const run=modelHarness();run('draft.begin(0,original[0])');
  assert.equal(run("draft.update({color:'red'})"),false);
  assert.equal(run('draft.update({opacity:0})'),false);
  assert.equal(run('draft.update({size:81})'),false);
  assert.equal(run("draft.update({brush:'unknown'})"),false);
  assert.deepEqual(run('draft.commit(original)'),run('original'));
});

test('adding a pen copies it, and the six favorite limit is enforced',()=>{
  const run=modelHarness();
  const added=run('appendFavoritePen(original,original[0])');
  assert.equal(added.length,3);assert.equal(run('original.length'),2);
  assert.equal(run('appendFavoritePen(Array.from({length:6},()=>original[0]),original[0])'),null);
});

test('deleting preserves other presets and retains at least one favorite',()=>{
  const run=modelHarness();assert.deepEqual(run('removeFavoritePen(original,0)'),[run('original[1]')]);
  assert.equal(run('removeFavoritePen([original[0]],0)'),null);
  assert.equal(run('removeFavoritePen(original,-1)'),null);
});

function uiHarness(){
  const context=vm.createContext({});
  vm.runInContext(`
    const elements=new Map(),saved=new Map(),messages=[];
    class Element {
      constructor(tag='div',id=''){this.tagName=tag;this.id=id;this.children=[];this.listeners={};this.dataset={};this.style={setProperty(){}};this.hidden=false;this.attributes={};this.classes=new Set();this.classList={toggle:(c,on)=>on?this.classes.add(c):this.classes.delete(c)};}
      set id(id){this.elementId=id;if(id)elements.set(id,this);}
      get id(){return this.elementId;}
      set innerHTML(html){this.html=html;for(const match of html.matchAll(/id="([^"]+)"/g))if(!elements.has(match[1]))elements.set(match[1],new Element('div',match[1]));}
      get innerHTML(){return this.html||'';}
      addEventListener(type,fn){(this.listeners[type]??=[]).push(fn);}
      dispatch(type,value){this.value=value??this.value;for(const fn of this.listeners[type]||[])fn({target:this,preventDefault(){}});}
      append(...children){this.children.push(...children);}
      appendChild(child){this.children.push(child);return child;}
      replaceChildren(...children){this.children=children;}
      cloneNode(){const node=new Element(this.tagName,this.id);node.innerHTML=this.innerHTML;return node;}
      replaceWith(node){elements.set(this.id,node);}
      setAttribute(key,value){this.attributes[key]=value;}
      querySelectorAll(selector){return this.children.filter(child=>selector==='button'&&child.tagName==='button');}
      getContext(){return {clearRect(){},beginPath(){},moveTo(){},bezierCurveTo(){},stroke(){}};}
    }
    const $=id=>{if(!elements.has(id))elements.set(id,new Element('div',id));return elements.get(id);};
    const document={body:new Element(),createElement:tag=>new Element(tag)};
    const localStorage={setItem:(key,value)=>saved.set(key,value),getItem:key=>saved.get(key)||null};
    const brushNames={pen:'ボールペン',fountain:'万年筆',pencil:'鉛筆',highlighter:'蛍光ペン'};
    const penSvg='<svg></svg>',markerSvg='<svg></svg>';
    let favorites=[{brush:'pen',color:'#202124',size:4,opacity:1},{brush:'highlighter',color:'#ffcf59',size:22,opacity:.3}],selectedFavorite=0;
    let selectedBrush='pen',currentColor='#202124',currentTool='pen';
    const toolSizes={pen:4,highlighter:22},toolOpacities={pen:1,highlighter:.3};
    function currentPreset(){const tool=selectedBrush==='highlighter'?'highlighter':'pen';return {brush:selectedBrush,color:currentColor,size:toolSizes[tool],opacity:toolOpacities[tool]};}
    function persistPens(){localStorage.setItem('beamerplus_favorite_pens',JSON.stringify(favorites));localStorage.setItem('beamerplus_current_pen',JSON.stringify(currentPreset()));}
    function closeOverlays(){}
    function openOverlay(id){closeOverlays();$(id).hidden=false;}
    function finishActiveInput(){}
    function showToast(message){messages.push(message);}
    function renderFavorites(){}
    function updatePenUI(){renderFavorites();}
    function applyPreset(preset,index){currentColor=preset.color;selectedBrush=preset.brush;selectedFavorite=index;}
  `,context);
  vm.runInContext(script,context);
  const run=code=>vm.runInContext(code,context);
  const read=code=>JSON.parse(run(`JSON.stringify(${code})`));
  const click=id=>run(`$('${id}').dispatch('click')`);
  return {run,read,click};
}

test('favorite editor saves to the same persisted slot and leaves the current pen alone',()=>{
  const h=uiHarness();h.run('openFavoriteEditor(1)');
  h.run("$('favorite-editor-size').dispatch('input','36')");
  h.run("$('favorite-editor-custom-color').dispatch('input','#3478dc')");
  h.click('favorite-editor-save');
  const stored=h.read("JSON.parse(saved.get('beamerplus_favorite_pens'))");
  assert.equal(stored.length,2);assert.equal(stored[1].size,36);assert.equal(stored[1].color,'#3478dc');
  assert.equal(h.read('currentColor'),'#202124');assert.equal(h.read('toolSizes.pen'),4);
  assert.equal(h.read("$('favorite-manager-overlay').hidden"),false);
});

test('canceling the editor neither saves nor changes the pen',()=>{
  const h=uiHarness();h.run('openFavoriteEditor(0)');h.run("$('favorite-editor-size').dispatch('input','20')");h.click('favorite-editor-cancel');
  assert.equal(h.read('favorites[0].size'),4);assert.equal(h.read('saved.size'),0);assert.equal(h.read('toolSizes.pen'),4);
});

test('round color button opens chooser and saves the selected current color without changing favorites',()=>{
  const h=uiHarness();h.click('wheel-current-color');
  assert.equal(h.read("$('quick-color-overlay').hidden"),false);
  h.run("$('quick-color-swatches').children.find(b=>b.dataset.favoriteColor==='#ef5350').dispatch('click')");
  assert.equal(h.read('currentColor'),'#ef5350');assert.equal(h.read('favorites[0].color'),'#202124');
  assert.equal(h.read("JSON.parse(saved.get('beamerplus_current_pen')).color"),'#ef5350');
  assert.equal(h.read("$('quick-color-overlay').hidden"),true);
  assert.equal(h.read("$('wheel-current-color').style.background"),'#ef5350');
});

test('native custom color changes current color and is persisted',()=>{
  const h=uiHarness();h.click('wheel-current-color');h.run("$('quick-custom-color').dispatch('input','#123456')");
  assert.equal(h.read('currentColor'),'#123456');assert.equal(h.read("JSON.parse(saved.get('beamerplus_current_pen')).color"),'#123456');
});
