"""Continuous paper scrolling, lazy vector previews and a thumbnail sidebar.

Only one paper owns the existing ink/selection editor. Other visible papers are
browser-rendered previews; scrolling never depends on a server round trip.
"""

CONTINUOUS_STYLE = r"""
#stage{display:block;padding:0;overflow:hidden;contain:layout paint}
#notebook-paper-stack{position:absolute;left:50%;top:20px;transform-origin:center top;will-change:transform;touch-action:none}
.notebook-paper{position:relative;background:white;box-shadow:0 1px 5px #20212412;overflow:hidden;margin-bottom:20px;touch-action:none;--paper-gap:36px}
.notebook-paper.ruled{background-image:repeating-linear-gradient(to bottom,transparent 0,transparent calc(var(--paper-gap) - 1px),#e7eaf1 var(--paper-gap))}
.notebook-paper.grid{background-image:linear-gradient(#e9edf3 1px,transparent 1px),linear-gradient(90deg,#e9edf3 1px,transparent 1px);background-size:var(--paper-gap) var(--paper-gap)}
.notebook-paper canvas{pointer-events:none}.notebook-paper #slide-wrapper{position:absolute;inset:0;box-shadow:none;transform:none!important;margin:0;background:transparent}
.notebook-paper #active-canvas,.notebook-paper #selection-box{pointer-events:auto}
.notebook-paper-number{position:absolute;bottom:8px;right:12px;color:#b6bcc7;font-size:11px;pointer-events:none}
.notebook-paper-loading{position:absolute;inset:0;display:grid;place-items:center;font-size:12px;color:#a1aabc;pointer-events:none}
#notebook-scrollbar{position:absolute;right:3px;top:8px;bottom:8px;width:12px;touch-action:none;z-index:45}
#notebook-scroll-thumb{position:absolute;left:4px;right:3px;min-height:24px;background:#a9b1c080;border-radius:4px}
#notebook-pages-overlay{inset:72px auto 0 0;width:278px;background:#f3f4f6;z-index:45;pointer-events:auto}
#notebook-pages-sheet{position:static;width:100%;height:100%;max-height:none;border:0;border-radius:0;background:transparent;box-shadow:none;padding:18px 12px;display:flex;flex-direction:column}
#notebook-pages-sheet .sheet-head{margin:0 4px 12px}#notebook-pages-sheet h2{font-size:16px}
#notebook-pages-list{flex:1;max-height:none;overflow:auto;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px 10px;align-content:start;padding:2px 4px 10px}
.notebook-page-card{min-width:0;position:relative}.notebook-page-row{display:block;position:relative;padding:0;border:0;border-radius:0;margin:0;background:transparent!important;min-height:0;color:#8a95a7;overflow:visible;text-align:center}
.notebook-page-preview{position:relative;display:block;width:100%;height:auto!important;aspect-ratio:var(--thumb-aspect,.75);border:2px solid transparent;border-radius:1px;background-color:#fff;box-shadow:0 1px 6px #1e293b12;overflow:hidden;margin-bottom:7px;box-sizing:border-box}
.notebook-page-row.active .notebook-page-preview{border-color:#718df1}.notebook-page-preview canvas{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
.notebook-page-copy strong{font-size:11px;font-weight:400}.notebook-page-copy small,.notebook-page-current{display:none}
.notebook-page-more{position:absolute;bottom:22px;right:3px;width:30px;height:32px;background:#ffffffdb;border:0;border-radius:15px;color:#75829a;font-size:22px;line-height:1;z-index:1}
.notebook-page-more:hover{background:#eef2fa}.notebook-page-add-card{background:#fff;border:0;box-shadow:0 1px 5px #1e293b0d;color:#8b97aa;min-height:95px;aspect-ratio:.75;font-size:28px}
#notebook-pages-message{margin:4px 4px;font-size:10px}#notebook-pages-add-sheet{margin:0;min-height:40px}
#notebook-pages-restore{border:0;background:transparent;color:#6e83a5;min-height:32px;font-size:11px}
#notebook-page-menu{position:fixed;z-index:150;min-width:190px;padding:7px;background:#fffffff9;border:1px solid #e4e8ee;border-radius:17px;box-shadow:0 6px 28px #25374e1a}
#notebook-page-menu[hidden]{display:none}#notebook-page-menu button{display:block;min-height:44px;width:100%;padding:9px 15px;border:0;border-radius:10px;background:transparent;text-align:left;font-size:13px;color:#526078}
#notebook-page-menu button:hover{background:#f0f3f8}#notebook-page-menu button:disabled{opacity:.35}#notebook-page-menu .danger{color:#b56965}
body.pages-open #stage{left:278px}body.pages-open #page-footer{left:292px}
@media(max-width:900px){#notebook-pages-overlay{top:62px;width:238px}body.pages-open #stage{left:238px}body.pages-open #page-footer{left:248px}body.assistant-open #notebook-pages-overlay{bottom:55dvh}#notebook-pages-sheet{padding:14px 9px}}
@media(max-width:600px){#notebook-pages-overlay{width:180px}body.pages-open #stage{left:180px}body.pages-open #page-footer{left:190px}#notebook-pages-list{grid-template-columns:1fr}#notebook-pages-controls{gap:0}#notebook-page-previous,#notebook-page-next{display:none}#page-footer{left:8px!important;gap:3px}#notebook-pages-message{line-height:1.5}}
"""

CONTINUOUS_SCRIPT = r"""
const notebookContinuousEnabled=true;
const paperStack=document.createElement('div');paperStack.id='notebook-paper-stack';stage.appendChild(paperStack);
const notebookScrollRail=document.createElement('div');notebookScrollRail.id='notebook-scrollbar';notebookScrollRail.setAttribute('aria-hidden','true');notebookScrollRail.innerHTML='<div id="notebook-scroll-thumb"></div>';stage.appendChild(notebookScrollRail);
const pageSidebarButton=document.createElement('button');pageSidebarButton.type='button';pageSidebarButton.id='open-pages';pageSidebarButton.className='icon-button';pageSidebarButton.setAttribute('aria-label','ページ一覧');pageSidebarButton.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="4" y="4" width="13" height="17" rx="2"/><path d="M8 1h12v16M8 9h5M8 13h5"/></svg>';$('open-options').before(pageSidebarButton);
pageSidebarButton.addEventListener('click',()=>{if(notebookPagesOverlay.hidden)openNotebookPages();else notebookPagesOverlay.hidden=true;});
const pageRestoreButton=document.createElement('button');pageRestoreButton.id='notebook-pages-restore';pageRestoreButton.type='button';pageRestoreButton.textContent='↶ ページ操作を元に戻す';$('notebook-pages-add-sheet').after(pageRestoreButton);pageRestoreButton.addEventListener('click',()=>requestNotebookPage('restore'));
const pageContextMenu=document.createElement('div');pageContextMenu.id='notebook-page-menu';pageContextMenu.hidden=true;pageContextMenu.setAttribute('role','menu');pageContextMenu.setAttribute('aria-label','ページの操作');document.body.appendChild(pageContextMenu);
const continuousPages=new Map(),continuousCache=new Map(),continuousReads=new Map();
let continuousNotebook='',continuousWidth=600,continuousHeight=450,continuousLayoutKey='',continuousPreserveView=false,continuousIntent=null,continuousAutoSelect=false,continuousFrame=null,continuousSettleTimer=null,continuousReadSequence=0,continuousSidebarOpen=false,continuousPreviewQueue=[],continuousScrollDrag=null,continuousInkQueue=null;
const continuousReset=notebookView.reset.bind(notebookView);
notebookView.reset=function(){if(!continuousPreserveView)continuousReset();};
function notebookFitScale(pageId=currentDocumentId){
  const height=continuousPages.get(pageId)?.height||slideWrapper.clientHeight||continuousWidth/paperAspect;
  return Math.max(.01,Math.min(1,Math.max(1,stage.clientHeight-40)/height,Math.max(1,stage.clientWidth-40)/continuousWidth));
}
function notebookMinimumScale(){
  let tallest=slideWrapper.clientHeight||continuousWidth/paperAspect;
  for(const row of continuousPages.values())if(row.height>tallest)tallest=row.height;
  return Math.max(.01,Math.min(1,Math.max(1,stage.clientHeight-40)/tallest,Math.max(1,stage.clientWidth-40)/continuousWidth));
}
notebookView.zoomAt=function(scale,point){
  const next=Math.max(notebookMinimumScale(),Math.min(5,scale)),ratio=next/this.scale,r=stage.getBoundingClientRect(),px=point.x-r.left-r.width/2,py=point.y-r.top-20;
  this.x=px-(px-this.x)*ratio;this.y=py-(py-this.y)*ratio;this.scale=next;
};
notebookView.constrain=function(width,height){
  const next=Math.max(notebookMinimumScale(),Math.min(5,this.scale));
  if(next!==this.scale){const ratio=next/this.scale;this.x*=ratio;this.y*=ratio;this.scale=next;}
  const maxX=Math.max(0,(continuousWidth*this.scale-width)/2+20);
  this.x=Math.max(-maxX,Math.min(maxX,this.x));this.y=Math.max(Math.min(0,height-40-continuousHeight*this.scale),Math.min(0,this.y));
};
function continuousRow(id){return continuousPages.get(id);}
function cacheCurrentPaper(){
  if(!currentDocumentId||continuousNotebook&&continuousNotebook!==currentNotebookId)return;
  const meta=notebookPages.find(p=>p.id===currentDocumentId);
  continuousCache.set(currentDocumentId,{strokes:sketchbookStrokes,texts:noteTexts,paper,aspect:paperAspect,revision:meta?.revision});
}
function continuousVisible(row,margin=0){const top=20+notebookView.y+row.top*notebookView.scale,bottom=top+row.height*notebookView.scale;return bottom>=-margin&&top<=stage.clientHeight+margin;}
function paintPaperPreview(canvas,content,width,height,density=1){
  canvas.width=Math.max(1,Math.round(width*density));canvas.height=Math.max(1,Math.round(height*density));const ctx=canvas.getContext('2d');ctx.setTransform(density,0,0,density,0,0);
  for(const stroke of content.strokes||[])drawStroke(ctx,stroke,width,height);drawNoteTexts(ctx,content.texts||[],width,height);
}
function paintContinuousRow(row,force=false){
  const active=row.id===currentDocumentId;row.preview.hidden=active;
  if(active){row.loading.hidden=true;return;}
  const visible=continuousVisible(row,stage.clientHeight*.7);
  if(!visible){if(row.preview.width>1){row.preview.width=row.preview.height=1;row.painted=null;}return;}
  const content=continuousCache.get(row.id);row.loading.hidden=!!content||!row.meta.strokeCount&&!row.meta.textCount;
  if(!content){if(continuousInkQueue?.pageId===row.id){paintPaperPreview(row.preview,{strokes:[],texts:[]},continuousWidth,row.height);if(continuousInkQueue.tool!=='eraser')drawStroke(row.preview.getContext('2d'),continuousInkQueue.stroke,continuousWidth,row.height);}return;}
  const density=Math.min(window.devicePixelRatio||1,2,1600/continuousWidth);
  if(force||row.painted!==content||row.paintWidth!==continuousWidth){paintPaperPreview(row.preview,content,continuousWidth,row.height,density);row.painted=content;row.paintWidth=continuousWidth;}
  if(continuousInkQueue?.pageId===row.id&&continuousInkQueue.tool!=='eraser')drawStroke(row.preview.getContext('2d'),continuousInkQueue.stroke,continuousWidth,row.height);
}
function reconcileContinuousPages(){
  const ids=new Set(notebookPages.map(p=>p.id));
  for(const [id,row] of continuousPages)if(!ids.has(id)){if(row.node.contains(slideWrapper))stage.appendChild(slideWrapper);row.node.remove();continuousPages.delete(id);continuousCache.delete(id);}
  for(const [index,meta] of notebookPages.entries()){
    let row=continuousPages.get(meta.id);
    if(!row){const node=document.createElement('section');node.className='notebook-paper';node.dataset.pageId=meta.id;node.setAttribute('aria-label',`ページ ${index+1}`);const preview=document.createElement('canvas'),loading=document.createElement('div'),number=document.createElement('span');preview.width=preview.height=1;loading.className='notebook-paper-loading';loading.textContent='ページを読み込み中…';number.className='notebook-paper-number';node.append(preview,loading,number);row={id:meta.id,node,preview,loading,number};continuousPages.set(meta.id,row);}
    row.meta=meta;row.node.classList.toggle('ruled',meta.paper==='ruled');row.node.classList.toggle('grid',meta.paper==='grid');row.number.textContent=`${index+1} / ${notebookPages.length}`;paperStack.appendChild(row.node);
    const cached=continuousCache.get(meta.id);if(meta.id!==currentDocumentId&&cached&&meta.revision&&cached.revision!==meta.revision){continuousCache.delete(meta.id);row.painted=null;}
  }
  const active=continuousRow(currentDocumentId);if(active){active.node.appendChild(slideWrapper);slideWrapper.style.transform='none';}
  if(!notebookPages.length&&!paperStack.contains(slideWrapper))paperStack.appendChild(slideWrapper);
}
function layoutContinuousPaper(){
  const r=stage.getBoundingClientRect();continuousWidth=Math.max(60,Math.min(1100,r.width-40));paperStack.style.width=continuousWidth+'px';let top=0;
  for(const meta of notebookPages){const row=continuousRow(meta.id);if(!row)continue;row.top=top;row.height=continuousWidth/(meta.aspect||4/3);row.node.style.width=continuousWidth+'px';row.node.style.height=row.height+'px';row.node.style.setProperty('--paper-gap',row.height/24+'px');top+=row.height+20;}
  continuousHeight=Math.max(continuousWidth/paperAspect,top-20);const active=continuousRow(currentDocumentId),height=active?.height||continuousWidth/paperAspect;
  slideWrapper.style.width=continuousWidth+'px';slideWrapper.style.height=height+'px';slideWrapper.style.setProperty('--paper-gap',height/24+'px');
  const key=[continuousWidth,height,currentDocumentId,notebookView.scale].join(':');if(key!==continuousLayoutKey){continuousLayoutKey=key;refreshNotebookResolution();}
  refreshNotebookView();
}
adjustLayout=function(){finishActiveInput();layoutContinuousPaper();};
refreshNotebookView=function(redraw=false){
  const previousScale=notebookView.scale;
  notebookView.constrain(stage.clientWidth,stage.clientHeight);paperStack.style.transform=`translateX(-50%) translate(${notebookView.x}px,${notebookView.y}px) scale(${notebookView.scale})`;slideWrapper.style.setProperty('--view-scale',notebookView.scale);
  $('zoom-fit').textContent=`${Math.round(notebookView.scale*100)}%`;$('zoom-out').disabled=notebookView.scale<=notebookMinimumScale()+1e-8;$('zoom-in').disabled=notebookView.scale>=5;
  const full=continuousHeight*notebookView.scale,track=Math.max(1,stage.clientHeight-16),thumb=Math.min(track,Math.max(24,track*stage.clientHeight/Math.max(1,full)));$('notebook-scroll-thumb').style.height=thumb+'px';$('notebook-scroll-thumb').style.top=(track-thumb)*(-notebookView.y/Math.max(1,full-stage.clientHeight+40))+'px';notebookScrollRail.hidden=full<=stage.clientHeight;
  if(typeof positionSelectionToolbar==='function')positionSelectionToolbar();if(typeof refreshEraserCursor==='function')refreshEraserCursor();
  if(redraw||previousScale!==notebookView.scale)refreshNotebookResolution();scheduleContinuousPaint();
};
function scheduleContinuousPaint(){if(continuousFrame!==null)return;continuousFrame=requestAnimationFrame(()=>{continuousFrame=null;for(const row of continuousPages.values())paintContinuousRow(row);loadVisiblePaperPreviews();});}
function scrollToNotebookPage(id){const row=continuousRow(id);if(!row)return;notebookView.y=-row.top*notebookView.scale;refreshNotebookView();}
function fitNotebookPage(){finishActiveInput();notebookView.scale=notebookFitScale();notebookView.x=0;notebookView.y=-(continuousRow(currentDocumentId)?.top||0)*notebookView.scale;refreshNotebookView(true);}
function scrollNotebookWheel(event){event.preventDefault();if(isDrawing||typeof selectionPointerActive==='function'&&selectionPointerActive())return;finishActiveInput();if(event.ctrlKey||event.metaKey)notebookView.zoomAt(notebookView.scale*Math.exp(-event.deltaY*.007),{x:event.clientX,y:event.clientY});else{const unit=event.deltaMode===1?18:event.deltaMode===2?stage.clientHeight:1;notebookView.y-=event.deltaY*unit;notebookView.x-=event.deltaX*unit;}refreshNotebookView(!!(event.ctrlKey||event.metaKey));settleNotebookScroll();}
function settleNotebookScroll(){
  clearTimeout(continuousSettleTimer);continuousSettleTimer=setTimeout(()=>{
    if(!notebookReady||notebookPagePending||isDrawing||viewTouches.size||typeof selectionRequest!=='undefined'&&selectionRequest||typeof selectionPointerActive==='function'&&selectionPointerActive())return;
    const middle=stage.clientHeight*.48;let closest=null,best=Infinity;
    for(const row of continuousPages.values()){const start=20+notebookView.y+row.top*notebookView.scale,end=start+row.height*notebookView.scale,distance=middle<start?start-middle:middle>end?middle-end:0;if(distance<best){best=distance;closest=row;}}
    if(closest&&closest.id!==currentDocumentId){continuousAutoSelect=true;requestNotebookPage('select',closest.id);continuousAutoSelect=false;}
  },160);
}
function sidebarPaperVisible(card){if(notebookPagesOverlay.hidden)return false;const a=card.getBoundingClientRect(),b=$('notebook-pages-list').getBoundingClientRect();return a.bottom>=b.top-180&&a.top<=b.bottom+180;}
function paintSidebarPreview(card,meta,force=false){
  const preview=card.querySelector('.notebook-page-preview');if(!preview)return;
  preview.style.setProperty('--thumb-aspect',meta.aspect||4/3);
  if(!sidebarPaperVisible(card))return;
  const content=continuousCache.get(meta.id);if(!content)return;let canvas=preview.querySelector('canvas');if(!canvas){preview.textContent='';canvas=document.createElement('canvas');preview.appendChild(canvas);}
  if(force||canvas._paperContent!==content){paintPaperPreview(canvas,content,125,125/(meta.aspect||4/3),2);canvas._paperContent=content;}
}
function loadVisiblePaperPreviews(){
  const wanted=[];for(const row of continuousPages.values())if(row.id!==currentDocumentId&&continuousVisible(row,stage.clientHeight*.7)&&!continuousCache.has(row.id))wanted.push(row.id);
  if(!notebookPagesOverlay.hidden)for(const card of $('notebook-pages-list').querySelectorAll('.notebook-page-card')){const meta=notebookPages.find(p=>p.id===card.dataset.pageId);if(meta){paintSidebarPreview(card,meta);if(sidebarPaperVisible(card)&&!continuousCache.has(meta.id))wanted.push(meta.id);}}
  continuousPreviewQueue=[...new Set(wanted)];pumpPaperPreviews();
}
function pumpPaperPreviews(){
  if(!notebookReady||!continuousNotebook||isDrawing||continuousInkQueue)return;
  while(continuousReads.size<2&&continuousPreviewQueue.length){const pageId=continuousPreviewQueue.shift();if(continuousCache.has(pageId)||[...continuousReads.values()].some(r=>r.pageId===pageId))continue;const meta=notebookPages.find(p=>p.id===pageId);if(!meta)continue;
    const requestId='preview_'+(++continuousReadSequence),request={pageId,revision:meta.revision,notebookId:continuousNotebook};continuousReads.set(requestId,request);
    if(!sendWS({type:'note_page_preview',requestId,pageId,notebookId:continuousNotebook})){continuousReads.delete(requestId);break;}
    request.timer=setTimeout(()=>{continuousReads.delete(requestId);pumpPaperPreviews();},8000);
  }
}
function renderSidebarCards(){
  const list=$('notebook-pages-list');for(const button of [...list.querySelectorAll('.notebook-page-row')]){
    const meta=notebookPages.find(p=>p.id===button.dataset.pageId);if(!meta)continue;const card=document.createElement('div');card.className='notebook-page-card';card.dataset.pageId=meta.id;button.replaceWith(card);card.appendChild(button);
    const more=document.createElement('button');more.type='button';more.className='notebook-page-more';more.textContent='⋮';more.setAttribute('aria-label',`ページ ${meta.index+1} のメニュー`);more.disabled=!!notebookPagePending;more.addEventListener('click',event=>{event.stopPropagation();openPageContextMenu(meta.id,more);});card.appendChild(more);paintSidebarPreview(card,meta);
  }
  const add=document.createElement('button');add.type='button';add.className='notebook-page-add-card';add.textContent='＋';add.setAttribute('aria-label','末尾にページを追加');add.disabled=!!notebookPagePending;add.addEventListener('click',()=>requestNotebookPage('add',notebookPages.at(-1)?.id));list.appendChild(add);
  pageRestoreButton.disabled=!notebookPageCanRestore||!!notebookPagePending;
  scheduleContinuousPaint();
}
const renderPagesBeforeContinuous=renderNotebookPages;
renderNotebookPages=function(status={}){renderPagesBeforeContinuous(status);renderSidebarCards();};
function openPageContextMenu(pageId,anchor){
  pageContextMenu.replaceChildren();const actions=[['add','ページを追加'],['copy','コピー'],['cut','切り取り'],['paste','貼り付け'],['delete','削除'],['clear','ページを消去'],['share','共有']];
  for(const [action,label] of actions){const button=document.createElement('button');button.type='button';button.textContent=label;button.setAttribute('role','menuitem');if(['delete','clear'].includes(action))button.className='danger';button.disabled=!!notebookPagePending||action==='paste'&&!notebookPageCanPaste;button.addEventListener('click',()=>{pageContextMenu.hidden=true;if(action==='share')shareNotebookPage(pageId);else requestNotebookPage(action,pageId);});pageContextMenu.appendChild(button);}
  const r=anchor.getBoundingClientRect();pageContextMenu.hidden=false;pageContextMenu.style.left=Math.min(window.innerWidth-210,Math.max(8,r.right-180))+'px';pageContextMenu.style.top=Math.min(window.innerHeight-350,Math.max(75,r.bottom))+'px';
}
document.addEventListener('pointerdown',event=>{if(!pageContextMenu.hidden&&!pageContextMenu.contains(event.target)&&!event.target.closest('.notebook-page-more'))pageContextMenu.hidden=true;},{capture:true});
const closeBeforeContinuous=closeOverlays;closeOverlays=function(){closeBeforeContinuous();pageContextMenu.hidden=true;};
new MutationObserver(()=>{const open=!notebookPagesOverlay.hidden;if(continuousSidebarOpen===open)return;continuousSidebarOpen=open;document.body.classList.toggle('pages-open',open);pageSidebarButton.classList.toggle('active',open);pageSidebarButton.setAttribute('aria-expanded',String(open));layoutContinuousPaper();loadVisiblePaperPreviews();}).observe(notebookPagesOverlay,{attributes:true,attributeFilter:['hidden']});
$('notebook-pages-list').addEventListener('scroll',()=>{pageContextMenu.hidden=true;scheduleContinuousPaint();},{passive:true});
const requestPageBeforeContinuous=requestNotebookPage;
requestNotebookPage=function(action,pageId){
  if(notebookPagePending)return false;cacheCurrentPaper();const intent={action,pageId,auto:continuousAutoSelect};const sent=requestPageBeforeContinuous(action,pageId);if(sent){continuousIntent=intent;if(action==='select'&&!intent.auto)scrollToNotebookPage(pageId);}return sent;
};
// Sharing uses the platform share sheet when available, with a PNG download fallback.
const continuousShares=new Map();
function shareNotebookPage(pageId){finishActiveInput();const requestId='share_page_'+(++continuousReadSequence);if(sendWS({type:'note_file',action:'png',requestId,documentId:currentDocumentId,pageId})){continuousShares.set(requestId,pageId);showToast('このページの画像を作成しています…');}}
async function deliverPageShare(message){
  if(!message.ok){showToast(message.message||'共有する画像を作れませんでした');return;}
  const bytes=Uint8Array.from(atob(message.data),c=>c.charCodeAt(0)),file=new File([bytes],message.filename,{type:message.mime});
  if(navigator.canShare?.({files:[file]})){try{await navigator.share({files:[file],title:$('note-title').value});return;}catch(error){if(error.name==='AbortError')return;}}
  downloadNotebookFile(message);showToast('ページ画像を保存しました。画像から共有できます');
}
const paintTextBeforeContinuous=requestLatestNoteTextPaint;
requestLatestNoteTextPaint=function(svg){paintTextBeforeContinuous(svg);for(const row of continuousPages.values())if(row.id!==currentDocumentId&&continuousCache.get(row.id)?.texts?.some(t=>noteTextRenderedSvg(t)===svg))paintContinuousRow(row,true);if(!notebookPagesOverlay.hidden)for(const card of $('notebook-pages-list').querySelectorAll('.notebook-page-card')){const meta=notebookPages.find(p=>p.id===card.dataset.pageId);if(meta&&continuousCache.get(meta.id)?.texts?.some(t=>noteTextRenderedSvg(t)===svg))paintSidebarPreview(card,meta,true);}};
const handleBeforeContinuous=handleServerMessage;
handleServerMessage=function(message){
  if(message.type==='note_file_result'&&continuousShares.has(message.requestId)){continuousShares.delete(message.requestId);deliverPageShare(message);return;}
  if(message.type==='note_page_preview_result'){
    const pending=continuousReads.get(message.requestId);if(!pending)return;clearTimeout(pending.timer);continuousReads.delete(message.requestId);const meta=notebookPages.find(p=>p.id===message.pageId);
    if(message.ok&&pending.notebookId===continuousNotebook&&message.notebookId===continuousNotebook&&meta&&(!meta.revision||message.revision===meta.revision)){
      continuousCache.set(message.pageId,{...message});while(continuousCache.size>64){const id=[...continuousCache.keys()].find(id=>id!==currentDocumentId&&!continuousVisible(continuousRow(id)||{top:-100000,height:0},stage.clientHeight));if(!id)break;continuousCache.delete(id);}
      scheduleContinuousPaint();
    }pumpPaperPreviews();return;
  }
  const syncing=message.type==='state_sync',previous=currentDocumentId,previousBook=currentNotebookId,view={scale:notebookView.scale,x:notebookView.x,y:notebookView.y},intent=continuousIntent;
  if(syncing&&currentDocumentId)cacheCurrentPaper();continuousPreserveView=syncing&&previousBook===(message.notebookId||message.documentId);
  try{handleBeforeContinuous(message);}finally{continuousPreserveView=false;}
  if(syncing){
    const changedBook=continuousNotebook!==currentNotebookId;
    if(changedBook){for(const read of continuousReads.values())clearTimeout(read.timer);continuousReads.clear();continuousCache.clear();continuousNotebook=currentNotebookId;continuousLayoutKey='';}
    else Object.assign(notebookView,view);
    cacheCurrentPaper();reconcileContinuousPages();layoutContinuousPaper();
    if(changedBook||previous!==currentDocumentId&&(!intent||!intent.auto)&&intent?.action!=='copy')scrollToNotebookPage(currentDocumentId);
    if(!notebookPagePending)continuousIntent=null;
    renderSidebarCardsAfterSync();replayPendingPaperInput();
  }else if(['strokes_updated','stroke_undone','note_texts_updated','strokes_cleared'].includes(message.type)&&(!message.documentId||message.documentId===currentDocumentId)){cacheCurrentPaper();scheduleContinuousPaint();}
  if(message.type==='note_page_result'&&!message.ok){continuousIntent=null;if(continuousInkQueue){continuousInkQueue.failed=true;showToast('筆跡を画面に保留しています。ページを開き直すと再送します');}}
  if(message.type==='note_page_result'&&message.ok)replayPendingPaperInput();
};
function renderSidebarCardsAfterSync(){if(!notebookPagesOverlay.hidden){renderNotebookPages();}scheduleContinuousPaint();}
const connectionBeforeContinuous=updateAssistantConnection;updateAssistantConnection=function(connected){connectionBeforeContinuous(connected);if(!connected){for(const read of continuousReads.values())clearTimeout(read.timer);continuousReads.clear();continuousShares.clear();if(continuousInkQueue)continuousInkQueue.ended=true;}else scheduleContinuousPaint();};
notebookScrollRail.addEventListener('pointerdown',event=>{event.preventDefault();event.stopPropagation();finishActiveInput();continuousScrollDrag={id:event.pointerId,y:event.clientY,offset:notebookView.y};notebookScrollRail.setPointerCapture(event.pointerId);});
notebookScrollRail.addEventListener('pointermove',event=>{if(continuousScrollDrag?.id!==event.pointerId)return;const ratio=Math.max(1,(continuousHeight*notebookView.scale-stage.clientHeight+40)/Math.max(1,stage.clientHeight-40));notebookView.y=continuousScrollDrag.offset-(event.clientY-continuousScrollDrag.y)*ratio;refreshNotebookView();});
for(const type of ['pointerup','pointercancel'])notebookScrollRail.addEventListener(type,event=>{if(continuousScrollDrag?.id!==event.pointerId)return;continuousScrollDrag=null;settleNotebookScroll();});
// Hover activates a visible paper before the pen lands; fingers retain scrolling.
stage.addEventListener('pointerover',event=>{const row=event.target.closest('.notebook-paper');if(event.pointerType==='pen'&&row&&row.dataset.pageId!==currentDocumentId&&!penHasContact(event)&&!viewTouches.size&&!isDrawing&&!notebookPagePending){continuousAutoSelect=true;requestNotebookPage('select',row.dataset.pageId);continuousAutoSelect=false;}},{capture:true});
function queuedPaperPoint(event,row){const r=row.node.getBoundingClientRect();return [Math.max(0,Math.min(1,(event.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(event.clientY-r.top)/r.height)),inputPressure(event)];}
function queuePendingPaperInput(event){
  const node=event.target.closest('.notebook-paper'),row=node&&continuousRow(node.dataset.pageId);
  if(!row||row.id===currentDocumentId||continuousInkQueue||event.pointerType==='touch'&&(penOnlyToggle.checked||penInRange)||event.pointerType==='pen'&&!penHasContact(event)||event.pointerType==='mouse'&&event.button!==0)return false;
  if(notebookPagePending&&notebookPagePending.pageId!==row.id)return false;
  if(isDrawing||typeof selectionRequest!=='undefined'&&selectionRequest)return false;
  const tool=isPenEraser(event)?'eraser':currentTool;
  if(!['pen','highlighter','eraser'].includes(tool))return false;
  if(!notebookPagePending){continuousAutoSelect=true;const sent=requestNotebookPage('select',row.id);continuousAutoSelect=false;if(!sent)return false;}
  const stroke={color:currentColor,width_ratio:getCurrentWidthRatio(),opacity:getToolOpacity(),brush:getCurrentBrush(),points:[queuedPaperPoint(event,row)]};
  continuousInkQueue={pageId:row.id,notebookId:currentNotebookId,pointerId:event.pointerId,pointerType:event.pointerType,tool,stroke,ended:false};
  stage.setPointerCapture(event.pointerId);paintContinuousRow(row,true);event.preventDefault();event.stopImmediatePropagation();return true;
}
function replayPendingPaperInput(){
  const queued=continuousInkQueue;if(!queued||notebookPagePending||queued.pageId!==currentDocumentId||queued.notebookId!==currentNotebookId)return;
  continuousInkQueue=null;const points=queued.stroke.points;
  // The original normalized samples, pressure and pen style survive activation.
  const preset=currentPreset(),line=isLineMode;currentColor=queued.stroke.color;selectedBrush=queued.stroke.brush;toolSizes[queued.tool==='highlighter'?'highlighter':'pen']=queued.stroke.width_ratio/.001;toolOpacities[queued.tool==='highlighter'?'highlighter':'pen']=queued.stroke.opacity;
  beginInkAt({normX:points[0][0],normY:points[0][1]},queued.tool,points[0][2]);for(const point of points.slice(1))moveInkTo({normX:point[0],normY:point[1]},point[2]);
  if(queued.ended){finishInkStroke();currentColor=preset.color;selectedBrush=preset.brush;const key=preset.brush==='highlighter'?'highlighter':'pen';toolSizes[key]=preset.size;toolOpacities[key]=preset.opacity;isLineMode=line;}
  else{inkPointerId=queued.pointerId;penInRange=queued.pointerType==='pen';penContactArmed=penInRange;try{activeCanvas.setPointerCapture(queued.pointerId);}catch(_){finishActiveInput();}}
  renderInkSelection();
}
stage.addEventListener('pointerdown',event=>{const row=event.target.closest('.notebook-paper');if(!row||row.dataset.pageId===currentDocumentId||event.pointerType==='touch'&&penOnlyToggle.checked)return;if(queuePendingPaperInput(event))return;event.preventDefault();event.stopImmediatePropagation();if(!notebookPagePending){continuousAutoSelect=true;requestNotebookPage('select',row.dataset.pageId);continuousAutoSelect=false;}},{capture:true,passive:false});
stage.addEventListener('pointermove',event=>{const queued=continuousInkQueue;if(!queued||event.pointerId!==queued.pointerId)return;const row=continuousRow(queued.pageId);if(!row)return;const samples=event.getCoalescedEvents?.();for(const sample of samples?.length?samples:[event])queued.stroke.points.push(queuedPaperPoint(sample,row));paintContinuousRow(row,true);event.preventDefault();event.stopImmediatePropagation();},{capture:true,passive:false});
for(const type of ['pointerup','pointercancel'])stage.addEventListener(type,event=>{const queued=continuousInkQueue;if(!queued||event.pointerId!==queued.pointerId)return;queued.ended=true;if(stage.hasPointerCapture(event.pointerId))stage.releasePointerCapture(event.pointerId);event.preventDefault();event.stopImmediatePropagation();replayPendingPaperInput();},{capture:true});
reconcileContinuousPages();renderNotebookPages();
"""
