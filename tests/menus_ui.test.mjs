import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';

const menuSource=fs.readFileSync(new URL('../beamerplus/TabletMenus.py',import.meta.url),'utf8');
const script=menuSource.split('MENUS_SCRIPT = r"""')[1].split('"""')[0];
const librarySource=fs.readFileSync(new URL('../beamerplus/TabletLibrary.py',import.meta.url),'utf8');
const library=librarySource.split('LIBRARY_MODEL_SCRIPT = r"""')[1].split('"""')[0]+librarySource.split('LIBRARY_SCRIPT = LIBRARY_MODEL_SCRIPT + r"""')[1].split('"""')[0];

function harness(){
  const context=vm.createContext({structuredClone,Blob,atob,btoa});
  vm.runInContext(`
    const elements=new Map(),stored=new Map(),timers=new Map(),fileButtons=[],sent=[],downloads=[],createdBlobs=[],toasts=[],events=[];
    let timerSequence=0,canSend=true;
    class Element {
      constructor(tag='div',id=''){this.tagName=tag.toUpperCase();this.id=id;this.children=[];this.listeners={};this.dataset={};this.attributes={};this.style={};this.hidden=false;this.value='';this.textContent='';this.classes=new Set();this.classList={toggle:(key,on)=>on?this.classes.add(key):this.classes.delete(key),add:key=>this.classes.add(key)};}
      set id(id){this.elementId=id;if(id)elements.set(id,this);}
      get id(){return this.elementId;}
      set innerHTML(html){
        this.html=html;this.children=[];
        for(const match of html.matchAll(/id="([^"]+)"/g))elements.set(match[1],new Element('div',match[1]));
        for(const match of html.matchAll(/data-note-file="([^"]+)"/g)){const button=new Element('button');button.dataset.noteFile=match[1];fileButtons.push(button);this.children.push(button);}
      }
      get innerHTML(){return this.html||'';}
      appendChild(child){child.parent=this;this.children.push(child);return child;}
      append(...children){for(const child of children)this.appendChild(child);}
      replaceChildren(...children){this.children=[];this.append(...children);}
      replaceWith(element){elements.set(this.id,element);}
      cloneNode(){const element=new Element(this.tagName,this.id);element.html=this.html;return element;}
      setAttribute(key,value){this.attributes[key]=value;}
      addEventListener(type,fn){(this.listeners[type]??=[]).push(fn);}
      dispatch(type,overrides={}){const event={target:this,preventDefault(){},stopPropagation(){},...overrides};return Promise.all((this.listeners[type]||[]).map(fn=>fn(event)));}
      click(){if(this.tagName==='A')downloads.push({filename:this.download,href:this.href});return this.dispatch('click');}
      remove(){if(this.parent)this.parent.children=this.parent.children.filter(child=>child!==this);}
      querySelector(selector){if(!this.queries)this.queries={};if(!this.queries[selector])this.queries[selector]=new Element(selector.includes('button')?'button':'span');return this.queries[selector];}
      contains(target){return target===this||this.children.some(child=>child.contains?.(target));}
      closest(){return null;}
      focus(){}
      select(){}
      getBoundingClientRect(){return {left:500,top:150,right:540,bottom:190,width:40,height:40};}
    }
    const $=id=>{if(!elements.has(id))elements.set(id,new Element('div',id));return elements.get(id);};
    const document=new Element();document.body=new Element();document.createElement=tag=>new Element(tag);document.createTextNode=text=>({textContent:text});document.querySelectorAll=selector=>selector==='[data-note-file]'?fileButtons:[];
    const window={innerWidth:1280,innerHeight:800};
    const localStorage={setItem:(key,value)=>stored.set(key,value),getItem:key=>stored.get(key)||null};
    const URL={createObjectURL(blob){createdBlobs.push(blob);return 'blob:menu-test-'+createdBlobs.length;},revokeObjectURL(){}};
    function setTimeout(fn,delay){const id=++timerSequence;timers.set(id,{fn,delay});return id;}
    function clearTimeout(id){timers.delete(id);}
    function flushTimers(){const callbacks=[...timers.values()];timers.clear();for(const {fn} of callbacks)fn();}
    let notes=[{id:'a',title:'Algebra',paper:'grid'},{id:'b',title:'Biology',paper:'plain'}],currentDocumentId='a',currentNotebookId='a',notebookReady=true,titleTimer=null,isDrawing=false,inkPointerId=null,selectionRequest=null;
    $('note-title').value='Algebra';$('library-overlay').hidden=true;
    function finishActiveInput(){events.push('finish');}
    function showToast(message){toasts.push(message);}
    function closeOverlays(){$('library-overlay').hidden=true;}
    function openOverlay(id){closeOverlays();$(id).hidden=false;}
    function renderNotes(){}
    function sendWS(message){if(!canSend||!notebookReady)return false;events.push('send:'+message.type);sent.push(structuredClone(message));return true;}
    function handleServerMessage(message){
      if(message.type==='state_sync'){if(message.notes)notes=structuredClone(message.notes);currentDocumentId=message.documentId||currentDocumentId;currentNotebookId=message.notebookId||message.documentId||currentNotebookId;renderNotes();}
      else if(message.type==='note_ink_edit_result'&&message.requestId===selectionRequest)selectionRequest=null;
    }
    function updateAssistantConnection(connected){notebookReady=connected;}
  `,context);
  vm.runInContext(library+script,context);
  const run=code=>vm.runInContext(code,context);
  const read=code=>JSON.parse(run(`JSON.stringify((${code})??null)`));
  const message=msg=>run('handleServerMessage')(msg);
  const sync=(extra={})=>message({type:'state_sync',documentId:'a',saveState:'saved',savedAt:'2026-10-26T01:00:00Z',...extra});
  const saved=(extra={})=>message({type:'note_save_state',noteId:'a',state:'saved',savedAt:'2026-10-26T01:01:00Z',...extra});
  const checkpoint=()=>read('notebookSaveCheckpoint');
  const acknowledgeCheckpoint=(extra={})=>saved({saveCheckpoints:[checkpoint()],...extra});
  const fileResult=(extra={})=>message({type:'note_file_result',requestId:read('[...notebookFileRequests.keys()][0]'),ok:true,...extra});
  return {run,read,message,sync,saved,checkpoint,acknowledgeCheckpoint,fileResult};
}

test('connecting does not claim saved until the PC confirms a save state',()=>{
  const h=harness();assert.equal(h.read('notebookSaveState'),'connecting');
  h.run('updateAssistantConnection(true)');assert.equal(h.read('notebookSaveState'),'connecting');assert.equal(h.read("$('save-status').textContent"),'接続中');
  h.sync();assert.equal(h.read('notebookSaveState'),'saved');assert.equal(h.read("$('save-detail-title').textContent"),'PCに保存済み');
});

test('save acknowledgement for another note does not change the current save status',()=>{
  const h=harness();h.sync();h.run("sendWS({type:'note_title',id:'a',title:'New title'})");h.saved({noteId:'b'});
  assert.equal(h.read('notebookSaveState'),'dirty');assert.equal(h.read('notebookDeferredSave'),null);
});

test('stroke completion waits for its new checkpoint rather than an old saved ACK',()=>{
  const h=harness();h.sync();h.run("isDrawing=true;inkPointerId=1;sendWS({type:'stroke_start'})");h.saved();
  assert.equal(h.read('notebookSaveState'),'dirty');assert.notEqual(h.read('notebookDeferredSave'),null);
  h.run("isDrawing=false;inkPointerId=null;sendWS({type:'stroke_end'})");
  assert.equal(h.read('notebookSaveState'),'dirty');assert.equal(h.read('notebookDeferredSave'),null);
  assert.deepEqual(h.read('sent.at(-1)'),{type:'note_save_checkpoint',documentId:'a',requestId:h.checkpoint()});
  h.saved();assert.equal(h.read('notebookSaveState'),'dirty');
  h.acknowledgeCheckpoint();assert.equal(h.read('notebookSaveState'),'saved');assert.equal(h.checkpoint(),null);assert.equal(h.read('notebookDeferredSave'),null);
});

test('selection completion requests its own checkpoint and discards earlier deferred saved ACK',()=>{
  const h=harness();h.sync();h.run("selectionRequest='selection-1';sendWS({type:'note_ink_edit'})");h.saved();
  assert.equal(h.read('notebookSaveState'),'dirty');h.message({type:'note_ink_edit_result',requestId:'selection-1',ok:true});
  assert.equal(h.read('notebookSaveState'),'dirty');assert.equal(h.read('notebookDeferredSave'),null);assert.match(h.checkpoint(),/^save_/);
  h.saved();assert.equal(h.read('notebookSaveState'),'dirty');h.acknowledgeCheckpoint();assert.equal(h.read('notebookSaveState'),'saved');
});

test('a new mutation discards an earlier deferred saved ACK',()=>{
  const h=harness();h.sync();h.run("isDrawing=true;inkPointerId=1;sendWS({type:'stroke_start'})");h.saved();
  h.run("sendWS({type:'stroke_move'})");assert.equal(h.read('notebookDeferredSave'),null);
  h.run("isDrawing=false;inkPointerId=null;sendWS({type:'stroke_end'})");assert.equal(h.read('notebookSaveState'),'dirty');h.saved();assert.equal(h.read('notebookSaveState'),'dirty');h.acknowledgeCheckpoint();assert.equal(h.read('notebookSaveState'),'saved');
});

test('stroke_end alone does not incorrectly mark an unchanged note dirty',()=>{
  const h=harness();h.sync();h.run("sendWS({type:'stroke_end'})");assert.equal(h.read('notebookSaveState'),'saved');
  h.run("canSend=false;sendWS({type:'stroke_end'})");assert.equal(h.read('notebookSaveState'),'saved');
});

test('saved state_sync cannot claim an in-progress stroke is saved',()=>{
  const h=harness();h.sync();h.run("isDrawing=true;inkPointerId=1;sendWS({type:'stroke_start'})");h.sync();
  assert.equal(h.read('notebookSaveState'),'dirty');assert.notEqual(h.read('notebookDeferredSave'),null);
});

test('saved state_sync is deferred while a selection edit is awaiting its result',()=>{
  const h=harness();h.sync();h.run("selectionRequest='selection-1';sendWS({type:'note_ink_edit'})");h.sync();
  assert.equal(h.read('notebookSaveState'),'dirty');assert.notEqual(h.read('notebookDeferredSave'),null);
  h.message({type:'note_ink_edit_result',requestId:'selection-1',ok:true});assert.equal(h.read('notebookSaveState'),'dirty');h.acknowledgeCheckpoint();assert.equal(h.read('notebookSaveState'),'saved');
});

test('file results are correlated before a private download is created',()=>{
  const h=harness();h.sync();h.run("requestNotebookFile('pdf')");
  h.message({type:'note_file_result',requestId:'another-client-request',ok:true,data:'UERG',mime:'application/pdf',filename:'wrong.pdf'});
  assert.equal(h.read('downloads.length'),0);assert.equal(h.read('notebookFileRequests.size'),1);
  h.fileResult({data:'UERG',mime:'application/pdf',filename:'Algebra.pdf'});
  assert.equal(h.read('downloads.length'),1);assert.equal(h.read('downloads[0].filename'),'Algebra.pdf');assert.equal(h.read('createdBlobs.length'),1);assert.equal(h.read('notebookFileRequests.size'),0);
  assert.equal(h.read('fileButtons.every(button=>!button.disabled)'),true);
});

test('successful backup import reports how many notes arrived without downloading a file',()=>{
  const h=harness();h.sync();h.run("requestNotebookFile('import',{data:'e30='})");h.fileResult({importedCount:3});
  assert.equal(h.read('downloads.length'),0);assert.match(h.read("$('notebook-file-message').textContent"),/3 件.*元のノートも残/);assert.equal(h.read('toasts.at(-1)'),'バックアップを取り込みました');
});

test('failed correlated file requests show the backend reason and reenable file controls',()=>{
  const h=harness();h.sync();h.run("requestNotebookFile('backup_all')");h.fileResult({ok:false,message:'バックアップを保存できません'});
  assert.equal(h.read('notebookFileRequests.size'),0);assert.equal(h.read('fileButtons.every(button=>!button.disabled)'),true);assert.equal(h.read("$('notebook-file-message').textContent"),'バックアップを保存できません');
});

test('disconnect releases pending file requests and removes saved status',()=>{
  const h=harness();h.sync();h.run("requestNotebookFile('backup_all')");const requestId=h.read('[...notebookFileRequests.keys()][0]');h.run('updateAssistantConnection(false)');
  assert.equal(h.read('notebookSaveState'),'offline');assert.equal(h.read('notebookFileRequests.size'),0);assert.equal(h.read('fileButtons.every(button=>!button.disabled)'),true);assert.match(h.read("$('notebook-file-message').textContent"),/接続が切れ/);
  h.message({type:'note_file_result',requestId,ok:true,data:'e30=',mime:'application/json',filename:'stale.spennotes'});assert.equal(h.read('downloads.length'),0);
});

test('library switching flushes the edited title before note_select and cancels the title timer',()=>{
  const h=harness();h.sync();h.run(`
    $('note-title').value='Edited title';
    titleTimer=setTimeout(()=>sendWS({type:'note_title',id:'a',title:'late stale title'}),450);
    beginNotebookLibraryNavigation('select','b');
  `);
  assert.deepEqual(h.read("sent.filter(message=>message.type!=='note_save_checkpoint')"),[{type:'note_title',id:'a',title:'Edited title'},{type:'note_select',id:'b'}]);
  assert.deepEqual(h.read('sent.map(message=>message.type)'),['note_title','note_save_checkpoint','note_select']);
  assert.equal(h.read('timers.size'),0);h.run('flushTimers()');assert.equal(h.read('sent.length'),3);
});

test('each new standalone mutation advances the checkpoint and old acknowledgements stay dirty',()=>{
  const h=harness();h.sync();h.run("sendWS({type:'note_title',id:'a',title:'Renamed'})");const first=h.checkpoint();
  h.run("sendWS({type:'note_paper',paper:'ruled'})");const second=h.checkpoint();assert.notEqual(first,second);
  h.saved({saveCheckpoints:[first]});assert.equal(h.read('notebookSaveState'),'dirty');assert.equal(h.checkpoint(),second);
  h.saved({saveCheckpoints:[first,second]});assert.equal(h.read('notebookSaveState'),'saved');assert.equal(h.checkpoint(),null);
  h.run("sendWS({type:'clear'})");const third=h.checkpoint();assert.notEqual(third,first);assert.notEqual(third,second);
  h.saved({saveCheckpoints:[first,second]});assert.equal(h.read('notebookSaveState'),'dirty');
  h.saved({saveCheckpoints:[first,second,third]});assert.equal(h.read('notebookSaveState'),'saved');
});

test('erase completion creates a checkpoint only while a change is waiting for save',()=>{
  const h=harness();h.sync();h.run("sendWS({type:'erase_end'})");assert.equal(h.checkpoint(),null);
  h.run("sendWS({type:'erase'});sendWS({type:'erase_end'})");assert.match(h.checkpoint(),/^save_/);assert.equal(h.read('notebookSaveState'),'dirty');
  h.saved();assert.equal(h.read('notebookSaveState'),'dirty');h.acknowledgeCheckpoint();assert.equal(h.read('notebookSaveState'),'saved');
});

test('disconnect clears the required checkpoint and deferred ACK before a new connection',()=>{
  const h=harness();h.sync();h.run("sendWS({type:'undo'})");const oldCheckpoint=h.checkpoint();
  h.saved();assert.notEqual(h.read('notebookDeferredSave'),null);h.run('updateAssistantConnection(false)');
  assert.equal(h.checkpoint(),null);assert.equal(h.read('notebookDeferredSave'),null);assert.equal(h.read('notebookSaveState'),'offline');
  h.run('updateAssistantConnection(true)');assert.equal(h.read('notebookSaveState'),'connecting');h.sync();
  h.run("sendWS({type:'redo'})");const nextCheckpoint=h.checkpoint();assert.notEqual(nextCheckpoint,oldCheckpoint);
  h.saved({saveCheckpoints:[oldCheckpoint]});assert.equal(h.read('notebookSaveState'),'dirty');
  h.acknowledgeCheckpoint();assert.equal(h.read('notebookSaveState'),'saved');
});

test('title flush on a later page edits the notebook title while its checkpoint targets that page',()=>{
  const h=harness();h.sync({documentId:'page2',notebookId:'bookA',notes:[{id:'bookA',title:'Book title'},{id:'bookB',title:'Other book'}]});
  h.run("$('note-title').value='Book title';flushNotebookTitle()");assert.equal(h.read('sent.length'),0,'an unchanged notebook title needs no write');
  h.run("$('note-title').value='Edited book title';flushNotebookTitle()");
  assert.deepEqual(h.read('sent[0]'),{type:'note_title',id:'bookA',title:'Edited book title'});assert.equal(h.read('sent[1].type'),'note_save_checkpoint');assert.equal(h.read('sent[1].documentId'),'page2');
});

test('renaming from a later page opens and submits the containing notebook title',()=>{
  const h=harness();h.sync({documentId:'page2',notebookId:'bookA',notes:[{id:'bookA',title:'Book title'}]});h.run("$('note-title').value='Book title';$('menu-rename').dispatch('click')");
  assert.equal(h.read('notebookLibraryRenameId'),'bookA');assert.equal(h.read("$('library-rename-title').value"),'Book title');
  h.run("$('library-rename-title').value='Renamed book';$('library-rename-form').dispatch('submit')");
  const request=h.read("sent.findLast(message=>message.type==='note_library')");assert.equal(request.action,'rename');assert.equal(request.id,'bookA');assert.equal(request.title,'Renamed book');
});

for(const action of ['duplicate','trash'])test(`${action} from a later page targets the containing notebook`,()=>{
  const h=harness();h.sync({documentId:'page2',notebookId:'bookA',notes:[{id:'bookA',title:'Book title'}]});h.run(`$('note-title').value='Book title';$('menu-${action}').dispatch('click')`);
  const request=h.read("sent.findLast(message=>message.type==='note_library')");assert.equal(request.action,action);assert.equal(request.id,'bookA');assert.equal(h.read('currentDocumentId'),'page2');
});

test('switching notebooks from a later page flushes the old notebook title before selecting the new notebook',()=>{
  const h=harness();h.sync({documentId:'page2',notebookId:'bookA',notes:[{id:'bookA',title:'Book title'},{id:'bookB',title:'Other book'}]});
  h.run("$('note-title').value='Updated old notebook';beginNotebookLibraryNavigation('select','bookB')");
  assert.deepEqual(h.read("sent.filter(message=>message.type!=='note_save_checkpoint')"),[{type:'note_title',id:'bookA',title:'Updated old notebook'},{type:'note_select',id:'bookB'}]);
  assert.equal(h.read('sent[1].documentId'),'page2');h.message({type:'state_sync',documentId:'pageB2',notebookId:'bookB',saveState:'saved'});assert.equal(h.read('notebookLibraryPending'),null);assert.equal(h.read('currentNotebookId'),'bookB');
});
