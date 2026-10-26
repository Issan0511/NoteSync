"""Detect a stale, still-open tablet page after the desktop host is updated."""

VERSION_SCRIPT = r"""
const notebookClientBuild='__CLIENT_BUILD__';
let notebookUpdateRequest=null,notebookUpdateSequence=0,notebookUpdateInputLocked=false;
const notebookUpdateInertNodes=new Map();
const notebookUpdateBanner=document.createElement('div');
notebookUpdateBanner.id='notebook-update-banner';notebookUpdateBanner.hidden=true;
notebookUpdateBanner.style.cssText='position:fixed;left:50%;bottom:30px;transform:translateX(-50%);width:min(560px,calc(100vw - 28px));padding:16px 18px;background:#fff;border:1px solid #dbe4f0;border-radius:17px;box-shadow:0 7px 30px #25345124;z-index:190;color:#536781;font-size:12px;line-height:1.8';
notebookUpdateBanner.setAttribute('role','status');
const notebookUpdateText=document.createElement('p');notebookUpdateText.textContent='ノートアプリが更新されました。保存して画面を更新すると、新しい書き込みと数式を表示できます。';notebookUpdateText.style.margin='0 0 10px';
const notebookUpdateButton=document.createElement('button');notebookUpdateButton.type='button';notebookUpdateButton.className='save-primary';notebookUpdateButton.textContent='保存して画面を更新';notebookUpdateBanner.append(notebookUpdateText,notebookUpdateButton);document.body.appendChild(notebookUpdateBanner);
function checkNotebookClientVersion(serverBuild){if(typeof serverBuild==='string'&&serverBuild!==notebookClientBuild)notebookUpdateBanner.hidden=false;}
function lockNotebookUpdateInput(locked){
  if(notebookUpdateInputLocked===locked)return;notebookUpdateInputLocked=locked;
  if(locked){
    for(const node of Array.from(document.body.children)){
      if(node===notebookUpdateBanner)continue;
      notebookUpdateInertNodes.set(node,node.inert);node.inert=true;
    }
  }else{
    for(const [node,inert] of notebookUpdateInertNodes)node.inert=inert;
    notebookUpdateInertNodes.clear();
  }
  notebookUpdateBanner.setAttribute('aria-busy',String(locked));
}
// Capture on window, ahead of the tablet's document/stage/canvas handlers.
// Release/cancel events still reach existing gesture cleanup after ink has
// been finished, so a failed update cannot leave a captured pointer stuck.
for(const type of ['pointerdown','pointermove','mousedown','mousemove','touchstart','touchmove','click','dblclick','contextmenu','wheel','keydown','keypress','beforeinput','input','change','compositionstart','compositionupdate','compositionend','submit','paste','cut','drop','dragstart']){
  window.addEventListener(type,event=>{
    if(!notebookUpdateInputLocked)return;
    if(event.cancelable!==false)event.preventDefault();
    event.stopImmediatePropagation();
  },{capture:true,passive:false});
}
notebookUpdateButton.addEventListener('click',()=>{
  if(notebookUpdateRequest||notebookUpdateInputLocked)return;
  finishActiveInput();
  if(typeof selectionPointerActive==='function'&&selectionPointerActive()&&typeof clearInkSelection==='function')clearInkSelection();
  if(typeof viewTouches!=='undefined'){
    const pointers=[...viewTouches.keys()];viewTouches.clear();
    if(typeof pinchBaseline!=='undefined')pinchBaseline=null;
    for(const id of pointers)if(typeof stage!=='undefined'&&stage.hasPointerCapture(id))stage.releasePointerCapture(id);
  }
  if(typeof flushNotebookTitle==='function')flushNotebookTitle();
  lockNotebookUpdateInput(true);
  const requestId='update_'+Date.now().toString(36)+'_'+(++notebookUpdateSequence);notebookUpdateRequest=requestId;
  if(!sendWS({type:'note_save',requestId})){notebookUpdateRequest=null;lockNotebookUpdateInput(false);return;}
  notebookUpdateButton.disabled=true;notebookUpdateButton.textContent='保存しています…';
});
const notebookVersionHandle=handleServerMessage;
handleServerMessage=function(message){notebookVersionHandle(message);if(message.type==='note_library_result'&&notebookUpdateRequest&&message.requestId===notebookUpdateRequest){notebookUpdateRequest=null;if(message.ok){location.reload();return;}lockNotebookUpdateInput(false);notebookUpdateButton.disabled=false;notebookUpdateButton.textContent='もう一度保存して更新';notebookUpdateText.textContent=message.message||'保存を確認できませんでした。接続を確認して、もう一度お試しください。';}};
const notebookVersionConnection=updateAssistantConnection;
updateAssistantConnection=function(connected){notebookVersionConnection(connected);if(!connected&&notebookUpdateRequest){notebookUpdateRequest=null;lockNotebookUpdateInput(false);notebookUpdateButton.disabled=false;notebookUpdateButton.textContent='再接続してから更新';}};
"""
