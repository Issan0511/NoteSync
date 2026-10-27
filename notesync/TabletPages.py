"""Touch-friendly page controls for a multi-page handwritten notebook."""

PAGES_STYLE = r"""
#stage{bottom:62px}#page-footer{bottom:10px;min-height:40px;align-items:center;gap:14px}#page-footer>#note-footer{margin-left:auto;margin-right:5px}
#notebook-pages-controls{display:flex;align-items:center;gap:2px;pointer-events:auto;flex-shrink:0;padding:3px;border:1px solid #e0e5ed;border-radius:23px;background:#fcfcfdf5;box-shadow:0 2px 9px #27345106;touch-action:manipulation}
#notebook-pages-controls button{height:36px;min-width:36px;border:0;border-radius:18px;color:#6b7d98;background:transparent;font-size:12px;padding:7px 9px;white-space:nowrap}#notebook-pages-controls button:hover{background:#edf1f7}#notebook-pages-controls button:disabled{opacity:.3}#notebook-pages-controls svg{width:18px;height:18px}
#notebook-pages-number{min-width:58px!important;font-variant-numeric:tabular-nums}#notebook-page-add{display:flex;align-items:center;gap:4px;border-left:1px solid #e4e9f1!important;border-radius:0 18px 18px 0!important;padding-right:12px!important;color:#526e96!important}#notebook-page-add svg{width:17px;height:17px}
#notebook-pages-sheet{right:90px;bottom:69px;width:330px;max-height:calc(100dvh - 155px);padding:20px}#notebook-pages-sheet .sheet-head{margin-bottom:12px}#notebook-pages-list{max-height:45dvh;overflow:auto;overscroll-behavior:contain;touch-action:pan-y;padding:3px 0}
.notebook-page-row{display:flex;align-items:center;gap:13px;width:100%;border:1px solid #e3e8ef;border-radius:12px;background:#fafbfd;color:#65758c;min-height:74px;padding:11px;margin:8px 0;text-align:left}.notebook-page-row.active{border-color:#a8bad6;background:#f0f4fb;color:#496389}.notebook-page-preview{display:flex;align-items:center;justify-content:center;width:43px;height:48px;flex-shrink:0;background:white;border:1px solid #e0e6ef;border-radius:2px;color:#b6c2d4;font-size:11px}.notebook-page-preview.ruled{background-image:repeating-linear-gradient(to bottom,transparent 0,transparent 9px,#e6edf6 10px)}.notebook-page-preview.grid{background-image:linear-gradient(#e9eef5 1px,transparent 1px),linear-gradient(90deg,#e9eef5 1px,transparent 1px);background-size:10px 10px}.notebook-page-copy{flex:1;min-width:0}.notebook-page-copy strong{display:block;font-size:13px;font-weight:550}.notebook-page-copy small{display:block;font-size:11px;color:#98a3b3;margin-top:6px}.notebook-page-current{font-size:10px;color:#8095b2}
#notebook-pages-message{font-size:11px;color:#8898af;line-height:1.8;min-height:18px;margin:11px 0 8px}#notebook-pages-message.error{color:#b25e5e}#notebook-pages-add-sheet{margin-top:7px;min-height:44px}
#assistant-launch{bottom:66px}
@media(max-width:900px){#notebook-pages-sheet{right:70px;bottom:66px;width:310px}#page-footer{left:12px;right:72px;gap:9px}body.assistant-open #stage{bottom:calc(55dvh + 62px)}body.assistant-open #page-footer{bottom:calc(55dvh + 10px)}body.assistant-open #notebook-pages-sheet{bottom:calc(55dvh + 65px);max-height:calc(45dvh - 85px)}}
@media(max-width:700px){#page-footer>#note-footer{display:none}#page-footer{justify-content:flex-end}#notebook-pages-sheet{right:12px;max-width:calc(100vw - 24px)}#notebook-pages-controls button{font-size:11px;padding:7px 8px}}
"""

PAGES_SCRIPT = r"""
const notebookPageIcon=name=>'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+({previous:'<path d="m14 6-6 6 6 6"/>',next:'<path d="m10 6 6 6-6 6"/>',add:'<path d="M12 4v16M4 12h16"/>',close:'<path d="m6 6 12 12M18 6 6 18"/>'}[name]||'')+'</svg>';
let notebookPages=[],notebookPageIndex=0,notebookPagePending=null,notebookPageSequence=0,notebookPageCanRestore=false,notebookPageCanPaste=false;
const notebookPageControls=document.createElement('nav');notebookPageControls.id='notebook-pages-controls';notebookPageControls.setAttribute('aria-label','ノートのページ');
notebookPageControls.innerHTML=`<button type="button" id="notebook-page-previous" aria-label="前のページ">${notebookPageIcon('previous')}</button><button type="button" id="notebook-pages-number" aria-label="ページ一覧を開く">– / –</button><button type="button" id="notebook-page-next" aria-label="次のページ">${notebookPageIcon('next')}</button><button type="button" id="notebook-page-add" aria-label="新しいページを追加">${notebookPageIcon('add')}ページ</button>`;$('page-footer').appendChild(notebookPageControls);
const notebookPagesOverlay=document.createElement('div');notebookPagesOverlay.id='notebook-pages-overlay';notebookPagesOverlay.className='overlay';notebookPagesOverlay.hidden=true;
notebookPagesOverlay.innerHTML=`<section id="notebook-pages-sheet" class="sheet" role="dialog" aria-label="ページ一覧"><div class="sheet-head"><h2>ページ</h2><button type="button" id="notebook-pages-close" class="icon-button" aria-label="ページ一覧を閉じる">${notebookPageIcon('close')}</button></div><div id="notebook-pages-list"></div><p id="notebook-pages-message" role="status"></p><button type="button" id="notebook-pages-add-sheet" class="wide-button">＋ 新しいページ</button></section>`;document.body.appendChild(notebookPagesOverlay);
function notebookPageMessage(message,error=false){$('notebook-pages-message').textContent=message;$('notebook-pages-message').classList.toggle('error',error);}
function notebookPageCount(value){return Number.isFinite(value)&&value>=0?Math.floor(value):0;}
function renderNotebookPages(status={}){
  if(typeof status.canRestorePage==='boolean')notebookPageCanRestore=status.canRestorePage;
  if(typeof status.canPastePage==='boolean')notebookPageCanPaste=status.canPastePage;
  if(Array.isArray(status.pages))notebookPages=status.pages.filter(page=>typeof page.id==='string').map(page=>({...page}));
  if(!notebookPages.length&&currentDocumentId)notebookPages=[{id:currentDocumentId,index:0,strokeCount:0,textCount:0}];
  const active=notebookPages.findIndex(page=>page.id===(status.pageId||currentDocumentId));
  notebookPageIndex=active>=0?active:Math.max(0,Math.min(notebookPages.length-1,Number.isInteger(status.currentPage)?status.currentPage:notebookPageIndex));
  const busy=!!notebookPagePending,disabled=busy||!notebookReady||!currentDocumentId,total=notebookPages.length;
  $('notebook-pages-number').textContent=total?`${notebookPageIndex+1} / ${total}`:'– / –';$('notebook-pages-number').setAttribute('aria-label',total?`ページ ${notebookPageIndex+1} / ${total}、一覧を開く`:'ページ一覧を開く');
  $('notebook-page-previous').disabled=disabled||notebookPageIndex<=0;$('notebook-page-next').disabled=disabled||notebookPageIndex>=total-1;$('notebook-pages-number').disabled=disabled;
  $('notebook-page-add').disabled=disabled;$('notebook-pages-add-sheet').disabled=disabled;
  const list=$('notebook-pages-list');list.replaceChildren();
  notebookPages.forEach((page,index)=>{
    const row=document.createElement('button');row.type='button';row.className='notebook-page-row';row.classList.toggle('active',page.id===currentDocumentId);row.disabled=disabled;row.dataset.pageId=page.id;row.setAttribute('aria-label',`ページ ${index+1}${page.id===currentDocumentId?'、表示中':' を開く'}`);
    const preview=document.createElement('span');preview.className='notebook-page-preview';if(['ruled','grid'].includes(page.paper))preview.classList.add(page.paper);preview.textContent=index+1;preview.setAttribute('aria-hidden','true');
    const copy=document.createElement('span');copy.className='notebook-page-copy';const title=document.createElement('strong');title.textContent=`ページ ${index+1}`;const details=document.createElement('small'),ink=notebookPageCount(page.strokeCount),text=notebookPageCount(page.textCount);details.textContent=ink||text?[ink?`筆跡 ${ink}`:'',text?`テキスト ${text}`:''].filter(Boolean).join(' · '):'空白';copy.append(title,details);row.append(preview,copy);
    if(page.id===currentDocumentId){const current=document.createElement('span');current.className='notebook-page-current';current.textContent='表示中';row.appendChild(current);}
    row.addEventListener('click',()=>{if(page.id===currentDocumentId)notebookPagesOverlay.hidden=true;else requestNotebookPage('select',page.id);});list.appendChild(row);
  });
}
function openNotebookPages(){finishActiveInput();closeOverlays();notebookPagesOverlay.hidden=false;renderNotebookPages();}
function requestNotebookPage(action,pageId){
  if(notebookPagePending||!['add','select','copy','cut','paste','delete','clear','restore'].includes(action))return false;
  if(!notebookReady||!currentDocumentId){const message='PCに接続してから、もう一度お試しください';notebookPageMessage(message,true);showToast(message);return false;}
  if(action==='select'&&(!notebookPages.some(page=>page.id===pageId)||pageId===currentDocumentId))return false;
  finishActiveInput();if(typeof flushNotebookTitle==='function')flushNotebookTitle();
  const requestId='page_'+Date.now().toString(36)+'_'+(++notebookPageSequence),message={type:'note_page',action,documentId:currentDocumentId,requestId};if(pageId)message.pageId=pageId;
  if(!sendWS(message)){const error='ページを変更できませんでした。接続を確認してください';notebookPageMessage(error,true);showToast(error);return false;}
  notebookPagePending={requestId,action,pageId,notebookId:typeof currentNotebookId==='string'?currentNotebookId:'',acknowledged:false,targetPageId:null};
  notebookPageMessage(action==='add'?'ページを追加しています…':'ページを開いています…');renderNotebookPages();return true;
}
function completeNotebookPageRequest(){
  const pending=notebookPagePending;if(!pending||!pending.acknowledged||pending.targetPageId!==currentDocumentId)return;
  if(pending.notebookId&&typeof currentNotebookId==='string'&&pending.notebookId!==currentNotebookId)return;
  const action=pending.action;notebookPagePending=null;notebookPageMessage('');if(typeof notebookContinuousEnabled==='undefined')notebookPagesOverlay.hidden=true;renderNotebookPages();
  if(['copy','cut','delete','clear','paste','restore'].includes(action))showToast({copy:'ページをコピーしました。「貼り付け」で追加できます',cut:'ページを切り取りました。貼り付け・元に戻すができます',delete:'ページを削除しました。ページ一覧の「元に戻す」で復元できます',clear:'ページを消去しました。ページ一覧の「元に戻す」で復元できます',paste:'ページを貼り付けました',restore:'ページ操作を元に戻しました'}[action]);
}
$('notebook-pages-number').addEventListener('click',openNotebookPages);$('notebook-pages-close').addEventListener('click',()=>notebookPagesOverlay.hidden=true);
$('notebook-page-add').addEventListener('click',()=>requestNotebookPage('add'));$('notebook-pages-add-sheet').addEventListener('click',()=>requestNotebookPage('add'));
$('notebook-page-previous').addEventListener('click',()=>{const page=notebookPages[notebookPageIndex-1];if(page)requestNotebookPage('select',page.id);});
$('notebook-page-next').addEventListener('click',()=>{const page=notebookPages[notebookPageIndex+1];if(page)requestNotebookPage('select',page.id);});
notebookPagesOverlay.addEventListener('pointerdown',event=>{if(event.target===notebookPagesOverlay){event.preventDefault();notebookPagesOverlay.hidden=true;}});
const closeOverlaysBeforePages=closeOverlays;closeOverlays=function(){closeOverlaysBeforePages();notebookPagesOverlay.hidden=true;};
const notebookPageInkMessages=new Set(['stroke_start','stroke_move','stroke_end','erase_start','erase','erase_end','line_update','undo','redo','clear','note_paper']);
const sendBeforePages=sendWS;sendWS=function(message){return sendBeforePages(notebookPageInkMessages.has(message.type)?{...message,documentId:message.documentId??currentDocumentId}:message);};
// Navigation captures finger pinch/pan before this listener. Only fresh ink
// and selection starts are paused while the requested page is being loaded.
stage.addEventListener('pointerdown',event=>{
  if(!notebookPagePending)return;
  if(typeof queuePendingPaperInput==='function'&&queuePendingPaperInput(event))return;
  const selectionTarget=event.target.closest?.('#selection-box,[data-selection-handle]');
  if(event.pointerType==='touch'&&penOnlyToggle.checked&&!selectionTarget)return;
  event.preventDefault();event.stopImmediatePropagation();
},{capture:true,passive:false});
stage.addEventListener('touchstart',event=>{
  if(!notebookPagePending)return;
  const stylus=Array.from(event.changedTouches||[]).some(touch=>touch.touchType==='stylus'),selectionTarget=event.target.closest?.('#selection-box,[data-selection-handle]');
  if(!stylus&&penOnlyToggle.checked&&!selectionTarget)return;event.preventDefault();event.stopImmediatePropagation();
},{capture:true,passive:false});
const handleMessageBeforePages=handleServerMessage;handleServerMessage=function(message){
  const result=handleMessageBeforePages(message);
  if(message.type==='state_sync'){
    const pending=notebookPagePending;
    if(pending?.notebookId&&message.notebookId&&pending.notebookId!==message.notebookId){notebookPagePending=null;notebookPageMessage('');notebookPagesOverlay.hidden=true;}
    renderNotebookPages(message);completeNotebookPageRequest();
  }else if(message.type==='note_page_result'&&notebookPagePending&&message.requestId===notebookPagePending.requestId){
    if(message.ok){notebookPagePending.acknowledged=true;notebookPagePending.targetPageId=message.pageId||notebookPagePending.pageId;completeNotebookPageRequest();}
    else{notebookPagePending=null;const error=message.message||'ページを変更できませんでした';notebookPageMessage(error,true);showToast(error);renderNotebookPages();}
  }
  return result;
};
const connectionBeforePages=updateExtensionConnection;updateExtensionConnection=function(connected){const result=connectionBeforePages(connected);if(!connected){notebookPagePending=null;notebookPageMessage('PCとの接続が切れました。再接続してからお試しください。',true);}renderNotebookPages();return result;};
renderNotebookPages();
"""
