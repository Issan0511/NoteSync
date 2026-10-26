import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';

const script=fs.readFileSync(new URL('../beamerplus/TabletPages.py',import.meta.url),'utf8')
  .split('PAGES_SCRIPT = r"""')[1].split('"""')[0];
const pages=[{id:'note-a',index:0,strokeCount:4,textCount:1,paper:'grid',aspect:4/3},{id:'page-b',index:1,strokeCount:0,textCount:0,paper:'plain',aspect:4/3}];

function harness(){
  const context=vm.createContext({structuredClone});
  vm.runInContext(`
    const elements=new Map(),sent=[],events=[],handled=[],toasts=[];
    let canSend=true,navigationStarts=0,navigationMoves=0,pointerEnds=0,inkStarts=0;
    class Element {
      constructor(tag='div',id=''){this.tagName=tag;this.id=id;this.children=[];this.listeners={};this.listenerOptions={};this.dataset={};this.attributes={};this.style={};this.hidden=false;this.disabled=false;this.textContent='';this.selectionTarget=false;this.classes=new Set();this.classList={toggle:(key,on)=>on?this.classes.add(key):this.classes.delete(key),add:key=>this.classes.add(key)};}
      set id(id){this.elementId=id;if(id)elements.set(id,this);}
      get id(){return this.elementId;}
      set innerHTML(html){this.html=html;this.children=[];for(const match of html.matchAll(/id="([^"]+)"/g))elements.set(match[1],new Element('div',match[1]));}
      get innerHTML(){return this.html||'';}
      appendChild(child){this.children.push(child);return child;}
      append(...children){this.children.push(...children);}
      replaceChildren(...children){this.children=children;}
      setAttribute(key,value){this.attributes[key]=value;}
      addEventListener(type,fn,options){(this.listeners[type]??=[]).push(fn);(this.listenerOptions[type]??=[]).push(options);}
      closest(selector){return this.selectionTarget&&selector.includes('selection')?this:null;}
      dispatch(type,overrides={}){
        const event={type,target:this,pointerType:'pen',pointerId:1,cancelable:true,defaultPrevented:false,propagationStopped:false,preventDefault(){this.defaultPrevented=true;},stopImmediatePropagation(){this.propagationStopped=true;},...overrides};
        for(const fn of this.listeners[type]||[]){fn(event);if(event.propagationStopped)break;}
        if(!event.propagationStopped&&event.target!==this)for(const fn of event.target.listeners[type]||[])fn(event);
        return event;
      }
      click(){if(!this.disabled)return this.dispatch('click');}
    }
    const $=id=>{if(!elements.has(id))elements.set(id,new Element('div',id));return elements.get(id);};
    const document={body:new Element('body'),createElement:tag=>new Element(tag)};
    const stage=new Element('stage'),activeCanvas=new Element('canvas'),selectionBox=new Element('selection');selectionBox.selectionTarget=true;
    const penOnlyToggle={checked:true};
    let currentDocumentId='note-a',currentNotebookId='note-a',notebookReady=true,sketchbookStrokes=[{id:'old-ink'}],noteTexts=[{text:'old annotation'}];
    function finishActiveInput(){events.push('finish');}
    function flushNotebookTitle(){events.push('flush-title');}
    function showToast(message){toasts.push(message);}
    function closeOverlays(){}
    function sendWS(message){events.push('send:'+message.type);if(!canSend||!notebookReady)return false;sent.push(structuredClone(message));return true;}
    function handleServerMessage(message){handled.push(structuredClone(message));if(message.type==='state_sync'){currentDocumentId=message.documentId;currentNotebookId=message.notebookId||currentNotebookId;if(message.sketchbookStrokes)sketchbookStrokes=structuredClone(message.sketchbookStrokes);if(message.noteTexts)noteTexts=structuredClone(message.noteTexts);}}
    function updateAssistantConnection(connected){notebookReady=connected;}
    // TabletNavigation registers its capture listener before the pages module.
    stage.addEventListener('pointerdown',event=>{if(event.pointerType==='touch'&&penOnlyToggle.checked&&!event.target.selectionTarget){navigationStarts++;event.preventDefault();event.stopImmediatePropagation();}},{capture:true});
    stage.addEventListener('pointermove',()=>navigationMoves++);
    stage.addEventListener('pointerup',()=>pointerEnds++);
    activeCanvas.addEventListener('pointerdown',()=>inkStarts++);
    selectionBox.addEventListener('pointerdown',()=>inkStarts++);
  `+script,context);
  const run=code=>vm.runInContext(code,context);
  const read=code=>JSON.parse(run(`JSON.stringify((${code})??null)`));
  const click=id=>run(`$('${id}').click()`);
  const message=msg=>run('handleServerMessage')(msg);
  const sync=(extra={})=>message({type:'state_sync',documentId:'note-a',notebookId:'note-a',pageId:'note-a',pages,currentPage:0,totalPages:pages.length,...extra});
  const result=(ok=true,extra={})=>message({type:'note_page_result',ok,requestId:read('notebookPagePending.requestId'),pageId:'page-b',...extra});
  sync();return {run,read,click,message,sync,result};
}

test('page controls reflect the confirmed page and correctly disable first/last boundaries',()=>{
  const h=harness();assert.equal(h.read("$('notebook-pages-number').textContent"),'1 / 2');assert.equal(h.read("$('notebook-page-previous').disabled"),true);assert.equal(h.read("$('notebook-page-next').disabled"),false);
  h.sync({documentId:'page-b',pageId:'page-b',currentPage:1});assert.equal(h.read("$('notebook-pages-number').textContent"),'2 / 2');assert.equal(h.read("$('notebook-page-previous').disabled"),false);assert.equal(h.read("$('notebook-page-next').disabled"),true);
});

test('page selection finishes ink and title before sending the active page document ID',()=>{
  const h=harness();h.click('notebook-page-next');
  assert.deepEqual(h.read('events'),['finish','flush-title','send:note_page']);assert.equal(h.read('sent[0].documentId'),'note-a');assert.equal(h.read('sent[0].pageId'),'page-b');assert.equal(h.read('sent[0].action'),'select');
  assert.equal(h.read('currentDocumentId'),'note-a');assert.deepEqual(h.read('sketchbookStrokes'),[{id:'old-ink'}]);assert.deepEqual(h.read('noteTexts'),[{text:'old annotation'}]);
  assert.equal(h.read("$('notebook-page-add').disabled"),true);h.click('notebook-page-next');assert.equal(h.read('sent.length'),1);
});

test('successful selection remains pending until target page state_sync confirms the new scene',()=>{
  const h=harness();h.click('notebook-pages-number');h.click('notebook-page-next');h.result();
  assert.notEqual(h.read('notebookPagePending'),null);assert.equal(h.read('notebookPagesOverlay.hidden'),false);assert.equal(h.read("$('notebook-page-add').disabled"),true);
  h.sync();assert.notEqual(h.read('notebookPagePending'),null);
  h.sync({documentId:'page-b',pageId:'page-b',currentPage:1,sketchbookStrokes:[],noteTexts:[]});
  assert.equal(h.read('notebookPagePending'),null);assert.equal(h.read('notebookPagesOverlay.hidden'),true);assert.equal(h.read('currentDocumentId'),'page-b');assert.deepEqual(h.read('sketchbookStrokes'),[]);assert.deepEqual(h.read('noteTexts'),[]);assert.equal(h.read("$('notebook-page-add').disabled"),false);
});

test('adding a page targets the current page rather than its containing notebook and waits for server metadata',()=>{
  const h=harness();h.sync({documentId:'page-b',pageId:'page-b',currentPage:1});h.click('notebook-page-add');
  assert.equal(h.read('sent[0].action'),'add');assert.equal(h.read('sent[0].documentId'),'page-b');assert.equal(h.read('sent[0].pageId'),null);assert.equal(h.read('notebookPages.length'),2);
  h.result(true,{pageId:'page-c'});assert.equal(h.read('notebookPages.length'),2);assert.notEqual(h.read('notebookPagePending'),null);
  h.sync({documentId:'page-c',pageId:'page-c',currentPage:2,totalPages:3,pages:[...pages,{id:'page-c',index:2,strokeCount:0,textCount:0}]});
  assert.equal(h.read('notebookPagePending'),null);assert.equal(h.read("$('notebook-pages-number').textContent"),'3 / 3');
});

test('unrelated page results are ignored and failure preserves the old page and its ink',()=>{
  const h=harness();h.click('notebook-page-next');h.message({type:'note_page_result',requestId:'someone-else',ok:true,pageId:'page-b'});assert.notEqual(h.read('notebookPagePending'),null);
  h.result(false,{message:'保存できません'});assert.equal(h.read('notebookPagePending'),null);assert.equal(h.read('currentDocumentId'),'note-a');assert.deepEqual(h.read('sketchbookStrokes'),[{id:'old-ink'}]);assert.equal(h.read('toasts.at(-1)'),'保存できません');assert.equal(h.read("$('notebook-page-add').disabled"),false);
});

test('page list shows real ink counts or blank pages and uses explicit taps rather than swipes',()=>{
  const h=harness();h.click('notebook-pages-number');assert.equal(h.read('notebookPagesOverlay.hidden'),false);
  assert.equal(h.read("$('notebook-pages-list').children[0].children[1].children[1].textContent"),'筆跡 4 · テキスト 1');assert.equal(h.read("$('notebook-pages-list').children[1].children[1].children[1].textContent"),'空白');
  h.run("$('notebook-pages-list').children[1].click()");assert.equal(h.read('sent[0].action'),'select');assert.equal(h.read('sent[0].pageId'),'page-b');
  assert.equal(h.read('stage.listeners.pointermove.length'),1,'page switching must not add a swipe/move handler');
});

test('pending page changes block new pen and selection starts while existing navigation remains usable',()=>{
  const h=harness();h.click('notebook-page-next');
  const pen=h.run("stage.dispatch('pointerdown',{pointerType:'pen',target:activeCanvas})");assert.equal(pen.propagationStopped,true);assert.equal(h.read('inkStarts'),0);
  const mouse=h.run("stage.dispatch('pointerdown',{pointerType:'mouse',target:activeCanvas})");assert.equal(mouse.propagationStopped,true);
  h.run("stage.dispatch('pointerdown',{pointerType:'touch',target:activeCanvas})");assert.equal(h.read('navigationStarts'),1);assert.equal(h.read('inkStarts'),0);
  const selection=h.run("stage.dispatch('pointerdown',{pointerType:'touch',target:selectionBox})");assert.equal(selection.propagationStopped,true);assert.equal(h.read('inkStarts'),0);
  h.run("penOnlyToggle.checked=false");const fingerInk=h.run("stage.dispatch('pointerdown',{pointerType:'touch',target:activeCanvas})");assert.equal(fingerInk.propagationStopped,true);assert.equal(h.read('inkStarts'),0);
  h.run("stage.dispatch('pointermove',{target:activeCanvas});stage.dispatch('pointerup',{target:activeCanvas})");assert.equal(h.read('navigationMoves'),1);assert.equal(h.read('pointerEnds'),1);
});

test('pen and selection starts resume after failure without replacing the existing handlers',()=>{
  const h=harness();h.click('notebook-page-next');h.result(false);h.run("stage.dispatch('pointerdown',{pointerType:'pen',target:activeCanvas})");assert.equal(h.read('inkStarts'),1);
  h.run("stage.dispatch('pointerdown',{pointerType:'pen',target:selectionBox})");assert.equal(h.read('inkStarts'),2);
});

test('ink and paper mutations are scoped to the current page and explicitly old documents stay rejectable',()=>{
  const h=harness();h.sync({documentId:'page-b',pageId:'page-b',currentPage:1});
  for(const type of ['stroke_start','stroke_move','stroke_end','erase_start','erase','erase_end','line_update','undo','redo','clear','note_paper'])h.run('sendWS')({type});
  assert.equal(h.read("sent.every(message=>message.documentId==='page-b')"),true);
  h.run('sendWS')({type:'stroke_end',documentId:'note-a'});assert.equal(h.read('sent.at(-1).documentId'),'note-a');
  const edit={type:'note_ink_edit',documentId:'note-a',requestId:'edit-1'};h.run('sendWS')(edit);assert.deepEqual(h.read('sent.at(-1)'),edit);
});

test('disconnect releases pending page controls and ignores a late success result',()=>{
  const h=harness();h.click('notebook-page-next');const requestId=h.read('notebookPagePending.requestId');h.run('updateAssistantConnection(false)');
  assert.equal(h.read('notebookPagePending'),null);assert.equal(h.read("$('notebook-page-add').disabled"),true);assert.equal(h.read('currentDocumentId'),'note-a');
  h.message({type:'note_page_result',requestId,ok:true,pageId:'page-b'});assert.equal(h.read('currentDocumentId'),'note-a');h.run('updateAssistantConnection(true)');assert.equal(h.read("$('notebook-page-add').disabled"),false);
});

test('failed transmission and invalid selections keep the current page available',()=>{
  const h=harness();assert.equal(h.run("requestNotebookPage('select','missing')"),false);assert.equal(h.run("requestNotebookPage('select','note-a')"),false);assert.equal(h.read('sent.length'),0);
  h.run('canSend=false');h.click('notebook-page-add');assert.equal(h.read('notebookPagePending'),null);assert.equal(h.read('currentDocumentId'),'note-a');assert.equal(h.read("$('notebook-page-add').disabled"),false);assert.match(h.read('toasts.at(-1)'),/接続/);
});

test('switching to another notebook cancels stale page navigation context',()=>{
  const h=harness();h.click('notebook-page-next');h.sync({documentId:'other-note',notebookId:'other-note',pageId:'other-note',pages:[{id:'other-note',index:0}],currentPage:0,totalPages:1});
  assert.equal(h.read('notebookPagePending'),null);assert.equal(h.read('currentNotebookId'),'other-note');assert.equal(h.read("$('notebook-pages-number').textContent"),'1 / 1');assert.equal(h.read("$('notebook-page-next').disabled"),true);
});

test('an already-arrived target state is reconciled when its matching result follows',()=>{
  const h=harness();h.click('notebook-page-next');h.sync({documentId:'page-b',pageId:'page-b',currentPage:1});assert.notEqual(h.read('notebookPagePending'),null);h.result();assert.equal(h.read('notebookPagePending'),null);assert.equal(h.read("$('notebook-pages-number').textContent"),'2 / 2');
});
