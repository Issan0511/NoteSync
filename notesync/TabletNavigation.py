"""Paper zoom and pan without changing stored ink coordinates."""

NAVIGATION_STYLE = r"""
#stage{overflow:hidden;touch-action:none}
#slide-wrapper{transform-origin:center center;will-change:transform}
.notebook-zoom{position:absolute;left:16px;bottom:12px;display:flex;align-items:center;gap:2px;background:#fffffff2;border:1px solid #dedfe7;border-radius:24px;padding:3px;z-index:40;box-shadow:0 2px 10px #24293408;touch-action:manipulation}
.notebook-zoom button{border:0;background:transparent;color:#626b7e;min-width:36px;height:34px;border-radius:20px;font-size:18px;touch-action:manipulation}
.notebook-zoom button:hover{background:#eff1f6}.notebook-zoom #zoom-fit{font-size:11px;min-width:60px}.notebook-zoom button:disabled{opacity:.35}
"""

VIEW_MODEL_SCRIPT = r"""
class NotebookViewTransform {
  constructor(){this.scale=1;this.x=0;this.y=0;}
  reset(){this.scale=1;this.x=0;this.y=0;}
  zoomAt(scale,point,center){
    const next=Math.max(1,Math.min(5,scale)),ratio=next/this.scale;
    this.x=point.x-center.x-(point.x-center.x-this.x)*ratio;
    this.y=point.y-center.y-(point.y-center.y-this.y)*ratio;
    this.scale=next;
    if(next===1){this.x=0;this.y=0;}
  }
  constrain(width,height,paperWidth,paperHeight){
    if(this.scale===1){this.x=0;this.y=0;return;}
    const maxX=Math.max(0,(paperWidth*this.scale-width)/2+Math.min(120,width*.2));
    const maxY=Math.max(0,(paperHeight*this.scale-height)/2+Math.min(120,height*.2));
    this.x=Math.max(-maxX,Math.min(maxX,this.x));this.y=Math.max(-maxY,Math.min(maxY,this.y));
  }
}
"""

NAVIGATION_SCRIPT = VIEW_MODEL_SCRIPT + r"""
const notebookView=new NotebookViewTransform();
const zoomControls=document.createElement('div');zoomControls.className='notebook-zoom';zoomControls.setAttribute('aria-label','ノートの拡大');
zoomControls.innerHTML='<button type="button" id="zoom-out" aria-label="縮小">−</button><button type="button" id="zoom-fit" aria-label="全体を表示">100%</button><button type="button" id="zoom-in" aria-label="拡大">＋</button>';
stage.appendChild(zoomControls);
function viewCenter(){const r=stage.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};}
function refreshNotebookResolution(){
  const w=slideWrapper.clientWidth,h=slideWrapper.clientHeight;
  if(!w||!h)return;
  const density=Math.min((window.devicePixelRatio||1)*notebookView.scale,4,4096/Math.max(w,h));
  for(const canvas of [committedCanvas,activeCanvas]){canvas.width=Math.round(w*density);canvas.height=Math.round(h*density);canvas.getContext('2d').setTransform(density,0,0,density,0,0);}
  renderAllStrokes(sketchbookStrokes);
  if(typeof renderInkSelection==='function')renderInkSelection();
}
function refreshNotebookView(redraw=false){
  const r=stage.getBoundingClientRect();notebookView.constrain(r.width,r.height,slideWrapper.clientWidth,slideWrapper.clientHeight);
  slideWrapper.style.transform=`translate(${notebookView.x}px,${notebookView.y}px) scale(${notebookView.scale})`;
  slideWrapper.style.setProperty('--view-scale',notebookView.scale);
  $('zoom-fit').textContent=`${Math.round(notebookView.scale*100)}%`;$('zoom-out').disabled=notebookView.scale<=1;$('zoom-in').disabled=notebookView.scale>=5;
  if(typeof positionSelectionToolbar==='function')positionSelectionToolbar();
  if(typeof refreshEraserCursor==='function')refreshEraserCursor();
  if(redraw)refreshNotebookResolution();
}
function zoomNotebook(scale,point=viewCenter()){
  finishActiveInput();notebookView.zoomAt(scale,point,viewCenter());refreshNotebookView(true);
}
$('zoom-in').addEventListener('click',()=>zoomNotebook(notebookView.scale*1.35));
$('zoom-out').addEventListener('click',()=>zoomNotebook(notebookView.scale/1.35));
$('zoom-fit').addEventListener('click',()=>{if(typeof fitNotebookPage==='function'){fitNotebookPage();return;}finishActiveInput();notebookView.reset();refreshNotebookView(true);});
stage.addEventListener('wheel',e=>{
  if(e.target.closest('button,input,select,textarea'))return;
  if(typeof scrollNotebookWheel==='function'){scrollNotebookWheel(e);return;}
  e.preventDefault();finishActiveInput();
  if(e.ctrlKey||e.metaKey)notebookView.zoomAt(notebookView.scale*Math.exp(-e.deltaY*.007),{x:e.clientX,y:e.clientY},viewCenter());
  else if(notebookView.scale>1){notebookView.x-=e.deltaX;notebookView.y-=e.deltaY;}
  else notebookView.zoomAt(notebookView.scale*Math.exp(-e.deltaY*.002),{x:e.clientX,y:e.clientY},viewCenter());
  refreshNotebookView(true);
},{passive:false});
const viewTouches=new Map();let pinchBaseline=null;
function beginViewGesture(){
  const points=[...viewTouches.values()];
  if(points.length>=2){const [a,b]=points;pinchBaseline={distance:Math.max(1,Math.hypot(b.x-a.x,b.y-a.y)),scale:notebookView.scale,mid:{x:(a.x+b.x)/2,y:(a.y+b.y)/2},x:notebookView.x,y:notebookView.y};}
  else if(points.length)pinchBaseline={mid:points[0],x:notebookView.x,y:notebookView.y,panAllowed:!penInRange};
  else pinchBaseline=null;
}
stage.addEventListener('pointerdown',e=>{
  if(e.pointerType==='pen'&&penHasContact(e)){
    for(const id of viewTouches.keys())if(stage.hasPointerCapture(id))stage.releasePointerCapture(id);
    viewTouches.clear();pinchBaseline=null;
  }
  if(e.pointerType!=='touch'||e.target.closest('button,input,select,textarea,[data-selection-handle],#selection-box'))return;
  if(typeof continuousInkQueue!=='undefined'&&continuousInkQueue)return;
  if(isDrawing||inkPointerId!==null||typeof selectionPointerActive==='function'&&selectionPointerActive())return;
  // The default pen-only mode reserves fingers for navigation, including while hovering.
  if(!penOnlyToggle.checked&&viewTouches.size===0)return;
  viewTouches.set(e.pointerId,{x:e.clientX,y:e.clientY});beginViewGesture();
  stage.setPointerCapture(e.pointerId);e.preventDefault();e.stopImmediatePropagation();
},{capture:true,passive:false});
stage.addEventListener('pointermove',e=>{
  if(e.pointerType==='pen'&&penHasContact(e)){
    for(const id of viewTouches.keys())if(stage.hasPointerCapture(id))stage.releasePointerCapture(id);
    viewTouches.clear();pinchBaseline=null;
  }
  if(!viewTouches.has(e.pointerId))return;
  viewTouches.set(e.pointerId,{x:e.clientX,y:e.clientY});const points=[...viewTouches.values()];
  if(points.length>=2&&pinchBaseline?.distance){
    const [a,b]=points,mid={x:(a.x+b.x)/2,y:(a.y+b.y)/2},center=viewCenter();
    notebookView.scale=pinchBaseline.scale;notebookView.x=pinchBaseline.x;notebookView.y=pinchBaseline.y;
    notebookView.zoomAt(pinchBaseline.scale*Math.hypot(b.x-a.x,b.y-a.y)/pinchBaseline.distance,pinchBaseline.mid,center);
    notebookView.x+=mid.x-pinchBaseline.mid.x;notebookView.y+=mid.y-pinchBaseline.mid.y;
  }else if(pinchBaseline?.panAllowed&&(notebookView.scale>1||typeof notebookContinuousEnabled!=='undefined')){notebookView.x=pinchBaseline.x+points[0].x-pinchBaseline.mid.x;notebookView.y=pinchBaseline.y+points[0].y-pinchBaseline.mid.y;}
  refreshNotebookView();e.preventDefault();e.stopImmediatePropagation();
},{capture:true,passive:false});
function endViewPointer(e){
  if(!viewTouches.delete(e.pointerId))return;
  if(stage.hasPointerCapture(e.pointerId))stage.releasePointerCapture(e.pointerId);
  beginViewGesture();if(!viewTouches.size)refreshNotebookResolution();e.preventDefault();e.stopImmediatePropagation();
  if(!viewTouches.size&&typeof settleNotebookScroll==='function')settleNotebookScroll();
}
stage.addEventListener('pointerup',endViewPointer,{capture:true});stage.addEventListener('pointercancel',endViewPointer,{capture:true});
stage.addEventListener('lostpointercapture',e=>{if(viewTouches.delete(e.pointerId))beginViewGesture();});
window.addEventListener('blur',()=>{const ids=[...viewTouches.keys()];viewTouches.clear();pinchBaseline=null;for(const id of ids)if(stage.hasPointerCapture(id))stage.releasePointerCapture(id);});
const layoutBeforeNavigation=adjustLayout;
adjustLayout=function(){layoutBeforeNavigation();refreshNotebookView(true);};
"""
