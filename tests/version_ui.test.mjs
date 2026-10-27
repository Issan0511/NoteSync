import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';

const script=fs.readFileSync(new URL('../notesync/TabletVersion.py',import.meta.url),'utf8')
  .split('VERSION_SCRIPT = r"""')[1].split('"""')[0].replace('__CLIENT_BUILD__','test-build-v1');

function harness(){
  const context=vm.createContext({structuredClone});
  vm.runInContext(`
    const elements=new Map(),sent=[],events=[],handled=[],lockChecks=[];
    let canSend=true,connected=true,reloads=0,time=1000;
    const draft={title:'途中のノート',strokes:[{points:[[.2,.3,.5],[.4,.5,.7]]}],texts:['保存してから更新する']};
    class Element {
      constructor(tag='div'){this.tagName=tag;this.children=[];this.listeners={};this.listenerOptions={};this.style={};this.attributes={};this.hidden=false;this.disabled=false;this.textContent='';this.inert=false;this.captures=new Set();}
      set id(id){this.elementId=id;elements.set(id,this);}
      get id(){return this.elementId;}
      append(...children){this.children.push(...children);}
      appendChild(child){this.children.push(child);return child;}
      setAttribute(name,value){this.attributes[name]=value;}
      addEventListener(type,fn,options){(this.listeners[type]??=[]).push(fn);(this.listenerOptions[type]??=[]).push(options);}
      hasPointerCapture(id){return this.captures.has(id);}
      releasePointerCapture(id){this.captures.delete(id);events.push('release:'+id);}
      dispatch(type,overrides={}){
        const event={type,target:this,cancelable:true,defaultPrevented:false,propagationStopped:false,preventDefault(){this.defaultPrevented=true;},stopImmediatePropagation(){this.propagationStopped=true;},...overrides};
        for(const node of new Set([window,document,this])){for(const fn of node.listeners[type]||[]){fn(event);if(event.propagationStopped)break;}if(event.propagationStopped)break;}
        return event;
      }
      click(){if(!this.disabled)return this.dispatch('click');}
    }
    const window=new Element('window'),document=new Element('document');document.body=new Element('body');document.createElement=tag=>new Element(tag);
    const notebookRoot=new Element('main'),alreadyLockedPanel=new Element('section'),canvas=new Element('canvas'),stage=new Element('stage');
    alreadyLockedPanel.inert=true;notebookRoot.append(canvas);document.body.append(notebookRoot,alreadyLockedPanel);
    const viewTouches=new Map();let pinchBaseline=null,selectionBusy=false,selectionCleared=0;
    function selectionPointerActive(){return selectionBusy;}
    function clearInkSelection(){selectionBusy=false;selectionCleared++;events.push('clear-selection');}
    const location={reload(){reloads++;events.push('reload');}};
    const NativeDate=Date;class ClockDate extends NativeDate{static now(){return time;}};Date=ClockDate;
    function finishActiveInput(){lockChecks.push(['finish',notebookUpdateInputLocked]);events.push('finish');}
    function flushNotebookTitle(){lockChecks.push(['flush-title',notebookUpdateInputLocked]);events.push('flush-title');}
    function sendWS(message){lockChecks.push(['send',notebookUpdateInputLocked]);events.push('send:'+message.type);if(!canSend||!connected)return false;sent.push(structuredClone(message));return true;}
    function handleServerMessage(message){handled.push(structuredClone(message));}
    function updateExtensionConnection(value){connected=value;events.push('connection:'+value);}
  `+script,context);
  const run=code=>vm.runInContext(code,context);
  const read=code=>JSON.parse(run(`JSON.stringify((${code})??null)`));
  const click=()=>run('notebookUpdateButton.click()');
  const message=msg=>run('handleServerMessage')(msg);
  const result=(ok=true,extra={})=>message({type:'note_library_result',requestId:read('notebookUpdateRequest'),ok,...extra});
  return {run,read,click,message,result};
}

test('a matching or missing server build leaves the banner hidden, while a different build shows it',()=>{
  const h=harness();h.run("checkNotebookClientVersion(undefined);checkNotebookClientVersion('test-build-v1')");assert.equal(h.read('notebookUpdateBanner.hidden'),true);
  h.run("checkNotebookClientVersion('server-build-v2')");assert.equal(h.read('notebookUpdateBanner.hidden'),false);assert.equal(h.read('notebookUpdateBanner.attributes.role'),'status');
});

test('update finishes input and flushes title before sending a correlated save request',()=>{
  const h=harness();const original=h.read('draft');h.click();
  assert.deepEqual(h.read('events'),['finish','flush-title','send:note_save']);assert.equal(h.read('sent.length'),1);
  assert.equal(h.read('sent[0].type'),'note_save');assert.equal(h.read('sent[0].requestId'),h.read('notebookUpdateRequest'));
  assert.equal(h.read('notebookUpdateButton.disabled'),true);assert.equal(h.read('reloads'),0);assert.deepEqual(h.read('draft'),original);
  assert.deepEqual(h.read('lockChecks'),[['finish',false],['flush-title',false],['send',true]]);
  assert.equal(h.read('notebookUpdateInputLocked'),true);assert.equal(h.read('notebookRoot.inert'),true);assert.equal(h.read('notebookUpdateBanner.inert'),false);
  h.click();assert.equal(h.read('sent.length'),1,'disabled button should not create duplicate save requests');
});

test('only a successful result for the pending update request reloads the page',()=>{
  const h=harness();h.click();h.message({type:'note_library_result',requestId:'another-client',ok:true});assert.equal(h.read('reloads'),0);assert.equal(h.read('notebookUpdateButton.disabled'),true);
  h.message({type:'note_saved',requestId:h.read('notebookUpdateRequest')});assert.equal(h.read('reloads'),0);
  h.result();assert.equal(h.read('reloads'),1);assert.equal(h.read('notebookUpdateRequest'),null);assert.equal(h.read('handled.length'),3);
  assert.equal(h.read('notebookUpdateInputLocked'),true);assert.equal(h.read('notebookRoot.inert'),true,'keep the input lock until reload finishes');
});

test('save failure retains the draft, explains the failure and enables retry',()=>{
  const h=harness();const original=h.read('draft');h.click();h.result(false,{message:'PCに保存できません'});
  assert.equal(h.read('reloads'),0);assert.equal(h.read('notebookUpdateRequest'),null);assert.equal(h.read('notebookUpdateButton.disabled'),false);assert.equal(h.read('notebookUpdateText.textContent'),'PCに保存できません');assert.deepEqual(h.read('draft'),original);
  assert.equal(h.read('notebookUpdateInputLocked'),false);assert.equal(h.read('notebookRoot.inert'),false);assert.equal(h.read('alreadyLockedPanel.inert'),true);
  h.run('time+=100');h.click();assert.equal(h.read('sent.length'),2);h.result();assert.equal(h.read('reloads'),1);
});

test('failed transmission retains the draft and leaves the update action retryable',()=>{
  const h=harness();const original=h.read('draft');h.run('canSend=false');h.click();
  assert.equal(h.read('sent.length'),0);assert.equal(h.read('notebookUpdateRequest'),null);assert.equal(h.read('notebookUpdateButton.disabled'),false);assert.equal(h.read('reloads'),0);assert.deepEqual(h.read('draft'),original);
  assert.equal(h.read('notebookUpdateInputLocked'),false);assert.equal(h.read('notebookRoot.inert'),false);assert.equal(h.read('alreadyLockedPanel.inert'),true);
  h.run('canSend=true;time+=100');h.click();h.result();assert.equal(h.read('reloads'),1);
});

test('disconnect releases an update request and ignores its late save result',()=>{
  const h=harness();const original=h.read('draft');h.click();const oldId=h.read('notebookUpdateRequest');h.run('updateExtensionConnection(false)');
  assert.equal(h.read('notebookUpdateRequest'),null);assert.equal(h.read('notebookUpdateButton.disabled'),false);assert.match(h.read('notebookUpdateButton.textContent'),/再接続/);assert.deepEqual(h.read('draft'),original);
  assert.equal(h.read('notebookUpdateInputLocked'),false);assert.equal(h.read('notebookRoot.inert'),false);assert.equal(h.read('alreadyLockedPanel.inert'),true);
  h.message({type:'note_library_result',requestId:oldId,ok:true});assert.equal(h.read('reloads'),0);
  h.run('updateExtensionConnection(true);time+=100');h.click();assert.notEqual(h.read('notebookUpdateRequest'),oldId);h.result();assert.equal(h.read('reloads'),1);
});

test('an unsolicited result without any pending update never reloads the page',()=>{
  const h=harness();h.message({type:'note_library_result',requestId:null,ok:true});h.message({type:'note_library_result',ok:true});
  assert.equal(h.read('reloads'),0);assert.equal(h.read('notebookUpdateRequest'),null);
});

test('retry request IDs remain unique even when the device clock has not advanced',()=>{
  const h=harness();h.click();const first=h.read('notebookUpdateRequest');h.result(false);h.click();const second=h.read('notebookUpdateRequest');
  assert.notEqual(first,second);h.message({type:'note_library_result',requestId:first,ok:true});assert.equal(h.read('reloads'),0);h.result();assert.equal(h.read('reloads'),1);
});

test('pointer, keyboard and editing input cannot reach notebook handlers while update save is pending',()=>{
  const h=harness();h.run(`
    let mutations=0;
    for(const type of ['pointerdown','pointermove','mousedown','touchstart','touchmove','click','dblclick','keydown','keypress','beforeinput','input','change','paste','cut','drop','submit','wheel'])canvas.addEventListener(type,()=>{mutations++;draft.title='unsaved change';});
  `);const original=h.read('draft');h.click();
  for(const type of ['pointerdown','pointermove','mousedown','touchstart','touchmove','click','dblclick','keydown','keypress','beforeinput','input','change','paste','cut','drop','submit','wheel']){
    const event=h.run(`canvas.dispatch(${JSON.stringify(type)})`);assert.equal(event.defaultPrevented,true,type+' default action should be prevented');assert.equal(event.propagationStopped,true,type+' must stop before tablet handlers');
  }
  assert.equal(h.read('mutations'),0);assert.deepEqual(h.read('draft'),original);assert.equal(h.read("window.listenerOptions.pointerdown[0].capture"),true);assert.equal(h.read("window.listenerOptions.touchmove[0].passive"),false);
  h.message({type:'note_texts_updated',documentId:'a',texts:[{text:'server annotation'}]});assert.equal(h.read('handled.at(-1).type'),'note_texts_updated','WebSocket annotation rendering must continue while user input is locked');
});

test('pointer release cleanup still runs, and normal input resumes after a failed update',()=>{
  const h=harness();h.run("let releases=0,mutations=0;canvas.addEventListener('pointerup',()=>releases++);canvas.addEventListener('pointerdown',()=>mutations++)");h.click();
  const release=h.run("canvas.dispatch('pointerup')");assert.equal(release.propagationStopped,false);assert.equal(h.read('releases'),1);
  h.result(false);const down=h.run("canvas.dispatch('pointerdown')");assert.equal(down.propagationStopped,false);assert.equal(h.read('mutations'),1);assert.equal(h.read('notebookUpdateInertNodes.size'),0);
});

test('starting an update cancels an existing selection gesture and releases pinch pointers before locking',()=>{
  const h=harness();h.run("selectionBusy=true;viewTouches.set(8,{x:100,y:200});stage.captures.add(8);pinchBaseline={distance:40}");h.click();
  assert.equal(h.read('selectionCleared'),1);assert.equal(h.read('selectionBusy'),false);assert.equal(h.read('viewTouches.size'),0);assert.equal(h.read('stage.captures.size'),0);assert.equal(h.read('pinchBaseline'),null);
  assert.deepEqual(h.read('events'),['finish','clear-selection','release:8','flush-title','send:note_save']);
});
