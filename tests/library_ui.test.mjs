import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';

const source=fs.readFileSync(new URL('../notesync/TabletLibrary.py',import.meta.url),'utf8');
const model=source.split('LIBRARY_MODEL_SCRIPT = r"""')[1].split('"""')[0];
const script=model+source.split('LIBRARY_SCRIPT = LIBRARY_MODEL_SCRIPT + r"""')[1].split('"""')[0];

function harness(){
  const context=vm.createContext({structuredClone});
  vm.runInContext(`
    const elements=new Map(),stored=new Map(),sent=[],events=[],toasts=[];
    class Element {
      constructor(tag='div',id=''){this.tagName=tag.toUpperCase();this.id=id;this.children=[];this.listeners={};this.dataset={};this.attributes={};this.style={};this.hidden=false;this.value='';this.textContent='';this.classes=new Set();this.classList={toggle:(key,on)=>on?this.classes.add(key):this.classes.delete(key),add:key=>this.classes.add(key)};}
      set id(id){this.elementId=id;if(id)elements.set(id,this);}
      get id(){return this.elementId;}
      set innerHTML(html){this.html=html;this.children=[];for(const match of html.matchAll(/id="([^"]+)"/g))elements.set(match[1],new Element('div',match[1]));}
      get innerHTML(){return this.html||'';}
      appendChild(child){this.children.push(child);return child;}
      append(...children){this.children.push(...children);}
      replaceChildren(...children){this.children=children;}
      cloneNode(){const element=new Element(this.tagName,this.id);element.html=this.html;return element;}
      replaceWith(element){elements.set(this.id,element);}
      setAttribute(key,value){this.attributes[key]=value;}
      addEventListener(type,fn){(this.listeners[type]??=[]).push(fn);}
      dispatch(type,overrides={}){const event={target:this,preventDefault(){},stopPropagation(){},...overrides};for(const fn of this.listeners[type]||[])fn(event);}
      contains(target){return target===this||this.children.some(child=>child.contains?.(target));}
      closest(){return null;}
      focus(){this.focused=true;}
      select(){this.selected=true;}
      getBoundingClientRect(){return {left:500,top:150,right:540,bottom:190,width:40,height:40};}
    }
    const $=id=>{if(!elements.has(id))elements.set(id,new Element('div',id));return elements.get(id);};
    const document=new Element();document.body=new Element();document.createElement=tag=>new Element(tag);
    const window={innerWidth:1280,innerHeight:800};
    const localStorage={setItem:(key,value)=>stored.set(key,value),getItem:key=>stored.get(key)||null};
    let notes=[
      {id:'a',title:'Algebra',paper:'grid',createdAt:'2026-10-25T00:00:00Z',updatedAt:'2026-10-26T01:00:00Z',strokeCount:12,textCount:2},
      {id:'b',title:'Biology',paper:'ruled',createdAt:'2026-10-24T00:00:00Z',updatedAt:'2026-10-25T01:00:00Z',strokeCount:4,textCount:0},
      {id:'c',title:'Chemistry',paper:'plain',createdAt:'2026-10-23T00:00:00Z',updatedAt:'2026-10-26T02:00:00Z',deletedAt:'2026-10-26T02:00:00Z',strokeCount:3,textCount:1}
    ],currentDocumentId='a',currentNotebookId='a',notebookReady=true;
    function finishActiveInput(){events.push('finish');}
    function flushNotebookTitle(){events.push('flush');}
    function showToast(message){toasts.push(message);}
    function closeOverlays(){$('library-overlay').hidden=true;}
    function openOverlay(id){closeOverlays();$(id).hidden=false;}
    function renderNotes(){}
    function sendWS(message){if(!notebookReady)return false;events.push('send:'+message.type);sent.push(structuredClone(message));return true;}
    function handleServerMessage(msg){if(msg.type==='state_sync'){if(msg.notes)notes=structuredClone(msg.notes);currentDocumentId=msg.documentId||currentDocumentId;currentNotebookId=msg.notebookId||msg.documentId||currentNotebookId;renderNotes();}}
    function updateExtensionConnection(connected){notebookReady=connected;}
    $('library-overlay').hidden=true;
  `,context);
  vm.runInContext(script,context);
  const run=code=>vm.runInContext(code,context);
  const read=code=>JSON.parse(run(`JSON.stringify((${code})??null)`));
  const click=id=>run(`$('${id}').dispatch('click')`);
  const message=msg=>run('handleServerMessage')(msg);
  const result=(ok=true,extra={})=>message({type:'note_library_result',requestId:read('notebookLibraryPending.requestId'),ok,...extra});
  return {run,read,click,message,result};
}

test('library filters normal/trash notes, searches titles, and sorts without changing metadata order',()=>{
  const h=harness();
  assert.deepEqual(h.read('notebookLibraryNotes(notes).map(note=>note.id)'),['a','b']);
  assert.deepEqual(h.read("notebookLibraryNotes(notes,{trash:true}).map(note=>note.id)"),['c']);
  assert.deepEqual(h.read("notebookLibraryNotes(notes,{query:'  ALG  '}).map(note=>note.id)"),['a']);
  assert.deepEqual(h.read('notes.map(note=>note.id)'),['a','b','c']);
  assert.deepEqual(h.read("notebookLibraryNotes([...notes].reverse(),{sort:'title'}).map(note=>note.id)"),['a','b']);
});

test('library opens from the existing button and renders paper cards with a current-note marker',()=>{
  const h=harness();h.click('open-library');
  assert.equal(h.read("$('library-overlay').hidden"),false);
  assert.equal(h.read("$('notebook-list').children.length"),2);
  assert.equal(h.read("$('notebook-list').children[0].classes.has('current')"),true);
  assert.equal(h.read("$('library-notes-count').textContent"),2);assert.equal(h.read("$('library-trash-count').textContent"),1);
});

test('opening a note waits for its confirmed state_sync before closing the library',()=>{
  const h=harness();h.click('open-library');h.run("$('notebook-list').children.find(card=>card.dataset.noteId==='b').children[0].dispatch('click')");
  assert.deepEqual(h.read('sent.at(-1)'),{type:'note_select',id:'b'});assert.equal(h.read("$('library-overlay').hidden"),false);
  h.message({type:'state_sync',documentId:'a'});assert.equal(h.read("$('library-overlay').hidden"),false);
  h.message({type:'state_sync',documentId:'b'});assert.equal(h.read("$('library-overlay').hidden"),true);assert.equal(h.read('notebookLibraryPending'),null);
});

test('creating a note flushes its pending title and waits for a newly created document',()=>{
  const h=harness();h.click('open-library');h.run('events.length=0');h.click('new-note');
  assert.deepEqual(h.read('events'),['finish','flush','send:note_new']);assert.equal(h.read("$('library-overlay').hidden"),false);
  h.message({type:'state_sync',documentId:'a'});assert.equal(h.read("$('library-overlay').hidden"),false);
  h.message({type:'state_sync',documentId:'new-note-id'});assert.equal(h.read("$('library-overlay').hidden"),true);
});

test('search and trash tabs expose separate empty states and recoverable notes',()=>{
  const h=harness();h.click('open-library');h.run("$('library-search').value='missing';$('library-search').dispatch('input')");
  assert.equal(h.read("$('notebook-list').children[0].children[0].textContent"),'見つかりませんでした');
  h.run("$('library-search').value='';$('library-search').dispatch('input')");h.click('library-trash-tab');
  assert.equal(h.read("$('notebook-list').children.length"),1);assert.equal(h.read("$('notebook-list').children[0].dataset.noteId"),'c');
  h.run("$('notebook-list').children[0].children[1].dispatch('click')");
  assert.equal(h.read('sent.at(-1).action'),'restore');assert.equal(h.read('sent.at(-1).id'),'c');
});

test('rename sends a correlated action and preserves the old title until authoritative state arrives',()=>{
  const h=harness();h.run("openNotebookRename('a')");
  h.run("$('library-rename-title').value='Renamed';$('library-rename-form').dispatch('submit')");
  assert.equal(h.read('notes[0].title'),'Algebra');assert.equal(h.read('sent.at(-1).type'),'note_library');
  assert.equal(h.read('sent.at(-1).action'),'rename');assert.equal(h.read('sent.at(-1).title'),'Renamed');assert.match(h.read('sent.at(-1).requestId'),/^library_/);
  h.result();assert.equal(h.read('notebookLibraryRename.hidden'),true);assert.equal(h.read('notes[0].title'),'Algebra');
});

test('rename errors keep the dialog editable and show the backend reason',()=>{
  const h=harness();h.run("openNotebookRename('a')");h.run("$('library-rename-title').value='Renamed';$('library-rename-form').dispatch('submit')");h.result(false,{message:'保存できません'});
  assert.equal(h.read('notebookLibraryRename.hidden'),false);assert.equal(h.read("$('library-rename-save').disabled"),false);assert.equal(h.read("$('library-rename-error').textContent"),'保存できません');assert.equal(h.read('notebookLibraryPending'),null);
});

test('the card menu offers rename, duplicate and reversible trash actions',()=>{
  const h=harness();h.click('open-library');h.run("$('notebook-list').children[0].children[1].dispatch('click')");
  assert.deepEqual(h.read('notebookLibraryMenu.children.map(button=>button.textContent)'),['名前を変更','科目を変更','複製','ゴミ箱へ移動']);
  h.run("notebookLibraryMenu.children[2].dispatch('click')");assert.equal(h.read('sent.at(-1).action'),'duplicate');h.result();
  h.run("requestNotebookLibraryAction('trash','a')");assert.equal(h.read('sent.at(-1).action'),'trash');assert.equal(h.read('notes[0].deletedAt'),null);
});

test('offline navigation keeps the library open and provides a retry message',()=>{
  const h=harness();h.click('open-library');h.run('updateExtensionConnection(false)');h.run("beginNotebookLibraryNavigation('select','b')");
  assert.equal(h.read('sent.length'),0);assert.equal(h.read('notebookLibraryPending'),null);assert.equal(h.read("$('library-overlay').hidden"),false);assert.equal(h.read("$('new-note').disabled"),true);assert.match(h.read("$('library-message').textContent"),/PCに接続/);
});

test('view/sort changes persist in the browser without affecting note data',()=>{
  const h=harness();h.click('library-list');h.run("$('library-sort').value='title';$('library-sort').dispatch('change')");
  assert.equal(h.read("stored.get('notesync_library_view')"),'list');assert.equal(h.read("stored.get('notesync_library_sort')"),'title');assert.equal(h.read("$('notebook-list').classes.has('library-list-view')"),true);
});

test('the current notebook card stays marked while a later page has its own document ID',()=>{
  const h=harness();h.run("notes=[{id:'bookA',title:'Algebra',paper:'grid'},{id:'bookB',title:'Biology',paper:'plain'}];currentDocumentId='page2';currentNotebookId='bookA'");h.click('open-library');
  assert.equal(h.read('notebookLibraryCurrentId()'),'bookA');
  assert.equal(h.read("$('notebook-list').children.find(card=>card.dataset.noteId==='bookA').classes.has('current')"),true);
  assert.equal(h.read("$('notebook-list').children.find(card=>card.dataset.noteId==='bookB').classes.has('current')"),false);
  assert.equal(h.read("$('notebook-list').children.find(card=>card.dataset.noteId==='bookA').children[0].children.some(child=>child.className==='library-current-badge')"),true);
});

test('selecting a notebook completes when its active page ID differs from its notebook ID',()=>{
  const h=harness();h.run("notes=[{id:'bookA',title:'Algebra'},{id:'bookB',title:'Biology'}];currentDocumentId='page2';currentNotebookId='bookA'");h.click('open-library');
  h.run("$('notebook-list').children.find(card=>card.dataset.noteId==='bookB').children[0].dispatch('click')");assert.deepEqual(h.read('sent.at(-1)'),{type:'note_select',id:'bookB'});
  h.message({type:'state_sync',documentId:'pageB2',notebookId:'bookB'});
  assert.equal(h.read('currentDocumentId'),'pageB2');assert.equal(h.read('currentNotebookId'),'bookB');assert.equal(h.read('notebookLibraryPending'),null);assert.equal(h.read("$('library-overlay').hidden"),true);
  assert.equal(h.read("$('notebook-list').children.find(card=>card.dataset.noteId==='bookB').classes.has('current')"),true);
});

test('new-notebook navigation cannot mistake another page of an existing notebook for a new notebook',()=>{
  const h=harness();h.run("notes=[{id:'bookA',title:'Algebra'},{id:'bookB',title:'Biology'}];currentDocumentId='page2';currentNotebookId='bookA'");h.click('open-library');h.click('new-note');
  h.message({type:'state_sync',documentId:'page3',notebookId:'bookA'});assert.notEqual(h.read('notebookLibraryPending'),null);assert.equal(h.read("$('library-overlay').hidden"),false);
  h.message({type:'state_sync',documentId:'pageB2',notebookId:'bookB'});assert.notEqual(h.read('notebookLibraryPending'),null);assert.equal(h.read("$('library-overlay').hidden"),false);
  h.message({type:'state_sync',documentId:'pageD2',notebookId:'bookD',notes:[{id:'bookA',title:'Algebra'},{id:'bookB',title:'Biology'},{id:'bookD',title:'New notebook'}]});
  assert.equal(h.read('notebookLibraryPending'),null);assert.equal(h.read("$('library-overlay').hidden"),true);assert.equal(h.read('notebookLibraryCurrentId()'),'bookD');
});


test('course filtering, moving and creating retain the selected course',()=>{
  const h=harness();h.run("notes[0].course='力学';notes[1].course='代数';renderNotebookLibrary()");
  h.run("$('library-course').value='力学';$('library-course').dispatch('change')");
  assert.equal(h.read("$('notebook-list').children.length"),1);
  h.run("openNotebookRename('a','course');$('library-rename-title').value='流体力学';$('library-rename-form').dispatch('submit')");
  assert.equal(h.read('sent.at(-1).action'),'course');assert.equal(h.read('sent.at(-1).course'),'流体力学');
  h.result();h.run("beginNotebookLibraryNavigation('new')");assert.equal(h.read('sent.at(-1).course'),'力学');
});
