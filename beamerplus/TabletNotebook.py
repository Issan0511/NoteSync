"""Notebook-first tablet UI, favorite pen wheel, and ink settings."""

from beamerplus.TabletInput import INPUT_SCRIPT
from beamerplus.TabletAssistant import ASSISTANT_MARKUP, ASSISTANT_SCRIPT, ASSISTANT_STYLE
from beamerplus.TabletNavigation import NAVIGATION_SCRIPT, NAVIGATION_STYLE
from beamerplus.TabletSelection import SELECTION_SCRIPT, SELECTION_STYLE
from beamerplus.TabletFavorites import FAVORITES_SCRIPT, FAVORITES_STYLE
from beamerplus.TabletEraserCursor import ERASER_CURSOR_SCRIPT
from beamerplus.TabletLibrary import LIBRARY_SCRIPT, LIBRARY_STYLE
from beamerplus.TabletMenus import MENUS_SCRIPT, MENUS_STYLE
from beamerplus.NotebookText import NOTE_TEXT_SCRIPT
from beamerplus.TabletText import INSTALL_TEXT_SCRIPT
from beamerplus.TabletVersion import VERSION_SCRIPT


ICONS = {
    'back': '<path d="m14 6-6 6 6 6"/>',
    'book': '<path d="M4 4h6a3 3 0 0 1 3 3v14a3 3 0 0 0-3-3H4zM13 7a3 3 0 0 1 3-3h5v14h-5a3 3 0 0 0-3 3"/>',
    'pen': '<path d="m5 19 3-1 11-11-3-3L5 15zM13 7l4 4M4 21h16"/>',
    'highlighter': '<path d="m5 17 8-12 6 4-8 12zM6 15l7 5M4 21h10"/>',
    'eraser': '<path d="m3 14 9-10a2 2 0 0 1 3 0l6 6a2 2 0 0 1 0 3l-7 8H9zM8 9l9 9M13 21h8"/>',
    'star': '<path d="m12 3 3 6 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1z"/>',
    'undo': '<path d="m8 5-5 5 5 5M3 10h10a6 6 0 0 1 6 6v3"/>',
    'redo': '<path d="m16 5 5 5-5 5m5-5H11a6 6 0 0 0-6 6v3"/>',
    'line': '<path d="m4 20 16-16M3 16l5 5M16 3l5 5"/>',
    'settings': '<path d="M4 6h16M4 12h16M4 18h16M8 3v6m8 0v6M9 15v6"/>',
    'more': '<circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/>',
    'download': '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
    'close': '<path d="m6 6 12 12M18 6 6 18"/>',
    'plus': '<path d="M12 4v16M4 12h16"/>',
}


def icon(name):
    return f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>'


def button(name, label, identifier, extra=''):
    return f'<button type="button" class="icon-button" id="{identifier}" aria-label="{label}" title="{label}" {extra}>{icon(name)}</button>'


STYLE = r"""
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;font-family:system-ui,-apple-system,'Noto Sans',sans-serif;color:#27292e;background:#ebebee}
button,input,select{font:inherit}button{cursor:pointer;-webkit-tap-highlight-color:transparent}button:disabled{opacity:.3;cursor:default}button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid #617de7;outline-offset:3px}
svg{width:24px;height:24px;display:block;flex-shrink:0}.icon-button{display:grid;place-items:center;width:44px;height:44px;flex-shrink:0;border:0;border-radius:50%;color:#4d4f56;background:transparent;transition:background .15s,color .15s}
.icon-button:hover{background:#ededf2}.icon-button.active{background:#e6e9f2;color:#202124}.icon-button.pen-button-active{background:#e6d5ae;color:#73531a}
#notebook-header{height:72px;background:#fcfcfd;display:flex;align-items:center;gap:12px;padding:0 24px 0 16px;border-bottom:1px solid #e0e0e4;position:relative;z-index:30}
#note-title{font-size:21px;font-weight:600;min-width:60px;width:350px;max-width:40vw;border:0;outline:none;background:transparent;color:#24262b;padding:8px 0;text-overflow:ellipsis}
.header-space{flex:1}.connection{width:7px;height:7px;border-radius:50%;background:#b5b7be;margin-right:6px}.connection.online{background:#67a292}#save-status{font-size:12px;color:#909299;white-space:nowrap}
#stage{position:absolute;left:0;right:76px;top:72px;bottom:30px;width:auto;height:auto;display:flex;align-items:center;justify-content:center;overflow:auto;padding:22px;touch-action:none}
#slide-wrapper{position:relative;flex-shrink:0;background:white;box-shadow:0 1px 6px #20212408;overflow:hidden;border-radius:1px;touch-action:none}
#slide-wrapper.ruled{background-image:repeating-linear-gradient(to bottom,transparent 0px,transparent calc(var(--paper-gap,36px) - 1px),#e7eaf1 var(--paper-gap,36px))}
#slide-wrapper.grid{background-image:linear-gradient(#e9edf3 1px,transparent 1px),linear-gradient(90deg,#e9edf3 1px,transparent 1px);background-size:var(--paper-gap,32px) var(--paper-gap,32px)}
canvas{position:absolute;inset:0;width:100%;height:100%;touch-action:none}#committed-canvas{pointer-events:none}#active-canvas{cursor:crosshair}
#tool-rail{position:absolute;right:0;top:72px;bottom:0;width:76px;background:#fcfcfd;border-left:1px solid #dedee4;display:flex;align-items:center;flex-direction:column;gap:4px;padding:12px 0;z-index:35;overflow-y:auto;scrollbar-width:none}
#tool-rail .icon-button{width:40px;height:40px}.rail-divider{height:1px;width:28px;background:#e5e5e9;margin:4px 0;flex-shrink:0}.color-dot{width:24px;height:24px;flex-shrink:0;border:0;border-radius:50%;margin:3px 0;box-shadow:inset 0 0 0 1px #0000000a}.color-dot.active{outline:2px solid #999da7;outline-offset:4px}
#page-footer{position:absolute;left:26px;right:100px;bottom:10px;display:flex;justify-content:space-between;font-size:11px;color:#92949c;pointer-events:none}
.overlay{position:fixed;inset:0;z-index:120;background:transparent}.overlay[hidden]{display:none!important}.sheet{position:absolute;background:#fff;border:1px solid #e4e4ea;box-shadow:0 12px 45px #1b203323;border-radius:20px;padding:22px;width:320px;max-height:calc(100dvh - 100px);overflow:auto}
.sheet h2{font-size:17px;margin:0;font-weight:650}.sheet-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px}.sheet-head .icon-button{width:28px;height:28px}.sheet label,.section-label{display:block;font-size:12px;color:#858892;margin:20px 0 10px}.setting-row{display:flex;gap:8px;align-items:center}.setting-row input[type=range]{width:100%;accent-color:#4a5c88}.setting-row output{min-width:36px;text-align:right;font-size:12px;color:#646975}
.brush-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}.brush-choice{border:1px solid #e6e6ed;background:#fafafa;border-radius:12px;padding:12px 2px 9px;color:#7c7f87;font-size:10px;display:flex;align-items:center;flex-direction:column;gap:7px}.brush-choice.active{border-color:#7889b2;background:#f0f3fa;color:#354972}.brush-choice svg{height:34px;width:28px}
.swatches{display:flex;flex-wrap:wrap;gap:12px}.swatch{width:28px;height:28px;border-radius:50%;border:1px solid #0000000d}.swatch.active{outline:2px solid #9ca3b5;outline-offset:3px}#custom-color{width:30px;height:30px;border:0;background:none;padding:0;border-radius:50%;cursor:pointer}
.wide-button{width:100%;border:1px solid #e3e5ec;border-radius:10px;background:#f7f8fa;color:#4e5670;padding:11px 12px;text-align:center;font-size:12px}.wide-button.danger{color:#ad5151;background:#fff}#pen-button-mode,#pen-button-mode option{color:#4e5670;background:#f7f8fa}#pen-preview{position:relative;height:50px;width:100%;border-radius:10px;background:#fafafa;margin-top:18px}
#pen-settings{top:86px;right:90px}#note-options{top:65px;right:90px}#eraser-settings{top:150px;right:90px}.segmented{display:flex;gap:8px}.segmented button{flex:1;padding:12px 4px;border:1px solid #e3e5ec;border-radius:10px;color:#757982;background:#fff;font-size:12px}.segmented button.active{color:#354972;border-color:#7889b2;background:#f0f3fa}
#favorites-wheel{position:fixed;width:258px;height:258px;max-width:90vw;max-height:90vw;border-radius:50%;background:#ffffffef;backdrop-filter:blur(12px);box-shadow:0 5px 30px #262c3c19;border:1px solid #eeeeef;overflow:visible}
#wheel-center{position:absolute;inset:65px;border-radius:50%;background:radial-gradient(circle at 42% 35%,#fff,#f0f0f4 80%);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;box-shadow:inset 0 0 8px #c5c8d322;color:#2d3342}
#wheel-center svg{width:45px;height:90px;transform:rotate(-35deg)}#wheel-label{font-size:10px;color:#8d8f98;position:absolute;bottom:14px}.wheel-favorite{position:absolute;width:40px;height:40px;border:0;border-radius:50%;display:grid;place-items:center;background:#f4f4f7;color:var(--ink);box-shadow:0 1px 3px #00000004}.wheel-favorite.active{outline:2px solid #aab4cb;outline-offset:3px}.wheel-favorite svg{width:22px;height:22px}.wheel-command{position:absolute;width:32px;height:32px;bottom:5px;left:113px;color:#777f94;background:white;border:1px solid #ececf2;border-radius:50%;display:grid;place-items:center}
.favorite-row{display:flex;gap:10px;align-items:center;padding:10px 0;border-bottom:1px solid #f0f1f5;font-size:12px}.favorite-row .favorite-apply{display:flex;align-items:center;gap:9px;flex:1;padding:0;border:0;background:none;text-align:left;color:#555b6d}.favorite-row .icon-button{width:25px;height:25px}.favorite-row svg{width:19px;height:19px}
#library-overlay{background:#292d3a24}#note-library{position:absolute;inset:0 auto 0 0;width:320px;max-width:90vw;background:#fbfbfc;padding:24px;box-shadow:8px 0 35px #0001;overflow:auto}.library-title{font-size:23px;font-weight:650;margin:20px 0 24px}.note-row{width:100%;padding:18px 14px;border:1px solid #e4e5ec;border-radius:12px;background:#fff;margin:9px 0;text-align:left;color:#535764}.note-row.active{background:#edf1f8;border-color:#b6c1d8;color:#354972}.note-row small{display:block;margin-top:7px;color:#a2a6b0;font-size:10px}
#toast{position:fixed;bottom:30px;left:50%;transform:translate(-50%,10px);background:#343947;color:#fff;padding:11px 18px;border-radius:30px;font-size:12px;z-index:130;opacity:0;pointer-events:none;transition:opacity .2s,transform .2s}#toast.show{opacity:1;transform:translate(-50%,0)}
#assistant-launch{right:90px;bottom:17px;padding:10px 15px;border-radius:30px;border:0;background:#323e57;color:#fff;font-size:12px;box-shadow:0 4px 12px #0001}#assistant-panel{width:360px;background:#fbfbfd;color:#353b49;border-color:#dedfe7;box-shadow:-10px 0 40px #00000008;padding:22px}#assistant-panel .btn{border:1px solid #e1e3ec;border-radius:10px;padding:8px 12px;background:white;color:#5b6275}#assistant-panel #assistant-send{background:#465979;color:white;border:0}#assistant-messages .assistant-message{background:#f0f1f5;color:#41495a}#assistant-messages .question{background:#eaf0f8;border:1px solid #d8e1ef}#assistant-question{background:white;color:#3a4254;border:1px solid #d9dde8}#assistant-status,.assistant-hint{color:#8a91a1}#assistant-panel h2{margin:0}#assistant-question::placeholder{color:#a2a8b6}
body.assistant-open #stage{right:436px;width:auto;height:auto}body.assistant-open #tool-rail{right:360px}body.assistant-open #page-footer{right:460px}
#auth-overlay{position:fixed;inset:0;display:none;align-items:center;justify-content:center;background:#ebebeee8;z-index:200}.auth-card{width:320px;background:white;padding:30px;border-radius:22px;box-shadow:0 10px 50px #0001}.auth-card input{width:100%;padding:12px;margin:14px 0;border:1px solid #d7dce7;border-radius:9px}.auth-card button{width:100%;padding:12px;border:0;border-radius:9px;background:#465979;color:white}#auth-error{font-size:12px;color:#b65252}
@media(max-width:900px){#notebook-header{height:62px;padding:0 10px;gap:2px}#note-title{font-size:17px;width:180px;max-width:44vw}#notebook-header .icon-button{width:36px;height:40px}#save-status{display:none}#tool-rail{top:62px;width:58px;padding:12px 0;gap:7px}#stage{top:62px;right:58px;padding:12px}#page-footer{left:16px;right:75px;font-size:10px}.sheet{max-width:calc(100vw - 22px)}#pen-settings,#eraser-settings,#note-options{right:12px;top:70px}#assistant-launch{right:72px;bottom:18px;font-size:11px}body.assistant-open #stage{width:auto;right:58px;bottom:calc(55dvh + 20px);height:auto}body.assistant-open #tool-rail{right:0;bottom:55dvh}body.assistant-open #assistant-panel{width:100%;height:55dvh;top:auto;bottom:0;right:0;padding:14px;border-left:0;border-top:1px solid #dedfe7}#header-redo{display:none}#page-footer span:first-child{display:none}}
"""

MARKUP = f"""
<header id="notebook-header">
{button('back', 'ノート一覧', 'open-library')}
<input id="note-title" aria-label="ノート名" maxlength="120" value="新しいノート" spellcheck="false" disabled>
<div class="header-space"></div><span id="status-dot" class="connection" title="PCに接続中"></span><span id="save-status">接続中</span>
{button('undo','元に戻す','header-undo')}{button('redo','やり直す','header-redo')}{button('more','ノートの設定','open-options')}
</header>
<main id="stage"><div id="slide-wrapper"><canvas id="committed-canvas"></canvas><canvas id="active-canvas" aria-label="手書きノート"></canvas></div></main>
<nav id="tool-rail" aria-label="筆記用具">
{button('pen','ペン・ペン設定','btn-pen')}{button('highlighter','蛍光ペン','btn-highlighter')}{button('eraser','消しゴム・消しゴム設定','btn-eraser')}{button('line','直線','btn-line')}{button('star','お気に入りのペン','open-favorites')}
<div class="rail-divider"></div><button class="color-dot" data-color="#202124" style="background:#202124" aria-label="黒"></button><button class="color-dot" data-color="#ef5350" style="background:#ef5350" aria-label="赤"></button><button class="color-dot" data-color="#3478dc" style="background:#3478dc" aria-label="青"></button><button class="color-dot" data-color="#42b68e" style="background:#42b68e" aria-label="緑"></button>
<div class="rail-divider"></div>{button('settings','ペンの設定','open-pen-settings')}{button('undo','元に戻す','rail-undo')}{button('redo','やり直す','rail-redo')}
</nav><footer id="page-footer"><span>S Penボタンをダブルクリック · お気に入り</span><span id="note-footer">白紙のノート</span></footer>
<div id="pen-overlay" class="overlay" hidden><section id="pen-settings" class="sheet" role="dialog" aria-label="ペンの設定">
<div class="sheet-head"><h2>ペン</h2>{button('close','閉じる','close-pen-settings')}</div>
<div class="brush-grid"><button class="brush-choice" data-brush="pen">{icon('pen')}ボールペン</button><button class="brush-choice" data-brush="fountain">{icon('pen')}万年筆</button><button class="brush-choice" data-brush="pencil">{icon('pen')}鉛筆</button><button class="brush-choice" data-brush="highlighter">{icon('highlighter')}蛍光ペン</button></div>
<label for="pen-size">太さ</label><div class="setting-row"><input id="pen-size" type="range" min="1" max="30" value="4"><output id="pen-size-value">4</output></div>
<label for="pen-opacity">濃さ</label><div class="setting-row"><input id="pen-opacity" type="range" min="10" max="100" value="100"><output id="pen-opacity-value">100%</output></div>
<span class="section-label">色</span><div id="pen-colors" class="swatches"></div><canvas id="pen-preview" width="276" height="50" aria-label="線のプレビュー"></canvas>
<div style="height:18px"></div><button class="wide-button" id="save-favorite">☆ このペンをお気に入りに追加</button><span class="section-label">お気に入り</span><div id="favorite-list"></div>
</section></div>
<div id="wheel-overlay" class="overlay" hidden><section id="favorites-wheel" role="dialog" aria-label="お気に入りのペン"><div id="wheel-center">{icon('pen')}<span id="wheel-label">お気に入り</span></div><div id="wheel-presets"></div><button class="wheel-command" id="wheel-settings" aria-label="お気に入りを編集">{icon('plus')}</button></section></div>
<div id="eraser-overlay" class="overlay" hidden><section id="eraser-settings" class="sheet" role="dialog" aria-label="消しゴムの設定"><div class="sheet-head"><h2>消しゴム</h2>{button('close','閉じる','close-eraser-settings')}</div><div class="segmented"><button data-erase="partial">触れた部分</button><button data-erase="stroke">ストローク全体</button></div><label for="eraser-size">消しゴムの大きさ</label><input id="eraser-size" type="range" min="5" max="70" value="18" style="width:100%;accent-color:#657da5"><p style="font-size:12px;line-height:1.7;color:#9297a2">S Penボタンを押している間も、この設定で消せます。消した操作は「元に戻す」で復元できます。</p></section></div>
<div id="options-overlay" class="overlay" hidden><section id="note-options" class="sheet" role="dialog" aria-label="ノートの設定"><div class="sheet-head"><h2>ノート</h2>{button('close','閉じる','close-options')}</div><label for="paper-style">用紙</label><select id="paper-style" class="wide-button"><option value="plain">白紙</option><option value="ruled">横罫線</option><option value="grid">方眼</option></select><label for="pen-button-mode">S Penボタン</label><select id="pen-button-mode" class="wide-button"><option value="hold">押している間だけ消す</option><option value="toggle">クリックでペンと消しゴムを切替</option></select><label><input type="checkbox" id="penOnlyToggle" checked> ペンのみで書く</label><button id="export-note" class="wide-button">画像として保存</button><div style="height:10px"></div><button id="clear-note" class="wide-button danger">このノートの筆跡を消す</button></section></div>
<div id="library-overlay" class="overlay" hidden><aside id="note-library" role="dialog" aria-label="ノート一覧"><div class="sheet-head"><h2>ノート</h2>{button('close','閉じる','close-library')}</div><div class="library-title">考えたことを、<br>そのまま。</div><button id="new-note" class="wide-button">＋ 新しいノート</button><div id="notebook-list"></div></aside></div>
<div id="auth-overlay"><form class="auth-card" id="auth-form"><h2>ノートに接続</h2><p style="font-size:12px;color:#9097a4">PCに表示されたパスコードを入力してください。</p><input type="password" id="passcode-input" aria-label="パスコード" autocomplete="off"><div id="auth-error"></div><button type="submit">接続</button></form></div><div id="toast" role="status"></div>
"""

SCRIPT = r"""
    const $ = id => document.getElementById(id);
    const stage=$('stage'),slideWrapper=$('slide-wrapper'),activeCanvas=$('active-canvas'),committedCanvas=$('committed-canvas');
    const activeCtx=activeCanvas.getContext('2d'),committedCtx=committedCanvas.getContext('2d');
    const btnPen=$('btn-pen'),btnHighlighter=$('btn-highlighter'),btnEraser=$('btn-eraser'),penOnlyToggle=$('penOnlyToggle'),penButtonModeSelect=$('pen-button-mode');
    let currentTool='pen',currentColor='#202124',selectedBrush='pen',isLineMode=false,isDrawing=false,isSketchbook=true,isSketchVisible=true;
    let currentStrokePoints=[],sketchbookStrokes=[],noteTexts=[],slideStrokes=[],currentDocumentId='',currentPage=0,slideImageReady=true,isTrackingSwipe=false;
    let eraserMode='stroke',toolSizes={pen:4,highlighter:22,eraser:18},toolOpacities={pen:1,highlighter:.3};
    let notebookReady=false,notes=[],paper='plain',paperAspect=4/3,selectedFavorite=-1,remoteStroke=null;
    const brushNames={pen:'ボールペン',fountain:'万年筆',pencil:'鉛筆',highlighter:'蛍光ペン'};
    const defaultFavorites=[{brush:'pen',color:'#202124',size:4,opacity:1},{brush:'pen',color:'#3478dc',size:4,opacity:1},{brush:'fountain',color:'#ef5350',size:5,opacity:1},{brush:'highlighter',color:'#ffcf59',size:22,opacity:.3}];
    let favorites=defaultFavorites.map(p=>({...p}));
    let brushMemory={pen:{brush:'pen',color:'#202124',size:4,opacity:1},fountain:{brush:'fountain',color:'#202124',size:5,opacity:1},pencil:{brush:'pencil',color:'#69717b',size:3,opacity:.6},highlighter:{brush:'highlighter',color:'#ffcf59',size:22,opacity:.3}};
    function validPreset(p){return p&&Object.hasOwn(brushNames,p.brush)&&/^#[0-9a-f]{6}$/i.test(p.color)&&Number.isFinite(p.size)&&p.size>=1&&p.size<=80&&Number.isFinite(p.opacity)&&p.opacity>=.1&&p.opacity<=1;}
    try{const saved=JSON.parse(localStorage.getItem('beamerplus_favorite_pens'));if(Array.isArray(saved)&&saved.length&&saved.length<=6&&saved.every(validPreset))favorites=saved;const pen=JSON.parse(localStorage.getItem('beamerplus_current_pen'));if(validPreset(pen)){selectedBrush=pen.brush;currentTool=pen.brush==='highlighter'?'highlighter':'pen';currentColor=pen.color;toolSizes[currentTool]=pen.size;toolOpacities[currentTool]=pen.opacity;}}catch(_){}
    try{const saved=JSON.parse(localStorage.getItem('beamerplus_brush_settings'));for(const brush of Object.keys(brushMemory))if(validPreset(saved?.[brush]))brushMemory[brush]=saved[brush];}catch(_){}
    function persistPens(){brushMemory[selectedBrush]=currentPreset();try{localStorage.setItem('beamerplus_favorite_pens',JSON.stringify(favorites));localStorage.setItem('beamerplus_current_pen',JSON.stringify(currentPreset()));localStorage.setItem('beamerplus_brush_settings',JSON.stringify(brushMemory));}catch(_){showToast('このブラウザではペン設定を保存できません');}}
    function currentPreset(){const tool=selectedBrush==='highlighter'?'highlighter':'pen';return {brush:selectedBrush,color:currentColor,size:toolSizes[tool],opacity:toolOpacities[tool]};}
    function getCurrentBrush(){return selectedBrush;}
    function getToolOpacity(){return toolOpacities[selectedBrush==='highlighter'?'highlighter':'pen'];}
    function getCurrentWidthRatio(){return toolSizes[selectedBrush==='highlighter'?'highlighter':'pen']*.001;}
    function canEditNotebook(){return notebookReady;}
    function startSwipe(){isTrackingSwipe=false;}function checkSwipe(){isTrackingSwipe=false;}
    function getPointerNormPos(e){const r=slideWrapper.getBoundingClientRect();return {normX:Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),normY:Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))};}
    function drawStroke(ctx,stroke){
      const points=stroke.points;if(!points||!points.length)return;const w=slideWrapper.clientWidth,h=slideWrapper.clientHeight,width=Math.max(.6,Math.min(w,h)*stroke.width_ratio);
      ctx.save();ctx.strokeStyle=stroke.color;ctx.fillStyle=stroke.color;ctx.globalAlpha=stroke.opacity??1;ctx.lineWidth=width;ctx.lineCap=stroke.brush==='highlighter'?'butt':'round';ctx.lineJoin='round';
      if(points.length===1){ctx.beginPath();ctx.arc(points[0][0]*w,points[0][1]*h,width/2,0,Math.PI*2);ctx.fill();}
      else if(stroke.brush==='fountain'){
        for(let i=1;i<points.length;i++){const a=points[i-1],b=points[i];ctx.lineWidth=width*(.35+.9*((a[2]??1)+(b[2]??1))/2);ctx.beginPath();ctx.moveTo(a[0]*w,a[1]*h);ctx.lineTo(b[0]*w,b[1]*h);ctx.stroke();}
      }else{ctx.beginPath();ctx.moveTo(points[0][0]*w,points[0][1]*h);for(let i=1;i<points.length-1;i++){const a=points[i],b=points[i+1];ctx.quadraticCurveTo(a[0]*w,a[1]*h,(a[0]+b[0])*w/2,(a[1]+b[1])*h/2);}const end=points.at(-1);ctx.lineTo(end[0]*w,end[1]*h);ctx.stroke();}ctx.restore();
    }
    __NOTE_TEXT_SCRIPT__
    function renderAllStrokes(strokes){committedCtx.clearRect(0,0,committedCanvas.width,committedCanvas.height);for(const stroke of strokes)drawStroke(committedCtx,stroke);drawNoteTexts(committedCtx,noteTexts,slideWrapper.clientWidth,slideWrapper.clientHeight);}
    function adjustLayout(){
      finishActiveInput();const r=stage.getBoundingClientRect(),width=Math.max(40,Math.min(r.width-44,(r.height-48)*paperAspect)),height=width/paperAspect;
      slideWrapper.style.setProperty('--paper-gap',`${height/24}px`);slideWrapper.style.width=`${width}px`;slideWrapper.style.height=`${height}px`;const dpr=window.devicePixelRatio||1;
      for(const canvas of [activeCanvas,committedCanvas]){canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);canvas.getContext('2d').setTransform(dpr,0,0,dpr,0,0);}renderAllStrokes(sketchbookStrokes);
    }
    let toastTimer;function showToast(message){$('toast').textContent=message;$('toast').classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').classList.remove('show'),2800);}
    function closeOverlays(){for(const id of ['pen-overlay','wheel-overlay','eraser-overlay','options-overlay','library-overlay'])$(id).hidden=true;}
    function openOverlay(id){finishActiveInput();closeOverlays();$(id).hidden=false;}
    for(const id of ['pen-overlay','wheel-overlay','eraser-overlay','options-overlay','library-overlay'])$(id).addEventListener('pointerdown',e=>{if(e.target===$(id)){e.preventDefault();closeOverlays();}});
    for(const [id,overlay] of [['close-pen-settings','pen-overlay'],['close-eraser-settings','eraser-overlay'],['close-options','options-overlay'],['close-library','library-overlay']])$(id).addEventListener('click',()=>$(overlay).hidden=true);
    document.addEventListener('keydown',e=>{if(e.key==='Escape')closeOverlays();if((e.ctrlKey||e.metaKey)&&!['INPUT','TEXTAREA'].includes(e.target.tagName)&&e.key.toLowerCase()==='z'){e.preventDefault();finishActiveInput();sendWS({type:e.shiftKey?'redo':'undo'});}});
    function selectTool(tool){finishActiveInput();currentTool=tool;updatePenUI();}
    function updateLineModeUI(){$('btn-line').classList.toggle('active',isLineMode);}
    function updatePenUI(){
      btnPen.classList.toggle('active',currentTool==='pen');btnHighlighter.classList.toggle('active',currentTool==='highlighter');btnEraser.classList.toggle('active',currentTool==='eraser');
      for(const b of document.querySelectorAll('.brush-choice'))b.classList.toggle('active',b.dataset.brush===selectedBrush);
      for(const b of document.querySelectorAll('[data-color],.swatch'))b.classList.toggle('active',b.dataset.color===currentColor);
      $('pen-size').max=selectedBrush==='highlighter'?80:30;$('pen-size').value=toolSizes[selectedBrush==='highlighter'?'highlighter':'pen'];$('pen-size-value').textContent=$('pen-size').value;
      $('pen-opacity').value=Math.round(getToolOpacity()*100);$('pen-opacity-value').textContent=`${$('pen-opacity').value}%`;
      btnPen.style.color=currentTool==='pen'?currentColor:'';btnHighlighter.style.color=currentTool==='highlighter'?currentColor:'';
      updateLineModeUI();updatePenShortcutUI();renderFavorites();drawPenPreview();
    }
    function applyPreset(p,index=-1){finishActiveInput();selectedBrush=p.brush;currentTool=p.brush==='highlighter'?'highlighter':'pen';currentColor=p.color;toolSizes[currentTool]=p.size;toolOpacities[currentTool]=p.opacity;selectedFavorite=index;isLineMode=false;persistPens();updatePenUI();}
    function setBrush(brush){brushMemory[selectedBrush]=currentPreset();applyPreset({...brushMemory[brush]});}
    function drawPenPreview(){const canvas=$('pen-preview'),ctx=canvas.getContext('2d');ctx.clearRect(0,0,276,50);ctx.strokeStyle=currentColor;ctx.globalAlpha=getToolOpacity();ctx.lineWidth=Math.max(1,Math.min(18,toolSizes[selectedBrush==='highlighter'?'highlighter':'pen']));ctx.lineCap=selectedBrush==='highlighter'?'butt':'round';ctx.beginPath();ctx.moveTo(20,32);ctx.bezierCurveTo(75,0,130,53,255,20);ctx.stroke();ctx.globalAlpha=1;}
    const penSvg=btnPen.innerHTML,markerSvg=btnHighlighter.innerHTML;
    function renderFavorites(){
      const wheel=$('wheel-presets'),list=$('favorite-list');wheel.replaceChildren();list.replaceChildren();
      favorites.forEach((preset,index)=>{const angle=(index/Math.max(1,favorites.length-1))*Math.PI*1.5-Math.PI*1.25,x=109+Math.cos(angle)*93,y=109+Math.sin(angle)*93;
        const b=document.createElement('button');b.type='button';b.className='wheel-favorite';b.style.left=`${x}px`;b.style.top=`${y}px`;b.style.setProperty('--ink',preset.color);b.title=`${brushNames[preset.brush]} · ${preset.size}`;b.setAttribute('aria-label',`お気に入り ${index+1} ${brushNames[preset.brush]} ${preset.color}`);b.innerHTML=preset.brush==='highlighter'?markerSvg:penSvg;b.classList.toggle('active',index===selectedFavorite);b.addEventListener('click',()=>{applyPreset(preset,index);closeOverlays();});wheel.appendChild(b);
        const row=document.createElement('div');row.className='favorite-row';const apply=document.createElement('button');apply.className='favorite-apply';const dot=document.createElement('span');dot.style.cssText=`display:block;width:18px;height:18px;border-radius:50%;background:${preset.color}`;apply.append(dot,document.createTextNode(`${brushNames[preset.brush]} · ${preset.size} · ${Math.round(preset.opacity*100)}%`));apply.addEventListener('click',()=>applyPreset(preset,index));row.appendChild(apply);
        const remove=document.createElement('button');remove.className='icon-button';remove.textContent='×';remove.setAttribute('aria-label',`お気に入り ${index+1} を削除`);remove.disabled=favorites.length===1;remove.addEventListener('click',()=>{favorites.splice(index,1);selectedFavorite=-1;persistPens();renderFavorites();});row.appendChild(remove);list.appendChild(row);
      });$('wheel-center').style.color=currentColor;
    }
    function openFavorites(x,y){openOverlay('wheel-overlay');renderFavorites();const size=258,wheel=$('favorites-wheel'),r=stage.getBoundingClientRect();wheel.style.left=`${Math.max(12,Math.min(r.right-size-12,(x??(r.left+r.width/2))-size/2))}px`;wheel.style.top=`${Math.max(r.top+8,Math.min(r.bottom-size-8,(y??(r.top+r.height/2))-size/2))}px`;}
    let favoriteGesture=null;
    function resetPenButtonGesture(){favoriteGesture?.reset();}
    function handlePenButtonGesture(e,signal){
      favoriteGesture??=new PenShortcutGesture();
      if(!favoriteGesture.update(signal,performance.now()))return false;
      if(selectedBrush==='highlighter')setBrush('pen');
      isLineMode=false;selectTool('pen');
      openFavorites(e.clientX,e.clientY);return true;
    }
    $('open-favorites').addEventListener('click',()=>openFavorites());$('wheel-settings').addEventListener('click',()=>openOverlay('pen-overlay'));
    btnPen.addEventListener('click',()=>{if(currentTool==='pen')openOverlay('pen-overlay');else{if(selectedBrush==='highlighter')setBrush('pen');selectTool('pen');}});
    btnHighlighter.addEventListener('click',()=>{if(currentTool==='highlighter')openOverlay('pen-overlay');else setBrush('highlighter');});
    btnEraser.addEventListener('click',()=>{if(currentTool==='eraser')openOverlay('eraser-overlay');else toggleQuickEraser();});
    $('open-pen-settings').addEventListener('click',()=>openOverlay(currentTool==='eraser'?'eraser-overlay':'pen-overlay'));
    $('btn-line').addEventListener('click',()=>{finishActiveInput();if(currentTool==='eraser')currentTool=selectedBrush==='highlighter'?'highlighter':'pen';isLineMode=!isLineMode;updatePenUI();});
    for(const b of document.querySelectorAll('.brush-choice'))b.addEventListener('click',()=>setBrush(b.dataset.brush));
    for(const color of ['#202124','#ef5350','#f49b50','#ffcf59','#42b68e','#3478dc','#8c69c7','#a7aab5']){const b=document.createElement('button');b.type='button';b.className='swatch';b.dataset.color=color;b.style.background=color;b.setAttribute('aria-label',color);$('pen-colors').appendChild(b);}
    const custom=document.createElement('input');custom.type='color';custom.id='custom-color';custom.setAttribute('aria-label','その他の色');custom.addEventListener('input',()=>{currentColor=custom.value;selectedFavorite=-1;persistPens();updatePenUI();});$('pen-colors').appendChild(custom);
    for(const b of document.querySelectorAll('[data-color]'))b.addEventListener('click',()=>{finishActiveInput();currentColor=b.dataset.color;selectedFavorite=-1;if(currentTool==='eraser')currentTool=selectedBrush==='highlighter'?'highlighter':'pen';persistPens();updatePenUI();});
    $('pen-size').addEventListener('input',e=>{toolSizes[selectedBrush==='highlighter'?'highlighter':'pen']=Number(e.target.value);selectedFavorite=-1;persistPens();updatePenUI();});
    $('pen-opacity').addEventListener('input',e=>{toolOpacities[selectedBrush==='highlighter'?'highlighter':'pen']=Number(e.target.value)/100;selectedFavorite=-1;persistPens();updatePenUI();});
    $('save-favorite').addEventListener('click',()=>{if(favorites.length>=6){showToast('お気に入りは6本までです。使わないペンを削除してください');return;}favorites.push(currentPreset());selectedFavorite=favorites.length-1;persistPens();renderFavorites();showToast('お気に入りに追加しました');});
    for(const b of document.querySelectorAll('[data-erase]'))b.addEventListener('click',()=>{eraserMode=b.dataset.erase;for(const option of document.querySelectorAll('[data-erase]'))option.classList.toggle('active',option.dataset.erase===eraserMode);try{localStorage.setItem('beamerplus_eraser_mode',eraserMode);}catch(_){}});
    try{const saved=localStorage.getItem('beamerplus_eraser_mode');if(['stroke','partial'].includes(saved))eraserMode=saved;}catch(_){}
    for(const option of document.querySelectorAll('[data-erase]'))option.classList.toggle('active',option.dataset.erase===eraserMode);
    $('eraser-size').addEventListener('input',e=>toolSizes.eraser=Number(e.target.value));
    for(const id of ['header-undo','rail-undo'])$(id).addEventListener('click',()=>{finishActiveInput();sendWS({type:'undo'});});
    for(const id of ['header-redo','rail-redo'])$(id).addEventListener('click',()=>{finishActiveInput();sendWS({type:'redo'});});
    function setHistory(msg){if(msg.canUndo!==undefined)for(const id of ['header-undo','rail-undo'])$(id).disabled=!msg.canUndo;if(msg.canRedo!==undefined)for(const id of ['header-redo','rail-redo'])$(id).disabled=!msg.canRedo;}
    function renderNotes(){const list=$('notebook-list');list.replaceChildren();for(const note of notes){const b=document.createElement('button');b.className='note-row';b.classList.toggle('active',note.id===currentDocumentId);b.textContent=note.title;const small=document.createElement('small');small.textContent=note.id===currentDocumentId?'いま開いているノート':'ノートを開く';b.appendChild(small);b.addEventListener('click',()=>{finishActiveInput();sendWS({type:'note_select',id:note.id});closeOverlays();});list.appendChild(b);}}
    $('open-library').addEventListener('click',()=>{renderNotes();openOverlay('library-overlay');});$('new-note').addEventListener('click',()=>{finishActiveInput();sendWS({type:'note_new'});closeOverlays();});
    $('open-options').addEventListener('click',()=>openOverlay('options-overlay'));
    let titleTimer;$('note-title').addEventListener('input',()=>{clearTimeout(titleTimer);const id=currentDocumentId,title=$('note-title').value;titleTimer=setTimeout(()=>sendWS({type:'note_title',id,title}),450);});
    $('paper-style').addEventListener('change',()=>sendWS({type:'note_paper',paper:$('paper-style').value}));
    $('clear-note').addEventListener('click',()=>{finishActiveInput();const sent=sendWS({type:'clear'});closeOverlays();if(sent)showToast('筆跡を消しました。「元に戻す」で復元できます');});
    function paintNotebookPaper(ctx,w,h){ctx.fillStyle='#fff';ctx.fillRect(0,0,w,h);if(paper==='plain')return;ctx.strokeStyle='#e5e9f0';ctx.lineWidth=1;const gap=h/24;ctx.beginPath();for(let y=gap;y<h;y+=gap){ctx.moveTo(0,y);ctx.lineTo(w,y);}if(paper==='grid')for(let x=gap;x<w;x+=gap){ctx.moveTo(x,0);ctx.lineTo(x,h);}ctx.stroke();}
    $('export-note').addEventListener('click',()=>{finishActiveInput();const canvas=document.createElement('canvas');canvas.width=1600;canvas.height=Math.round(1600/paperAspect);const ctx=canvas.getContext('2d');paintNotebookPaper(ctx,1600,canvas.height);ctx.drawImage(committedCanvas,0,0,1600,canvas.height);const a=document.createElement('a');a.download=($('note-title').value||'note')+'.png';a.href=canvas.toDataURL('image/png');a.click();closeOverlays();});
    const urlParams=new URLSearchParams(location.search),autoAuth=__AUTO_AUTH__;
    let currentPasscode=urlParams.get('code')||'',ws=null,reconnectTimer;
    try{currentPasscode=currentPasscode||sessionStorage.getItem('beamerplus_passcode')||'';}catch(_){}
    function sendWS(message){if(notebookReady&&ws&&ws.readyState===WebSocket.OPEN){ws.send(JSON.stringify(message));if(['stroke_start','stroke_move','erase','clear','undo','redo'].includes(message.type))$('save-status').textContent='保存中…';return true;}if(!['stroke_end','erase_end'].includes(message.type))showToast('PCとの接続を待ってください');return false;}
    function connectWS(){if(!autoAuth&&!currentPasscode){$('auth-overlay').style.display='flex';return;}clearTimeout(reconnectTimer);ws=new WebSocket(`ws://${location.hostname}:__WS_PORT__`);ws.onopen=()=>ws.send(JSON.stringify({type:'auth',passcode:currentPasscode,clientBuild:notebookClientBuild}));ws.onclose=()=>{finishActiveInput();notebookReady=false;$('note-title').disabled=true;$('status-dot').classList.remove('online');$('save-status').textContent='再接続中';updateAssistantConnection(false);reconnectTimer=setTimeout(connectWS,2000);};ws.onerror=()=>ws.close();ws.onmessage=event=>{try{const msg=JSON.parse(event.data);if(msg.type==='auth_result'){if(msg.success){checkNotebookClientVersion(msg.clientBuild);notebookReady=true;$('note-title').disabled=false;$('auth-overlay').style.display='none';$('status-dot').classList.add('online');$('save-status').textContent='保存済み';try{sessionStorage.setItem('beamerplus_passcode',currentPasscode);}catch(_){}updateAssistantConnection(true);}else{$('auth-overlay').style.display='flex';$('auth-error').textContent='パスコードを確認してください';}return;}handleServerMessage(msg);}catch(error){console.error(error);}};}
    $('auth-form').addEventListener('submit',e=>{e.preventDefault();currentPasscode=$('passcode-input').value.trim();if(ws&&ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify({type:'auth',passcode:currentPasscode,clientBuild:notebookClientBuild}));else connectWS();});
    function handleServerMessage(msg){
      if(msg.type.startsWith('ai_')){handleAssistantMessage(msg);return;}
      if(msg.type==='state_sync'){
        finishActiveInput();const oldAspect=paperAspect;paperAspect=Number.isFinite(msg.paperAspect)&&msg.paperAspect>=.4&&msg.paperAspect<=2.5?msg.paperAspect:4/3;currentDocumentId=msg.documentId||'';sketchbookStrokes=msg.sketchbookStrokes||msg.strokes||[];noteTexts=msg.noteTexts||[];notes=msg.notes||[];
        if(document.activeElement!==$('note-title'))$('note-title').value=msg.title||'新しいノート';paper=msg.paper||'plain';slideWrapper.classList.toggle('ruled',paper==='ruled');slideWrapper.classList.toggle('grid',paper==='grid');$('paper-style').value=paper;$('note-footer').textContent={plain:'白紙のノート',ruled:'横罫線のノート',grid:'方眼のノート'}[paper];if(oldAspect!==paperAspect)adjustLayout();else renderAllStrokes(sketchbookStrokes);renderNotes();setHistory(msg);
      }else if(msg.type==='note_texts_updated'){if(msg.documentId===currentDocumentId){noteTexts=msg.texts||[];renderAllStrokes(sketchbookStrokes);}}
      else if(['strokes_updated','stroke_undone'].includes(msg.type)){sketchbookStrokes=msg.strokes||[];renderAllStrokes(sketchbookStrokes);}
      else if(msg.type==='strokes_cleared'){sketchbookStrokes=[];renderAllStrokes([]);}
      else if(msg.type==='note_history')setHistory(msg);
      else if(msg.type==='note_saved'){$('save-status').textContent='保存済み';}
      else if(msg.type==='note_error'){$('save-status').textContent='保存を確認';showToast(msg.message);}
      else if(msg.type==='remote_stroke_start'){remoteStroke={color:msg.color,width_ratio:msg.widthRatio,opacity:msg.opacity,brush:msg.brush||'pen',points:[msg.p0]};}
      else if(msg.type==='remote_stroke_move'&&remoteStroke){remoteStroke.points.push([msg.normX,msg.normY,msg.pressure||1]);activeCtx.clearRect(0,0,activeCanvas.width,activeCanvas.height);drawStroke(activeCtx,remoteStroke);}
      else if(msg.type==='remote_stroke_end'){remoteStroke=null;}
    }
    __INPUT_SCRIPT__
    __ASSISTANT_SCRIPT__
    __NAVIGATION_SCRIPT__
    __SELECTION_SCRIPT__
    __INSTALL_TEXT_SCRIPT__
    __FAVORITES_SCRIPT__
    __ERASER_CURSOR_SCRIPT__
    __LIBRARY_SCRIPT__
    __MENUS_SCRIPT__
    __VERSION_SCRIPT__
    updatePenUI();setHistory({canUndo:false,canRedo:false});adjustLayout();connectWS();
    window.addEventListener('resize',adjustLayout);window.visualViewport?.addEventListener('resize',adjustLayout);
"""

NOTEBOOK_HTML = (f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1"><title>BeamerPlus Notes</title><style>{ASSISTANT_STYLE}{STYLE}{NAVIGATION_STYLE}{SELECTION_STYLE}{FAVORITES_STYLE}{LIBRARY_STYLE}{MENUS_STYLE}</style></head><body>{MARKUP}{ASSISTANT_MARKUP}<script>'
                 + SCRIPT.replace('__INPUT_SCRIPT__', INPUT_SCRIPT).replace('__ASSISTANT_SCRIPT__', ASSISTANT_SCRIPT).replace('__NOTE_TEXT_SCRIPT__', NOTE_TEXT_SCRIPT)
                 .replace('__NAVIGATION_SCRIPT__', NAVIGATION_SCRIPT).replace('__SELECTION_SCRIPT__', SELECTION_SCRIPT)
                 .replace('__INSTALL_TEXT_SCRIPT__', INSTALL_TEXT_SCRIPT)
                 .replace('__FAVORITES_SCRIPT__', FAVORITES_SCRIPT).replace('__ERASER_CURSOR_SCRIPT__', ERASER_CURSOR_SCRIPT)
                 .replace('__LIBRARY_SCRIPT__', LIBRARY_SCRIPT).replace('__MENUS_SCRIPT__', MENUS_SCRIPT)
                 .replace('__VERSION_SCRIPT__', VERSION_SCRIPT) + '</script></body></html>')
