"""Lasso selection, ink transforms and a contextual editing toolbar."""

SELECTION_STYLE = r"""
#selection-canvas{pointer-events:none;z-index:3}
#selection-layer{position:absolute;inset:0;z-index:5;pointer-events:none;transform-origin:0 0;will-change:transform}
#selection-box{position:absolute;border:1px solid #718df1;z-index:5;pointer-events:auto;cursor:move;touch-action:none;transform-origin:center}
#selection-box[hidden],#selection-actions[hidden],#selection-style[hidden]{display:none!important}
.selection-handle{position:absolute;width:12px;height:12px;border:1px solid #718df1;border-radius:50%;background:#fff;transform:translate(-50%,-50%) scale(calc(1 / var(--view-scale,1)));touch-action:none}
.selection-handle[data-selection-handle=nw]{left:0;top:0;cursor:nwse-resize}.selection-handle[data-selection-handle=ne]{left:100%;top:0;cursor:nesw-resize}.selection-handle[data-selection-handle=sw]{left:0;top:100%;cursor:nesw-resize}.selection-handle[data-selection-handle=se]{left:100%;top:100%;cursor:nwse-resize}
.selection-handle[data-selection-handle=rotate]{left:50%;top:calc(-28px / var(--view-scale,1));width:20px;height:20px;cursor:grab;font-size:15px;line-height:16px;text-align:center;color:#718df1}
#selection-actions{position:fixed;display:flex;gap:1px;max-width:calc(100vw - 24px);flex-wrap:wrap;justify-content:center;z-index:85;padding:5px;background:#fffffff5;border:1px solid #e2e3e9;border-radius:14px;box-shadow:0 3px 16px #252c3e13;touch-action:manipulation}
#selection-actions button{background:transparent;border:0;border-radius:8px;padding:10px 9px;color:#4b5262;font-size:12px;white-space:nowrap}#selection-actions button:hover{background:#eef1f7}#selection-actions button:disabled{opacity:.35}
#selection-style{position:fixed;z-index:90;top:90px;right:100px;background:white;border:1px solid #dedfe7;padding:20px;border-radius:18px;width:280px;box-shadow:0 5px 30px #252c3e16}#selection-style label{display:flex;align-items:center;justify-content:space-between;gap:14px;font-size:12px;color:#646d7d;margin:16px 0}#selection-style input[type=range]{width:160px;accent-color:#6b7fad}#selection-style .style-actions{display:flex;gap:8px}#selection-style button{flex:1;border:1px solid #dce0e8;border-radius:9px;background:#f3f5fa;padding:10px;font-size:12px;color:#505c77}
@media(max-width:900px){#selection-style{right:12px;top:75px}}
"""

SELECTION_GEOMETRY_SCRIPT = r"""
class InkSelectionGeometry {
  static inside(p,polygon){
    let inside=false;
    for(let i=0,j=polygon.length-1;i<polygon.length;j=i++){
      const a=polygon[i],b=polygon[j];
      if((a[1]>p[1])!==(b[1]>p[1])&&p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0])inside=!inside;
    }return inside;
  }
  static intersects(a,b,c,d){
    const cross=(p,q,r)=>(q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0]);
    const on=(p,q,r)=>Math.abs(cross(p,q,r))<1e-10&&r[0]>=Math.min(p[0],q[0])-1e-10&&r[0]<=Math.max(p[0],q[0])+1e-10&&r[1]>=Math.min(p[1],q[1])-1e-10&&r[1]<=Math.max(p[1],q[1])+1e-10;
    const abC=cross(a,b,c),abD=cross(a,b,d),cdA=cross(c,d,a),cdB=cross(c,d,b);
    return abC*abD<0&&cdA*cdB<0||on(a,b,c)||on(a,b,d)||on(c,d,a)||on(c,d,b);
  }
  static selected(strokes,polygon){
    if(polygon.length<3)return [];
    const selected=[];
    strokes.forEach((stroke,index)=>{
      if(stroke.points.some(p=>this.inside(p,polygon))){selected.push(index);return;}
      for(let i=1;i<stroke.points.length;i++){
        if(polygon.some((p,j)=>this.intersects(stroke.points[i-1],stroke.points[i],p,polygon[(j+1)%polygon.length]))){selected.push(index);return;}
      }
    });return selected;
  }
  static bounds(strokes){
    let left=Infinity,top=Infinity,right=-Infinity,bottom=-Infinity;
    for(const s of strokes)for(const p of s.points){left=Math.min(left,p[0]);top=Math.min(top,p[1]);right=Math.max(right,p[0]);bottom=Math.max(bottom,p[1]);}
    if(!Number.isFinite(left))return null;
    return {x:left,y:top,width:Math.max(.006,right-left),height:Math.max(.006,bottom-top)};
  }
  static transform(stroke,matrix,widthScale=1){
    const [a,b,c,d,e,f]=matrix;
    return {...stroke,width_ratio:stroke.width_ratio*widthScale,points:stroke.points.map(p=>[a*p[0]+c*p[1]+e,b*p[0]+d*p[1]+f,...p.slice(2)])};
  }
  static rotation(angle,center,aspect){
    const a=Math.cos(angle),b=Math.sin(angle)*aspect,c=-Math.sin(angle)/aspect,d=a;
    return [a,b,c,d,center.x-a*center.x-c*center.y,center.y-b*center.x-d*center.y];
  }
  static cssMatrix(matrix,width,height){
    const [a,b,c,d,e,f]=matrix;return [a,b*height/width,c*width/height,d,e*width,f*height];
  }
}
"""

SELECTION_SCRIPT = SELECTION_GEOMETRY_SCRIPT + r"""
let inkRevision=0,selectedInk=[],selectionClipboard=[],selectionRequest=null,selectionDrag=null,lassoPath=[],lassoPointer=null,lassoArmed=false,selectionSequence=0;
let selectionPending=null,selectionFrame=null,selectionBackgroundSplit=false;
const selectionSession=Date.now().toString(36)+'_'+Math.random().toString(36).slice(2);
const selectionLayer=document.createElement('div');selectionLayer.id='selection-layer';slideWrapper.appendChild(selectionLayer);
const selectionCanvas=document.createElement('canvas');selectionCanvas.id='selection-canvas';selectionLayer.appendChild(selectionCanvas);
const selectionBox=document.createElement('div');selectionBox.id='selection-box';selectionBox.hidden=true;selectionBox.setAttribute('aria-label','選択した筆跡。ドラッグで移動');
for(const corner of ['nw','ne','sw','se','rotate']){const handle=document.createElement('div');handle.className='selection-handle';handle.dataset.selectionHandle=corner;handle.setAttribute('aria-label',corner==='rotate'?'選択を回転':'選択の大きさを変更');if(corner==='rotate')handle.textContent='↻';selectionBox.appendChild(handle);}selectionLayer.appendChild(selectionBox);
const selectionActions=document.createElement('div');selectionActions.id='selection-actions';selectionActions.hidden=true;selectionActions.setAttribute('role','toolbar');selectionActions.setAttribute('aria-label','選択した筆跡の操作');
selectionActions.innerHTML='<button type="button" data-ink-action="cut">切り取り</button><button type="button" data-ink-action="copy">コピー</button><button type="button" data-ink-action="paste">貼り付け</button><button type="button" data-ink-action="duplicate">複製</button><button type="button" data-ink-action="delete">削除</button><button type="button" data-ink-action="style">スタイル</button><button type="button" data-ink-action="done">完了</button>';document.body.appendChild(selectionActions);
const selectionStyle=document.createElement('section');selectionStyle.id='selection-style';selectionStyle.hidden=true;selectionStyle.setAttribute('role','dialog');selectionStyle.setAttribute('aria-label','選択した筆跡のスタイル');
selectionStyle.innerHTML='<strong>筆跡のスタイル</strong><label>色<input type="color" id="selection-color" aria-label="選択の色"></label><label>太さ<input type="range" id="selection-width" aria-label="選択の太さ" min="1" max="80"></label><label>濃さ<input type="range" id="selection-opacity" aria-label="選択の濃さ" min="10" max="100"></label><div class="style-actions"><button type="button" id="selection-style-cancel">キャンセル</button><button type="button" id="selection-style-apply">変更する</button></div>';document.body.appendChild(selectionStyle);
const lassoButton=document.createElement('button');lassoButton.type='button';lassoButton.className='icon-button';lassoButton.id='btn-lasso';lassoButton.setAttribute('aria-label','囲って選択');lassoButton.title='囲って選択';lassoButton.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-dasharray="2 2"><path d="M8 20c-7-1-7-15 1-17 9-3 17 11 10 16-4 3-8 2-10-1s1-5 3-3c2 2-1 8-5 8"/></svg>';
$('btn-line').before(lassoButton);
lassoButton.addEventListener('click',()=>{finishActiveInput();currentTool='lasso';isLineMode=false;clearInkSelection();updatePenUI();showToast('選びたい筆跡を囲んでください');});
function selectionPointerActive(){return lassoPointer!==null||selectionDrag!==null;}
function resetSelectionPreview(){
  if(selectionFrame!==null){cancelAnimationFrame(selectionFrame);selectionFrame=null;}
  selectionLayer.style.transform='';
}
function restoreSelectionBackground(){
  if(selectionBackgroundSplit){renderBaseInk(sketchbookStrokes);selectionBackgroundSplit=false;}
}
function clearInkSelection(){
  const lassoId=lassoPointer,dragId=selectionDrag?.pointer;lassoPointer=null;lassoArmed=false;
  selectedInk=[];lassoPath=[];selectionDrag=null;selectionBox.hidden=true;selectionActions.hidden=true;selectionStyle.hidden=true;
  if(lassoId!==null&&activeCanvas.hasPointerCapture(lassoId))activeCanvas.releasePointerCapture(lassoId);
  if(dragId!==undefined&&selectionBox.hasPointerCapture(dragId))selectionBox.releasePointerCapture(dragId);
  resetSelectionPreview();restoreSelectionBackground();
  const ctx=selectionCanvas.getContext('2d');ctx.clearRect(0,0,selectionCanvas.width,selectionCanvas.height);
}
function selectedStrokes(){return selectedInk.map(i=>sketchbookStrokes[i]).filter(Boolean);}
function resizeSelectionCanvas(){
  const w=slideWrapper.clientWidth,h=slideWrapper.clientHeight,density=Math.min((window.devicePixelRatio||1)*(typeof notebookView!=='undefined'?notebookView.scale:1),4,4096/Math.max(1,w,h));
  const width=Math.round(w*density),height=Math.round(h*density);
  if(selectionCanvas.width!==width)selectionCanvas.width=width;
  if(selectionCanvas.height!==height)selectionCanvas.height=height;
  selectionCanvas.getContext('2d').setTransform(density,0,0,density,0,0);
}
function renderInkSelection(preview=null){
  resetSelectionPreview();resizeSelectionCanvas();const ctx=selectionCanvas.getContext('2d'),w=slideWrapper.clientWidth,h=slideWrapper.clientHeight;
  ctx.clearRect(0,0,w,h);
  if(lassoPath.length){ctx.strokeStyle='#6f788d';ctx.lineWidth=1/(typeof notebookView!=='undefined'?notebookView.scale:1);ctx.setLineDash([3,4]);ctx.beginPath();lassoPath.forEach((p,i)=>i?ctx.lineTo(p[0]*w,p[1]*h):ctx.moveTo(p[0]*w,p[1]*h));ctx.stroke();ctx.setLineDash([]);return;}
  const strokes=preview||selectedStrokes();
  if(selectedInk.length&&!selectionBackgroundSplit){
    const indices=new Set(selectedInk);renderBaseInk(sketchbookStrokes.filter((_,i)=>!indices.has(i)));selectionBackgroundSplit=true;
  }
  for(const stroke of strokes){drawStroke(ctx,{...stroke,color:'#80b8ee',opacity:.6,width_ratio:stroke.width_ratio+.004});drawStroke(ctx,stroke);}
  const bounds=InkSelectionGeometry.bounds(strokes);selectionBox.hidden=!bounds;
  if(bounds){selectionBox.style.left=`${bounds.x*100}%`;selectionBox.style.top=`${bounds.y*100}%`;selectionBox.style.width=`${bounds.width*100}%`;selectionBox.style.height=`${bounds.height*100}%`;}
  selectionActions.hidden=!bounds;for(const b of selectionActions.querySelectorAll('button'))b.disabled=!!selectionRequest||b.dataset.inkAction==='paste'&&!selectionClipboard.length;
  positionSelectionToolbar();
}
function positionSelectionToolbar(){
  if(selectionBox.hidden||selectionActions.hidden)return;
  const box=selectionBox.getBoundingClientRect(),r=stage.getBoundingClientRect(),width=selectionActions.offsetWidth,height=selectionActions.offsetHeight;
  selectionActions.style.left=`${Math.max(r.left+8,Math.min(r.right-width-8,box.left))}px`;
  selectionActions.style.top=`${Math.max(r.top+8,Math.min(r.bottom-height-8,box.top-height-38))}px`;
}
function requestInkEdit(action,extra={},optimistic=false){
  if(selectionRequest||!notebookReady)return false;finishActiveInput();
  const requestId=selectionSession+'_'+(++selectionSequence);selectionRequest=requestId;
  const original=sketchbookStrokes;
  selectionPending={requestId,documentId:currentDocumentId,baseRevision:inkRevision,latestSnapshot:null,localMutation:false,optimistic};
  if(optimistic){
    const indices=new Set(selectedInk);sketchbookStrokes=sketchbookStrokes.map((s,i)=>indices.has(i)?InkSelectionGeometry.transform(s,extra.matrix,extra.widthScale??1):s);
  }
  const sent=sendWS({type:'note_ink_edit',documentId:currentDocumentId,baseRevision:inkRevision,requestId,indices:selectedInk.slice(),action,...extra});
  if(!sent){selectionRequest=null;selectionPending=null;sketchbookStrokes=original;renderAllStrokes(sketchbookStrokes);return false;}
  $('save-status').textContent='保存中…';
  if(optimistic){for(const b of selectionActions.querySelectorAll('button'))b.disabled=true;selectionActions.hidden=false;positionSelectionToolbar();}
  else renderInkSelection();return true;
}
function swallowSelectionEvent(e){e.preventDefault();e.stopImmediatePropagation();}
function lassoNorm(e){const p=getPointerNormPos(e);return [p.normX,p.normY];}
function finishLasso(e,cancelled=false){
  if(e.pointerId!==lassoPointer)return;
  if(!cancelled&&lassoPath.length>=3){selectedInk=InkSelectionGeometry.selected(sketchbookStrokes,lassoPath);if(!selectedInk.length)showToast('筆跡が選ばれませんでした。文字を囲んでください');}
  lassoPath=[];lassoPointer=null;lassoArmed=false;if(activeCanvas.hasPointerCapture(e.pointerId))activeCanvas.releasePointerCapture(e.pointerId);renderInkSelection();swallowSelectionEvent(e);
}
activeCanvas.addEventListener('pointerdown',e=>{
  if(currentTool!=='lasso'||e.pointerType==='pen'&&isPenEraser(e)||e.pointerType==='touch'&&penOnlyToggle.checked||e.pointerType==='mouse'&&e.button!==0)return;
  if(selectionRequest||!notebookReady){swallowSelectionEvent(e);return;}
  if(lassoPointer!==null||selectionDrag){swallowSelectionEvent(e);return;}
  finishActiveInput();clearInkSelection();lassoPointer=e.pointerId;lassoArmed=true;
  if(e.pointerType!=='pen'||penHasContact(e))lassoPath=[lassoNorm(e)];
  activeCanvas.setPointerCapture(e.pointerId);swallowSelectionEvent(e);
},{capture:true});
activeCanvas.addEventListener('pointermove',e=>{
  if(e.pointerId!==lassoPointer)return;
  if(e.pointerType==='pen'&&!penHasContact(e)){swallowSelectionEvent(e);return;}
  if(lassoArmed){lassoPath.push(lassoNorm(e));renderInkSelection();}swallowSelectionEvent(e);
},{capture:true});
activeCanvas.addEventListener('pointerup',e=>finishLasso(e),{capture:true});activeCanvas.addEventListener('pointercancel',e=>finishLasso(e,true),{capture:true});
activeCanvas.addEventListener('lostpointercapture',e=>finishLasso(e,true),{capture:true});
selectionBox.addEventListener('pointerdown',e=>{
  if(selectionDrag||lassoPointer!==null){swallowSelectionEvent(e);return;}
  if(selectionRequest||e.pointerType==='mouse'&&e.button!==0)return;
  if(e.pointerType==='pen'&&isPenEraser(e)){
    clearInkSelection();onInkStart(e);swallowSelectionEvent(e);return;
  }
  if(e.pointerType==='pen'&&(!penHasContact(e)||isPenEraser(e))){swallowSelectionEvent(e);return;}
  finishActiveInput();const bounds=InkSelectionGeometry.bounds(selectedStrokes());if(!bounds)return;
  renderInkSelection();
  selectionDrag={pointer:e.pointerId,start:lassoNorm(e),bounds,paperRect:slideWrapper.getBoundingClientRect(),width:slideWrapper.clientWidth,height:slideWrapper.clientHeight,handle:e.target.dataset.selectionHandle||'move',matrix:[1,0,0,1,0,0],widthScale:1};
  selectionBox.setPointerCapture(e.pointerId);selectionActions.hidden=true;selectionStyle.hidden=true;swallowSelectionEvent(e);
});
function dragSelection(e){
  if(!selectionDrag||selectionDrag.pointer!==e.pointerId)return;
  const drag=selectionDrag,r=drag.paperRect,p=[Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))],b=drag.bounds;let m=[1,0,0,1,0,0],scale=1;
  if(drag.handle==='move'){
    const dx=Math.max(-b.x,Math.min(1-b.x-b.width,p[0]-drag.start[0])),dy=Math.max(-b.y,Math.min(1-b.y-b.height,p[1]-drag.start[1]));m=[1,0,0,1,dx,dy];
  }else if(drag.handle==='rotate'){
    const center={x:b.x+b.width/2,y:b.y+b.height/2},angle=Math.atan2(p[1]-center.y,(p[0]-center.x)*paperAspect)-Math.atan2(drag.start[1]-center.y,(drag.start[0]-center.x)*paperAspect);m=InkSelectionGeometry.rotation(angle,center,paperAspect);
  }else{
    const anchor={x:drag.handle.includes('w')?b.x+b.width:b.x,y:drag.handle.includes('n')?b.y+b.height:b.y};
    const initial=Math.max(.001,Math.hypot((drag.start[0]-anchor.x)*paperAspect,drag.start[1]-anchor.y));
    scale=Math.max(.1,Math.min(10,Math.hypot((p[0]-anchor.x)*paperAspect,p[1]-anchor.y)/initial));m=[scale,0,0,scale,anchor.x*(1-scale),anchor.y*(1-scale)];
  }
  drag.matrix=m;drag.widthScale=scale;
  if(selectionFrame===null)selectionFrame=requestAnimationFrame(()=>{selectionFrame=null;if(selectionDrag)paintSelectionPreview(selectionDrag);});
  swallowSelectionEvent(e);
}
function paintSelectionPreview(drag){
  selectionLayer.style.transform=`matrix(${InkSelectionGeometry.cssMatrix(drag.matrix,drag.width,drag.height).join(',')})`;
}
function cancelSelectionDrag(){
  const drag=selectionDrag;selectionDrag=null;resetSelectionPreview();
  if(drag&&selectionBox.hasPointerCapture(drag.pointer))selectionBox.releasePointerCapture(drag.pointer);
  restoreSelectionBackground();renderInkSelection();
}
selectionBox.addEventListener('pointermove',dragSelection);
function finishSelectionDrag(e,cancelled=false){
  if(!selectionDrag||selectionDrag.pointer!==e.pointerId)return;
  if(cancelled){cancelSelectionDrag();swallowSelectionEvent(e);return;}
  // Pointerup can arrive before either the last pointermove or its RAF paint.
  dragSelection(e);if(selectionFrame!==null){cancelAnimationFrame(selectionFrame);selectionFrame=null;}
  const drag=selectionDrag;selectionDrag=null;if(selectionBox.hasPointerCapture(e.pointerId))selectionBox.releasePointerCapture(e.pointerId);
  paintSelectionPreview(drag);
  const changed=drag.matrix.some((value,i)=>Math.abs(value-[1,0,0,1,0,0][i])>1e-7);
  if(changed)requestInkEdit('transform',{matrix:drag.matrix,widthScale:drag.widthScale},true);
  else renderInkSelection();swallowSelectionEvent(e);
}
selectionBox.addEventListener('pointerup',e=>finishSelectionDrag(e));selectionBox.addEventListener('pointercancel',e=>finishSelectionDrag(e,true));
selectionBox.addEventListener('lostpointercapture',e=>{if(selectionDrag?.pointer===e.pointerId)finishSelectionDrag(e,true);});
selectionActions.addEventListener('click',e=>{
  const action=e.target.dataset.inkAction;if(!action||selectionRequest)return;
  if(action==='done'){clearInkSelection();return;}
  if(action==='copy'||action==='cut'){selectionClipboard=structuredClone(selectedStrokes());showToast(action==='copy'?'筆跡をコピーしました':'筆跡を切り取りました');if(action==='cut')requestInkEdit('delete');else renderInkSelection();}
  else if(action==='paste')requestInkEdit('paste',{strokes:selectionClipboard,matrix:[1,0,0,1,.02,.02]});
  else if(action==='style'){
    const stroke=selectedStrokes()[0];if(!stroke)return;$('selection-color').value=stroke.color;$('selection-width').value=Math.round(stroke.width_ratio*1000);$('selection-opacity').value=Math.round(stroke.opacity*100);selectionStyle.hidden=false;
  }else requestInkEdit(action);
});
$('selection-style-cancel').addEventListener('click',()=>selectionStyle.hidden=true);
$('selection-style-apply').addEventListener('click',()=>{requestInkEdit('style',{color:$('selection-color').value,widthRatio:Number($('selection-width').value)*.001,opacity:Number($('selection-opacity').value)/100});selectionStyle.hidden=true;});
const pasteButton=document.createElement('button');pasteButton.type='button';pasteButton.className='wide-button';pasteButton.textContent='コピーした筆跡を貼り付け';pasteButton.id='paste-ink';$('note-options').appendChild(pasteButton);
pasteButton.addEventListener('click',()=>{if(!selectionClipboard.length){showToast('先に筆跡を囲んでコピーしてください');return;}currentTool='lasso';updatePenUI();closeOverlays();requestInkEdit('paste',{strokes:selectionClipboard,matrix:[1,0,0,1,.02,.02]});});
document.addEventListener('keydown',e=>{
  if(['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName)||!selectedInk.length||selectionRequest)return;
  if(e.key==='Escape'){clearInkSelection();return;}
  if(e.key==='Delete'||e.key==='Backspace'){e.preventDefault();requestInkEdit('delete');}
  if((e.ctrlKey||e.metaKey)&&['c','x','v'].includes(e.key.toLowerCase())){e.preventDefault();selectionActions.querySelector(`[data-ink-action="${{c:'copy',x:'cut',v:'paste'}[e.key.toLowerCase()]}"]`).click();}
});
const renderBaseInk=renderAllStrokes;
renderAllStrokes=function(strokes){
  if(selectionDrag)cancelSelectionDrag();
  const indices=new Set(selectedInk);selectionBackgroundSplit=indices.size>0;
  renderBaseInk(selectionBackgroundSplit?strokes.filter((_,i)=>!indices.has(i)):strokes);renderInkSelection();
};
const updatePenBeforeSelection=updatePenUI;
updatePenUI=function(){updatePenBeforeSelection();lassoButton.classList.toggle('active',currentTool==='lasso');if(currentTool!=='lasso'&&(selectedInk.length||lassoPointer!==null||selectionDrag))clearInkSelection();};
const layoutBeforeSelection=adjustLayout;adjustLayout=function(){if(selectionDrag)cancelSelectionDrag();layoutBeforeSelection();renderInkSelection();};
const sendBeforeSelection=sendWS;
sendWS=function(message){
  const sent=sendBeforeSelection(message);
  // Only stroke_end commits new browser ink. Server-only erases/undo may be
  // no-ops, so they must not prevent a rejected transform from being restored.
  if(sent&&selectionPending&&message.type==='stroke_end')selectionPending.localMutation=true;
  return sent;
};
const handleMessageBeforeSelection=handleServerMessage;
handleServerMessage=function(msg){
  if(msg.type==='note_ink_edit_result'){
    if(msg.requestId!==selectionRequest)return;
    const pending=selectionPending,snapshot=pending?.latestSnapshot;selectionRequest=null;selectionPending=null;
    if(msg.documentId!==currentDocumentId){clearInkSelection();return;}
    inkRevision=Math.max(inkRevision,msg.inkRevision||0,snapshot?.inkRevision||0);
    if(pending?.localMutation){clearInkSelection();updatePenUI();return;}
    if(msg.ok&&(!snapshot||snapshot.inkRevision===msg.inkRevision)){
      if(snapshot)sketchbookStrokes=snapshot.sketchbookStrokes||snapshot.strokes||[];
      if(currentTool==='lasso')selectedInk=msg.indices||[];else clearInkSelection();
      if(pending?.optimistic){updatePenUI();renderInkSelection();}
      else{renderAllStrokes(sketchbookStrokes);updatePenUI();}
    }else{
      clearInkSelection();if(snapshot)handleMessageBeforeSelection(snapshot);else renderAllStrokes(sketchbookStrokes);
    }return;
  }
  const changedDocument=msg.type==='state_sync'&&msg.documentId!==currentDocumentId;
  if(msg.type==='strokes_updated'&&msg.documentId&&msg.documentId!==currentDocumentId)return;
  if(selectionPending&&!changedDocument&&['state_sync','strokes_updated','stroke_undone'].includes(msg.type)){
    if(!selectionPending.latestSnapshot||msg.inkRevision>=selectionPending.latestSnapshot.inkRevision)selectionPending.latestSnapshot=msg;
    // Names and paper can still change while ink is awaiting acknowledgement.
    // Apply that metadata with the browser's current ink, never the old image.
    if(msg.type==='state_sync')handleMessageBeforeSelection({...msg,sketchbookStrokes});
    return;
  }
  if(selectionPending&&msg.type==='note_saved')return;
  if(msg.type==='strokes_updated'&&Number.isInteger(msg.inkRevision)&&msg.inkRevision<=inkRevision)return;
  if(Number.isInteger(msg.inkRevision)){
    if(msg.inkRevision!==inkRevision&&!selectionRequest)clearInkSelection();inkRevision=msg.inkRevision;
  }
  if(changedDocument){selectionRequest=null;selectionPending=null;clearInkSelection();notebookView.reset();}
  if(msg.type==='strokes_cleared'){clearInkSelection();selectionRequest=null;selectionPending=null;}
  handleMessageBeforeSelection(msg);
  if(changedDocument)refreshNotebookView(true);
};
window.addEventListener('blur',()=>{if(selectionDrag)cancelSelectionDrag();lassoPointer=null;lassoPath=[];restoreSelectionBackground();renderInkSelection();});
const connectionBeforeSelection=updateAssistantConnection;
updateAssistantConnection=function(connected){if(!connected){selectionRequest=null;selectionPending=null;clearInkSelection();}connectionBeforeSelection(connected);};
"""
