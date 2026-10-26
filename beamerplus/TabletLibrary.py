"""Full-screen notebook library with search, note actions and recoverable trash."""

LIBRARY_MODEL_SCRIPT = r"""
function notebookLibraryTimestamp(value){
  if(typeof value==='number')return Number.isFinite(value)?(value<1e12?value*1000:value):0;
  if(typeof value!=='string'||!value)return 0;
  const parsed=Date.parse(value);return Number.isFinite(parsed)?parsed:0;
}
function notebookLibraryNotes(items,{trash=false,query='',sort='updated'}={}){
  const search=query.trim().toLocaleLowerCase();
  return items.filter(note=>!!note.deletedAt===trash&&(!search||String(note.title||'新しいノート').toLocaleLowerCase().includes(search)))
    .slice().sort((a,b)=>sort==='title'?String(a.title||'').localeCompare(String(b.title||''),'ja'):notebookLibraryTimestamp(b.updatedAt||b.createdAt)-notebookLibraryTimestamp(a.updatedAt||a.createdAt)||String(a.title||'').localeCompare(String(b.title||''),'ja'));
}
function notebookLibraryCount(value){return Number.isFinite(value)&&value>=0?Math.floor(value):null;}
"""

LIBRARY_STYLE = r"""
#library-overlay{background:#f5f6f8;z-index:140}
#note-library{position:absolute;inset:0;width:100%;max-width:none;background:#f5f6f8;padding:0;box-shadow:none;overflow:hidden;display:flex;flex-direction:column;color:#303643}
.library-header{display:flex;align-items:center;gap:16px;padding:22px 32px 16px;background:#fcfcfd;flex-shrink:0;border-bottom:1px solid #e4e6eb}.library-header h2{font-size:27px;font-weight:650;letter-spacing:.01em;margin:0;flex:1}.library-header .icon-button{width:44px;height:44px}.library-create{display:flex;gap:8px;align-items:center;border:0;border-radius:24px;min-height:46px;padding:10px 19px;background:#465979;color:#fff;font-size:13px}.library-create svg{width:20px;height:20px}
#library-file-actions{display:flex;align-items:center;gap:6px}#library-file-actions button{min-height:44px;border:1px solid #e1e6ef;border-radius:13px;background:#f6f8fb;color:#6d7c94;padding:9px 13px;font-size:12px}
.library-tools{padding:22px 34px 0;display:flex;align-items:center;gap:14px;flex-wrap:wrap;flex-shrink:0}.library-search{position:relative;flex:1;min-width:180px;max-width:460px}.library-search svg{position:absolute;left:14px;top:13px;width:20px;height:20px;color:#9198a7}.library-search input{width:100%;height:46px;border:1px solid #e0e4eb;border-radius:15px;padding:10px 14px 10px 43px;background:#fff;color:#414958;font-size:14px;outline:none}.library-search input:focus{border-color:#8d9fbe}
.library-tabs{display:flex;gap:4px;padding:4px;border-radius:13px;background:#e9ecf2}.library-tabs button{min-height:38px;padding:8px 14px;border:0;border-radius:10px;background:transparent;color:#8a91a0;font-size:12px}.library-tabs button.active{background:#fff;box-shadow:0 2px 7px #25304a08;color:#415879}.library-tabs .library-tab-count{margin-left:6px;font-size:10px}
.library-sort{height:42px;max-width:155px;border:1px solid #dde2eb;background:#fff;color:#667084;border-radius:11px;padding:8px;font-size:12px}.library-view-controls{display:flex}.library-view-controls .icon-button{width:38px;height:38px;border-radius:11px}.library-view-controls .icon-button.active{background:#e3e8f2;color:#405778}.library-view-controls svg{width:20px;height:20px}
.library-summary{padding:16px 36px 12px;color:#8d95a4;font-size:12px;display:flex;align-items:center;justify-content:space-between;min-height:43px}.library-message{color:#677e9f}.library-message.error{color:#b15454}
#notebook-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:22px;padding:6px 34px 48px;overflow:auto;align-content:start;flex:1;overscroll-behavior:contain;touch-action:pan-y}
.library-card{position:relative;min-width:0;max-width:350px;border-radius:17px;background:#fff;border:1px solid #e4e7ed;box-shadow:0 3px 10px #27345104;overflow:hidden}.library-card.current{border-color:#9aafd0;box-shadow:0 0 0 1px #9aafd034}.library-card-main{display:block;position:relative;width:100%;border:0;padding:0;text-align:left;background:none;color:inherit}.library-card-main:disabled{opacity:1}.library-card-main:focus-visible{outline-offset:-4px}
.library-preview{height:174px;background:#eaeef3;display:flex;justify-content:center;align-items:center;padding:18px;overflow:hidden}.library-paper{display:flex;justify-content:center;align-items:center;position:relative;width:78%;height:100%;max-width:170px;background:white;box-shadow:0 2px 7px #24304710;border-radius:1px;color:#d4dbe5}.library-paper svg{width:34px;height:34px}.library-paper.ruled{background-image:repeating-linear-gradient(to bottom,transparent 0,transparent 16px,#e9edf4 17px)}.library-paper.grid{background-image:linear-gradient(#ecf0f5 1px,transparent 1px),linear-gradient(90deg,#ecf0f5 1px,transparent 1px);background-size:17px 17px}
.library-card-copy{padding:16px 16px 15px}.library-card-title{display:block;font-size:14px;font-weight:600;white-space:nowrap;text-overflow:ellipsis;overflow:hidden;margin-right:14px}.library-card-date{display:block;color:#929aaa;font-size:11px;margin-top:8px}.library-card-detail{display:block;font-size:10px;color:#9ca3af;line-height:1.5;margin-top:7px}.library-current-badge{position:absolute;top:12px;left:12px;border-radius:12px;background:#fffffff0;color:#5e7496;padding:5px 9px;font-size:10px;box-shadow:0 1px 5px #25304a08}.library-card-more{position:absolute;right:8px;top:8px;width:40px;height:40px;background:#ffffffed;box-shadow:0 1px 5px #25304a09;color:#758197}.library-card-more svg{width:21px;height:21px}.library-restore{border:0;border-top:1px solid #edf0f5;background:#f9fbfe;color:#5c7295;width:100%;padding:12px;font-size:12px;min-height:44px}
#notebook-list.library-list-view{grid-template-columns:1fr;gap:11px}.library-list-view .library-card{max-width:none;min-height:106px}.library-list-view .library-card-main{display:flex;align-items:center;min-height:106px}.library-list-view .library-preview{width:112px;height:106px;flex-shrink:0;padding:13px}.library-list-view .library-paper{width:73px;max-width:none}.library-list-view .library-paper svg{width:24px;height:24px}.library-list-view .library-card-copy{min-width:0;padding:14px 60px 14px 20px;flex:1}.library-list-view .library-card-more{top:30px;right:14px;box-shadow:none}.library-list-view .library-current-badge{font-size:9px;top:8px;left:7px;padding:4px 6px}.library-list-view .library-card-detail{margin-top:5px}.library-list-view .library-restore{position:absolute;right:16px;top:33px;width:76px;border:1px solid #dce4ef;border-radius:10px;padding:7px;min-height:38px}.library-list-view .library-card.trashed .library-card-copy{padding-right:105px}
.library-empty{grid-column:1/-1;display:flex;align-items:center;justify-content:center;flex-direction:column;text-align:center;gap:13px;min-height:280px;color:#969faf;padding:32px}.library-empty svg{width:50px;height:50px;color:#b8c3d3}.library-empty strong{font-size:17px;color:#68788f;font-weight:550}.library-empty p{font-size:12px;line-height:1.9;margin:0;max-width:290px}
#library-card-menu{position:fixed;z-index:145;width:205px;background:#fff;border:1px solid #e0e5ed;border-radius:15px;box-shadow:0 8px 35px #27334a20;padding:6px}#library-card-menu[hidden]{display:none!important}#library-card-menu button{display:block;width:100%;border:0;background:transparent;border-radius:9px;color:#59677d;text-align:left;padding:13px 14px;font-size:13px;min-height:44px}#library-card-menu button:hover{background:#f0f3f8}#library-card-menu button.danger{color:#b35c5c}
#library-rename-overlay{position:fixed;inset:0;background:#222a3b40;z-index:150;display:grid;place-items:center;padding:20px}#library-rename-overlay[hidden]{display:none!important}.library-rename-dialog{width:360px;max-width:100%;padding:24px;background:white;border-radius:20px;box-shadow:0 16px 60px #14213e25}.library-rename-dialog h3{margin:0 0 20px;font-size:18px;font-weight:600}.library-rename-dialog input{width:100%;height:48px;border:1px solid #a6b7d1;border-radius:11px;padding:10px 13px;color:#48566c;font-size:16px}.library-rename-buttons{display:flex;justify-content:flex-end;gap:8px;margin-top:22px}.library-rename-buttons button{border:0;border-radius:12px;padding:12px 17px;color:#67778e;background:#f1f4f9;font-size:13px;min-height:44px}.library-rename-buttons button[type=submit]{background:#465979;color:white}.library-rename-error{font-size:12px;line-height:1.6;color:#b15b5b;margin:12px 0 0;min-height:0}
@media(max-width:700px){.library-header{padding:15px 14px 13px;gap:10px;flex-wrap:wrap}.library-header h2{font-size:23px}.library-create{padding:10px 13px;font-size:12px}#library-file-actions{order:4;width:100%;justify-content:flex-end}#library-file-actions:empty{display:none}#library-file-actions button{font-size:11px;min-height:38px}.library-tools{padding:17px 18px 0;gap:10px}.library-search{flex-basis:100%;max-width:none}.library-tabs{margin-right:auto}.library-tabs button{padding:8px 12px}.library-sort{max-width:132px;font-size:11px}.library-view-controls{display:none}.library-summary{padding:15px 20px 10px;font-size:11px;gap:8px}#notebook-list{grid-template-columns:repeat(auto-fill,minmax(145px,1fr));gap:14px;padding:6px 18px 34px}.library-preview{height:154px;padding:16px}.library-card-copy{padding:13px 12px}.library-card-title{font-size:13px}.library-card-date{font-size:10px}.library-card-detail{font-size:9px}.library-current-badge{font-size:9px}.library-card-more{width:36px;height:36px}.library-card{border-radius:14px}}
"""

LIBRARY_SCRIPT = LIBRARY_MODEL_SCRIPT + r"""
const notebookLibraryIcon=(name)=>'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+({
  back:'<path d="m14 6-6 6 6 6"/>',plus:'<path d="M12 4v16M4 12h16"/>',search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  list:'<path d="M9 5h12M9 12h12M9 19h12M3 5h1M3 12h1M3 19h1"/>',more:'<circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/>',
  book:'<path d="M5 3h12a2 2 0 0 1 2 2v16H7a3 3 0 0 1-3-3V5a2 2 0 0 1 1-2zM4 17h15M8 6h7"/>',trash:'<path d="M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7"/>'
}[name]||'')+'</svg>';
let notebookLibraryTab='notes',notebookLibraryView='grid',notebookLibrarySort='updated',notebookLibraryPending=null,notebookLibraryRenameId=null,notebookLibrarySequence=0;
try{const view=localStorage.getItem('beamerplus_library_view'),sort=localStorage.getItem('beamerplus_library_sort');if(['grid','list'].includes(view))notebookLibraryView=view;if(['updated','title'].includes(sort))notebookLibrarySort=sort;}catch(_){}
$('note-library').innerHTML=`
  <header class="library-header"><button type="button" class="icon-button" id="close-library" aria-label="ノートへ戻る">${notebookLibraryIcon('back')}</button><h2>ノート</h2><div id="library-file-actions"></div><button type="button" id="new-note" class="library-create">${notebookLibraryIcon('plus')}新しいノート</button></header>
  <div class="library-tools"><label class="library-search">${notebookLibraryIcon('search')}<input type="search" id="library-search" aria-label="ノートを検索" placeholder="ノートを検索" autocomplete="off"></label>
  <div class="library-tabs" role="tablist" aria-label="ノートの種類"><button type="button" id="library-notes-tab" role="tab" class="active">すべて<span id="library-notes-count" class="library-tab-count"></span></button><button type="button" id="library-trash-tab" role="tab">ゴミ箱<span id="library-trash-count" class="library-tab-count"></span></button></div>
  <select id="library-sort" class="library-sort" aria-label="ノートの並べ替え"><option value="updated">更新した順</option><option value="title">名前の順</option></select><div class="library-view-controls"><button type="button" id="library-grid" class="icon-button" aria-label="カードで表示">${notebookLibraryIcon('grid')}</button><button type="button" id="library-list" class="icon-button" aria-label="一覧で表示">${notebookLibraryIcon('list')}</button></div></div>
  <div class="library-summary"><span id="library-summary-count"></span><span id="library-message" class="library-message" role="status"></span></div><div id="notebook-list" role="list" aria-label="保存したノート"></div>`;
$('note-library').setAttribute('aria-modal','true');
const notebookLibraryMenu=document.createElement('div');notebookLibraryMenu.id='library-card-menu';notebookLibraryMenu.hidden=true;notebookLibraryMenu.setAttribute('role','menu');notebookLibraryMenu.setAttribute('aria-label','ノートの操作');document.body.appendChild(notebookLibraryMenu);
const notebookLibraryRename=document.createElement('div');notebookLibraryRename.id='library-rename-overlay';notebookLibraryRename.hidden=true;
notebookLibraryRename.innerHTML='<form class="library-rename-dialog" id="library-rename-form" role="dialog" aria-modal="true" aria-label="ノートの名前を変更"><h3>名前を変更</h3><input id="library-rename-title" aria-label="新しいノート名" maxlength="120" required><p id="library-rename-error" class="library-rename-error" role="alert"></p><div class="library-rename-buttons"><button type="button" id="library-rename-cancel">キャンセル</button><button type="submit" id="library-rename-save">変更する</button></div></form>';document.body.appendChild(notebookLibraryRename);
function notebookLibraryMessage(message,error=false){$('library-message').textContent=message;$('library-message').classList.toggle('error',error);}
function notebookLibraryDate(value){const timestamp=notebookLibraryTimestamp(value);if(!timestamp)return '';const date=new Date(timestamp),options={month:'short',day:'numeric'};if(date.getFullYear()!==new Date().getFullYear())options.year='numeric';return date.toLocaleDateString('ja-JP',options);}
function persistNotebookLibraryView(){try{localStorage.setItem('beamerplus_library_view',notebookLibraryView);localStorage.setItem('beamerplus_library_sort',notebookLibrarySort);}catch(_){}}
function openNotebookLibrary(){
  finishActiveInput();if(typeof flushNotebookTitle==='function')flushNotebookTitle();openOverlay('library-overlay');notebookLibraryMenu.hidden=true;renderNotebookLibrary();
  if(!notebookReady)notebookLibraryMessage('PCとの接続を待っています');
}
function closeNotebookLibrary(){$('library-overlay').hidden=true;notebookLibraryMenu.hidden=true;notebookLibraryRename.hidden=true;}
function beginNotebookLibraryNavigation(action,id){
  if(notebookLibraryPending)return false;finishActiveInput();if(typeof flushNotebookTitle==='function')flushNotebookTitle();
  const pending={action,id,beforeIds:notes.map(note=>note.id)},message=action==='new'?{type:'note_new'}:{type:'note_select',id};
  if(!sendWS(message)){notebookLibraryMessage('PCに接続してから、もう一度お試しください',true);return false;}
  notebookLibraryPending=pending;notebookLibraryMessage(action==='new'?'新しいノートを作成中…':'ノートを開いています…');renderNotebookLibrary();return true;
}
function requestNotebookLibraryAction(action,id,extra={}){
  if(notebookLibraryPending)return false;
  if(!['rename','duplicate','trash','restore'].includes(action)||!notes.some(note=>note.id===id))return false;
  finishActiveInput();if(typeof flushNotebookTitle==='function')flushNotebookTitle();
  const requestId='library_'+Date.now().toString(36)+'_'+(++notebookLibrarySequence);
  if(!sendWS({type:'note_library',action,id,...extra,requestId})){notebookLibraryMessage('PCに接続してから、もう一度お試しください',true);return false;}
  notebookLibraryPending={action,id,...extra,requestId};notebookLibraryMenu.hidden=true;notebookLibraryMessage('変更を保存しています…');$('library-rename-save').disabled=true;renderNotebookLibrary();return true;
}
function openNotebookRename(id){
  const note=notes.find(item=>item.id===id);if(!note||notebookLibraryPending)return;
  finishActiveInput();notebookLibraryMenu.hidden=true;notebookLibraryRenameId=id;$('library-rename-title').value=note.title||'新しいノート';$('library-rename-error').textContent='';$('library-rename-save').disabled=false;notebookLibraryRename.hidden=false;$('library-rename-title').focus();$('library-rename-title').select();
}
function openNotebookLibraryMenu(note,anchor){
  if(notebookLibraryPending)return;notebookLibraryMenu.replaceChildren();
  for(const [action,label,danger] of [['rename','名前を変更'],['duplicate','複製'],['trash','ゴミ箱へ移動',true]]){
    const b=document.createElement('button');b.type='button';b.textContent=label;b.setAttribute('role','menuitem');if(danger)b.className='danger';b.addEventListener('click',()=>action==='rename'?openNotebookRename(note.id):requestNotebookLibraryAction(action,note.id));notebookLibraryMenu.appendChild(b);
  }
  const r=anchor.getBoundingClientRect();notebookLibraryMenu.style.left=`${Math.max(12,Math.min(window.innerWidth-217,r.right-205))}px`;notebookLibraryMenu.style.top=`${Math.max(12,Math.min(window.innerHeight-172,r.bottom+5))}px`;notebookLibraryMenu.hidden=false;
}
function notebookLibraryCard(note){
  const trashed=!!note.deletedAt,card=document.createElement('article');card.className='library-card';card.classList.toggle('current',!trashed&&note.id===currentDocumentId);card.classList.toggle('trashed',trashed);card.setAttribute('role','listitem');card.dataset.noteId=note.id;
  const open=document.createElement('button');open.type='button';open.className='library-card-main';open.disabled=!!notebookLibraryPending||trashed;open.setAttribute('aria-label',`${note.title||'新しいノート'}${trashed?'、ゴミ箱':' を開く'}`);
  const preview=document.createElement('div');preview.className='library-preview';preview.setAttribute('aria-hidden','true');const page=document.createElement('div');page.className='library-paper';if(['ruled','grid'].includes(note.paper))page.classList.add(note.paper);page.innerHTML=notebookLibraryIcon('book');preview.appendChild(page);open.appendChild(preview);
  if(note.id===currentDocumentId&&!trashed){const current=document.createElement('span');current.className='library-current-badge';current.textContent='開いているノート';open.appendChild(current);}
  const copy=document.createElement('div');copy.className='library-card-copy';const title=document.createElement('strong');title.className='library-card-title';title.textContent=note.title||'新しいノート';copy.appendChild(title);
  const date=document.createElement('span');date.className='library-card-date';const stamp=notebookLibraryDate(trashed?note.deletedAt:note.updatedAt||note.createdAt);date.textContent=stamp?(trashed?'移動 ':'更新 ')+stamp:'保存したノート';copy.appendChild(date);
  const detail=document.createElement('span');detail.className='library-card-detail';const counts=[],ink=notebookLibraryCount(note.strokeCount),text=notebookLibraryCount(note.textCount);if(ink!==null)counts.push(`筆跡 ${ink}`);if(text!==null)counts.push(`テキスト ${text}`);const paperLabel={plain:'白紙',ruled:'横罫線',grid:'方眼'}[note.paper]||'白紙';detail.textContent=[paperLabel,...counts].join(' · ');copy.appendChild(detail);open.appendChild(copy);open.addEventListener('click',()=>beginNotebookLibraryNavigation('select',note.id));card.appendChild(open);
  const more=document.createElement('button');more.type='button';more.disabled=!!notebookLibraryPending;
  if(trashed){more.className='library-restore';more.textContent='復元';more.setAttribute('aria-label',`${note.title||'新しいノート'} を復元`);more.addEventListener('click',()=>requestNotebookLibraryAction('restore',note.id));}
  else{more.className='icon-button library-card-more';more.innerHTML=notebookLibraryIcon('more');more.setAttribute('aria-label',`${note.title||'新しいノート'} の操作`);more.addEventListener('click',e=>{e.stopPropagation();openNotebookLibraryMenu(note,more);});}
  card.appendChild(more);return card;
}
function renderNotebookLibrary(){
  notebookLibraryMenu.hidden=true;
  const trash=notebookLibraryTab==='trash',items=notebookLibraryNotes(notes,{trash,query:$('library-search').value,sort:notebookLibrarySort});
  $('library-notes-count').textContent=notes.filter(note=>!note.deletedAt).length;$('library-trash-count').textContent=notes.filter(note=>!!note.deletedAt).length;
  for(const [id,active] of [['library-notes-tab',!trash],['library-trash-tab',trash]]){$(id).classList.toggle('active',active);$(id).setAttribute('aria-selected',String(active));}
  $('library-summary-count').textContent=`${items.length} 件${trash?' · ゴミ箱のノートは復元できます':''}`;
  $('library-sort').value=notebookLibrarySort;$('library-grid').classList.toggle('active',notebookLibraryView==='grid');$('library-list').classList.toggle('active',notebookLibraryView==='list');$('new-note').disabled=!!notebookLibraryPending||!notebookReady;
  const list=$('notebook-list');list.classList.toggle('library-list-view',notebookLibraryView==='list');list.replaceChildren();
  if(!items.length){
    const empty=document.createElement('div');empty.className='library-empty';empty.innerHTML=notebookLibraryIcon(trash?'trash':'book');const title=document.createElement('strong');title.textContent=$('library-search').value.trim()?'見つかりませんでした':trash?'ゴミ箱は空です':'最初のノートを作りましょう';const message=document.createElement('p');message.textContent=$('library-search').value.trim()?'別の言葉でノート名を検索してください。':trash?'移動したノートはここから復元できます。':'右上の「新しいノート」から、書き始められます。';empty.append(title,message);list.appendChild(empty);
  }else for(const note of items)list.appendChild(notebookLibraryCard(note));
}
const openLibraryBefore=$('open-library'),openLibraryReplacement=openLibraryBefore.cloneNode(true);openLibraryBefore.replaceWith(openLibraryReplacement);openLibraryReplacement.addEventListener('click',openNotebookLibrary);
$('close-library').addEventListener('click',closeNotebookLibrary);$('new-note').addEventListener('click',()=>beginNotebookLibraryNavigation('new'));
$('library-search').addEventListener('input',()=>{notebookLibraryMenu.hidden=true;renderNotebookLibrary();});
$('library-sort').addEventListener('change',e=>{notebookLibrarySort=e.target.value;persistNotebookLibraryView();renderNotebookLibrary();});
for(const [id,view] of [['library-grid','grid'],['library-list','list']])$(id).addEventListener('click',()=>{notebookLibraryView=view;persistNotebookLibraryView();renderNotebookLibrary();});
for(const [id,tab] of [['library-notes-tab','notes'],['library-trash-tab','trash']])$(id).addEventListener('click',()=>{notebookLibraryTab=tab;notebookLibraryMenu.hidden=true;renderNotebookLibrary();});
$('library-rename-cancel').addEventListener('click',()=>notebookLibraryRename.hidden=true);
notebookLibraryRename.addEventListener('pointerdown',e=>{if(e.target===notebookLibraryRename&&!notebookLibraryPending)notebookLibraryRename.hidden=true;});
$('library-rename-form').addEventListener('submit',e=>{e.preventDefault();const title=$('library-rename-title').value.trim();if(!title){$('library-rename-error').textContent='ノート名を入力してください';return;}requestNotebookLibraryAction('rename',notebookLibraryRenameId,{title});});
document.addEventListener('pointerdown',e=>{if(!notebookLibraryMenu.hidden&&!notebookLibraryMenu.contains(e.target)&&!e.target.closest?.('.library-card-more'))notebookLibraryMenu.hidden=true;});
const closeOverlaysBeforeLibrary=closeOverlays;closeOverlays=function(){closeOverlaysBeforeLibrary();notebookLibraryMenu.hidden=true;notebookLibraryRename.hidden=true;};
const renderNotesBeforeLibrary=renderNotes;renderNotes=function(){renderNotesBeforeLibrary();renderNotebookLibrary();};
const handleMessageBeforeLibrary=handleServerMessage;handleServerMessage=function(msg){
  const result=handleMessageBeforeLibrary(msg);
  if(msg.type==='state_sync'){
    renderNotebookLibrary();const pending=notebookLibraryPending;
    if(pending&&(pending.action==='select'&&msg.documentId===pending.id||pending.action==='new'&&msg.documentId&&!pending.beforeIds.includes(msg.documentId))){notebookLibraryPending=null;notebookLibraryMessage('');closeNotebookLibrary();renderNotebookLibrary();}
  }else if(msg.type==='note_library_result'&&notebookLibraryPending?.requestId===msg.requestId){
    const pending=notebookLibraryPending;notebookLibraryPending=null;$('library-rename-save').disabled=false;
    if(msg.ok){notebookLibraryRename.hidden=true;const message={rename:'名前を変更しました',duplicate:'ノートを複製しました',trash:'ゴミ箱へ移動しました',restore:'ノートを復元しました'}[pending.action];notebookLibraryMessage(message||'保存しました');if($('library-overlay').hidden)showToast(message||'保存しました');}
    else{const message=msg.message||msg.error||'変更を保存できませんでした';notebookLibraryMessage(message,true);$('library-rename-error').textContent=message;showToast(message);}
    renderNotebookLibrary();
  }else if(msg.type==='note_error'&&notebookLibraryPending){notebookLibraryPending=null;$('library-rename-save').disabled=false;const message=msg.message||'操作を完了できませんでした';notebookLibraryMessage(message,true);if(!notebookLibraryRename.hidden)$('library-rename-error').textContent=message;renderNotebookLibrary();}
  return result;
};
const connectionBeforeLibrary=updateAssistantConnection;updateAssistantConnection=function(connected){const result=connectionBeforeLibrary(connected);if(!connected){notebookLibraryPending=null;$('library-rename-save').disabled=false;notebookLibraryMessage('PCとの接続を待っています');}renderNotebookLibrary();return result;};
renderNotebookLibrary();
"""
