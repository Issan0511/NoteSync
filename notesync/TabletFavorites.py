"""Favorite-pen editing and the pen wheel's current-color picker."""


FAVORITES_MODEL_SCRIPT = r"""
    function validFavoritePen(preset) {
      return preset && ['pen','fountain','pencil','highlighter'].includes(preset.brush)
        && /^#[0-9a-f]{6}$/i.test(preset.color) && Number.isFinite(preset.size)
        && preset.size>=1 && preset.size<=80 && Number.isFinite(preset.opacity)
        && preset.opacity>=.1 && preset.opacity<=1;
    }
    function appendFavoritePen(presets,preset) {
      if(presets.length>=6 || !validFavoritePen(preset))return null;
      return [...presets.map(p=>({...p})),{...preset}];
    }
    function removeFavoritePen(presets,index) {
      if(presets.length<=1 || !Number.isInteger(index) || index<0 || index>=presets.length)return null;
      return presets.filter((_,i)=>i!==index).map(p=>({...p}));
    }
    class FavoritePenDraft {
      constructor(){this.cancel();}
      begin(index,preset) {
        if(!Number.isInteger(index) || index<0 || !validFavoritePen(preset))return false;
        this.index=index;this.preset={...preset};return true;
      }
      update(patch) {
        if(!this.preset)return false;
        const next={...this.preset,...patch};if(!validFavoritePen(next))return false;
        this.preset=next;return true;
      }
      commit(presets) {
        if(!this.preset || this.index>=presets.length)return null;
        const next=presets.map((p,i)=>({... (i===this.index?this.preset:p)}));
        this.cancel();return next;
      }
      cancel(){this.index=-1;this.preset=null;}
    }
"""


FAVORITES_STYLE = r"""
#favorites-wheel .wheel-command{width:134px;height:32px;left:61px;bottom:8px;border-radius:18px;font-size:10px;display:flex;justify-content:center;align-items:center;gap:5px;box-shadow:0 2px 8px #33333308}
#favorites-wheel .wheel-command svg{width:15px;height:15px}
#wheel-current-color{position:absolute;left:205px;top:109px;width:40px;height:40px;border:5px solid white;border-radius:50%;box-shadow:0 0 0 1px #dfe1e8,0 2px 8px #3331;padding:0;cursor:pointer}
#wheel-current-color:focus-visible{outline:2px solid #617de7;outline-offset:4px}
.favorite-row .favorite-edit{border:1px solid #e0e4ed;color:#536482;background:#f5f7fb;border-radius:8px;font-size:11px;padding:8px 10px;min-height:36px}
.favorite-row .favorite-apply{min-height:36px}.favorite-row .favorite-apply span{flex-shrink:0}
.favorite-row .favorite-description{font-size:11px;line-height:1.5;flex:1}
.favorite-row .favorite-remove{width:32px!important;height:36px!important;font-size:20px}
#favorites-manager,#favorite-editor,#quick-color-picker{top:86px;right:90px;width:340px}
.favorite-help{font-size:12px;color:#8a8f9c;line-height:1.75;margin:0 0 14px}
#favorites-manager-list{margin:4px 0 18px}
#favorites-manager-list:empty::after{content:'お気に入りを追加してください';font-size:12px;color:#8a8f9c}
.favorite-editor-buttons{display:flex;gap:9px;margin-top:22px}.favorite-editor-buttons button{flex:1}.favorite-primary{background:#465979;color:white;border-color:#465979}
#favorite-editor .brush-choice{font-size:10px}.favorite-color-input{width:34px;height:34px;padding:0;border:0;border-radius:50%;background:none;cursor:pointer}
#favorite-editor-preview{position:relative;inset:auto;display:block;height:56px;width:100%;background:#fafafa;border-radius:11px;margin-top:20px;pointer-events:none}
#quick-color-picker .swatches{gap:17px;padding:6px 2px}.quick-color-custom{display:flex;gap:12px;align-items:center;margin-top:22px;font-size:12px;color:#6f7788}
.favorite-empty-space{height:14px}
@media(max-width:900px){#favorites-manager,#favorite-editor,#quick-color-picker{right:12px;top:70px}}
"""


FAVORITES_SCRIPT = FAVORITES_MODEL_SCRIPT + r"""
    const favoriteDraft=new FavoritePenDraft();
    const favoriteExtraOverlays=['favorite-manager-overlay','favorite-editor-overlay','quick-color-overlay'];
    const favoriteColors=['#202124','#ef5350','#f49b50','#ffcf59','#42b68e','#3478dc','#8c69c7','#a7aab5'];
    const favoriteCloseIcon='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="m6 6 12 12M18 6 6 18"/></svg>';
    const favoriteEditIcon='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="m5 19 3-1 11-11-3-3L5 15zM13 7l4 4M4 21h16"/></svg>';
    const favoriteMarkup=document.createElement('div');
    favoriteMarkup.innerHTML=`
      <div id="favorite-manager-overlay" class="overlay" hidden><section id="favorites-manager" class="sheet" role="dialog" aria-label="お気に入りを編集">
        <div class="sheet-head"><h2>お気に入り</h2><button type="button" class="icon-button" id="close-favorites-manager" aria-label="お気に入りを閉じる">${favoriteCloseIcon}</button></div>
        <p class="favorite-help">ペンをタップして使う。「編集」で色・太さ・濃さを変更できます。</p><div id="favorites-manager-list"></div>
        <button type="button" id="favorite-add-current" class="wide-button">＋ 今のペンを追加</button>
      </section></div>
      <div id="favorite-editor-overlay" class="overlay" hidden><section id="favorite-editor" class="sheet" role="dialog" aria-label="お気に入りの設定">
        <div class="sheet-head"><h2 id="favorite-editor-title">お気に入りを編集</h2><button type="button" class="icon-button" id="close-favorite-editor" aria-label="編集をキャンセル">${favoriteCloseIcon}</button></div>
        <div id="favorite-editor-brushes" class="brush-grid"></div>
        <label for="favorite-editor-size">太さ</label><div class="setting-row"><input type="range" min="1" max="80" id="favorite-editor-size"><output id="favorite-editor-size-value"></output></div>
        <label for="favorite-editor-opacity">濃さ</label><div class="setting-row"><input type="range" min="10" max="100" id="favorite-editor-opacity"><output id="favorite-editor-opacity-value"></output></div>
        <span class="section-label">色</span><div class="swatches" id="favorite-editor-colors"></div>
        <canvas id="favorite-editor-preview" width="292" height="56" aria-label="お気に入りの線のプレビュー"></canvas>
        <div class="favorite-editor-buttons"><button type="button" id="favorite-editor-cancel" class="wide-button">キャンセル</button><button type="button" id="favorite-editor-save" class="wide-button favorite-primary">変更を保存</button></div>
      </section></div>
      <div id="quick-color-overlay" class="overlay" hidden><section id="quick-color-picker" class="sheet" role="dialog" aria-label="今のペンの色を変更">
        <div class="sheet-head"><h2>ペンの色</h2><button type="button" class="icon-button" id="close-quick-color" aria-label="色の選択を閉じる">${favoriteCloseIcon}</button></div>
        <div id="quick-color-swatches" class="swatches"></div><label class="quick-color-custom" for="quick-custom-color"><input type="color" id="quick-custom-color" class="favorite-color-input">その他の色を選ぶ</label>
      </section></div>`;
    document.body.appendChild(favoriteMarkup);
    const favoriteBaseCloseOverlays=closeOverlays;
    closeOverlays=function(){favoriteBaseCloseOverlays();for(const id of favoriteExtraOverlays)$(id).hidden=true;favoriteDraft.cancel();};
    for(const id of favoriteExtraOverlays)$(id).addEventListener('pointerdown',e=>{if(e.target===$(id)){e.preventDefault();closeOverlays();}});
    $('close-favorites-manager').addEventListener('click',closeOverlays);
    $('close-quick-color').addEventListener('click',closeOverlays);
    function openFavoriteManager(){openOverlay('favorite-manager-overlay');renderFavorites();}
    function openFavoriteEditor(index){
      if(!favorites[index])return;openOverlay('favorite-editor-overlay');favoriteDraft.begin(index,favorites[index]);
      $('favorite-editor-title').textContent=`お気に入り ${index+1} を編集`;renderFavoriteDraft();
    }
    function cancelFavoriteEditor(){favoriteDraft.cancel();openFavoriteManager();}
    $('close-favorite-editor').addEventListener('click',cancelFavoriteEditor);
    $('favorite-editor-cancel').addEventListener('click',cancelFavoriteEditor);
    $('favorite-editor-save').addEventListener('click',()=>{
      const index=favoriteDraft.index,next=favoriteDraft.commit(favorites);if(!next)return;
      favorites=next;if(selectedFavorite===index)selectedFavorite=-1;persistPens();updatePenUI();openFavoriteManager();showToast('お気に入りを更新しました');
    });
    function addCurrentFavorite(){
      const next=appendFavoritePen(favorites,currentPreset());if(!next){showToast('お気に入りは6本までです。使わないペンを削除してください');return;}
      favorites=next;selectedFavorite=favorites.length-1;persistPens();updatePenUI();showToast('お気に入りに追加しました');
    }
    function deleteFavorite(index){
      const next=removeFavoritePen(favorites,index);if(!next)return;
      favorites=next;if(selectedFavorite===index)selectedFavorite=-1;else if(selectedFavorite>index)selectedFavorite--;persistPens();updatePenUI();showToast('お気に入りを削除しました');
    }
    function replaceFavoriteButton(id,handler){const previous=$(id),replacement=previous.cloneNode(true);previous.replaceWith(replacement);replacement.addEventListener('click',handler);return replacement;}
    const favoriteWheelEdit=replaceFavoriteButton('wheel-settings',openFavoriteManager);
    favoriteWheelEdit.innerHTML=favoriteEditIcon+'<span>お気に入りを編集</span>';favoriteWheelEdit.title='お気に入りを編集';
    const favoriteAddButton=replaceFavoriteButton('save-favorite',addCurrentFavorite);favoriteAddButton.textContent='＋ 今のペンをお気に入りに追加';
    $('favorite-add-current').addEventListener('click',addCurrentFavorite);
    const favoriteCurrentColor=document.createElement('button');favoriteCurrentColor.type='button';favoriteCurrentColor.id='wheel-current-color';favoriteCurrentColor.setAttribute('aria-label','今のペンの色を変更');favoriteCurrentColor.title='今のペンの色を変更';$('favorites-wheel').appendChild(favoriteCurrentColor);
    favoriteCurrentColor.addEventListener('click',()=>{openOverlay('quick-color-overlay');$('quick-custom-color').value=currentColor;renderQuickColors();});
    function changeCurrentPenColor(color){
      if(!/^#[0-9a-f]{6}$/i.test(color))return;finishActiveInput();currentColor=color;selectedFavorite=-1;
      if(currentTool==='eraser'||currentTool==='lasso')currentTool=selectedBrush==='highlighter'?'highlighter':'pen';persistPens();updatePenUI();renderQuickColors();
    }
    function renderQuickColors(){for(const b of $('quick-color-swatches').querySelectorAll('button'))b.classList.toggle('active',b.dataset.favoriteColor===currentColor);$('quick-custom-color').value=currentColor;}
    for(const color of favoriteColors){
      const b=document.createElement('button');b.type='button';b.className='swatch';b.dataset.favoriteColor=color;b.style.background=color;b.setAttribute('aria-label',`色を ${color} に変更`);b.addEventListener('click',()=>{changeCurrentPenColor(color);closeOverlays();});$('quick-color-swatches').appendChild(b);
    }
    $('quick-custom-color').addEventListener('input',e=>changeCurrentPenColor(e.target.value));
    $('quick-custom-color').addEventListener('change',closeOverlays);
    for(const brush of Object.keys(brushNames)){
      const b=document.createElement('button');b.type='button';b.className='brush-choice';b.dataset.favoriteBrush=brush;b.innerHTML=(brush==='highlighter'?markerSvg:penSvg)+brushNames[brush];b.addEventListener('click',()=>{favoriteDraft.update({brush});renderFavoriteDraft();});$('favorite-editor-brushes').appendChild(b);
    }
    for(const color of favoriteColors){
      const b=document.createElement('button');b.type='button';b.className='swatch';b.dataset.favoriteColor=color;b.style.background=color;b.setAttribute('aria-label',`お気に入りの色 ${color}`);b.addEventListener('click',()=>{favoriteDraft.update({color});renderFavoriteDraft();});$('favorite-editor-colors').appendChild(b);
    }
    const favoriteCustomColor=document.createElement('input');favoriteCustomColor.id='favorite-editor-custom-color';favoriteCustomColor.type='color';favoriteCustomColor.className='favorite-color-input';favoriteCustomColor.setAttribute('aria-label','お気に入りのその他の色');favoriteCustomColor.addEventListener('input',e=>{favoriteDraft.update({color:e.target.value});renderFavoriteDraft();});$('favorite-editor-colors').appendChild(favoriteCustomColor);
    $('favorite-editor-size').addEventListener('input',e=>{favoriteDraft.update({size:Number(e.target.value)});renderFavoriteDraft();});
    $('favorite-editor-opacity').addEventListener('input',e=>{favoriteDraft.update({opacity:Number(e.target.value)/100});renderFavoriteDraft();});
    function renderFavoriteDraft(){
      const preset=favoriteDraft.preset;if(!preset)return;
      for(const b of $('favorite-editor-brushes').querySelectorAll('button'))b.classList.toggle('active',b.dataset.favoriteBrush===preset.brush);
      for(const b of $('favorite-editor-colors').querySelectorAll('button'))b.classList.toggle('active',b.dataset.favoriteColor===preset.color);
      $('favorite-editor-size').value=preset.size;$('favorite-editor-size-value').textContent=preset.size;
      $('favorite-editor-opacity').value=Math.round(preset.opacity*100);$('favorite-editor-opacity-value').textContent=`${Math.round(preset.opacity*100)}%`;favoriteCustomColor.value=preset.color;
      const ctx=$('favorite-editor-preview').getContext('2d');ctx.clearRect(0,0,292,56);ctx.strokeStyle=preset.color;ctx.globalAlpha=preset.opacity;ctx.lineWidth=Math.max(1,Math.min(20,preset.size));ctx.lineCap=preset.brush==='highlighter'?'butt':'round';ctx.beginPath();ctx.moveTo(18,36);ctx.bezierCurveTo(80,2,145,54,274,20);ctx.stroke();ctx.globalAlpha=1;
    }
    function favoriteListRow(preset,index){
      const row=document.createElement('div');row.className='favorite-row';
      const apply=document.createElement('button');apply.type='button';apply.className='favorite-apply';apply.setAttribute('aria-label',`お気に入り ${index+1} を使う`);
      const dot=document.createElement('span');dot.style.cssText=`display:block;width:18px;height:18px;border-radius:50%;background:${preset.color}`;
      const description=document.createElement('span');description.className='favorite-description';description.textContent=`${brushNames[preset.brush]} · ${preset.size} · ${Math.round(preset.opacity*100)}%`;
      apply.append(dot,description);apply.addEventListener('click',()=>{applyPreset(preset,index);closeOverlays();});row.appendChild(apply);
      const edit=document.createElement('button');edit.type='button';edit.className='favorite-edit';edit.textContent='編集';edit.setAttribute('aria-label',`お気に入り ${index+1} を編集`);edit.addEventListener('click',()=>openFavoriteEditor(index));row.appendChild(edit);
      const remove=document.createElement('button');remove.type='button';remove.className='icon-button favorite-remove';remove.textContent='×';remove.setAttribute('aria-label',`お気に入り ${index+1} を削除`);remove.disabled=favorites.length===1;remove.addEventListener('click',()=>deleteFavorite(index));row.appendChild(remove);return row;
    }
    renderFavorites=function(){
      const wheel=$('wheel-presets'),list=$('favorite-list'),manager=$('favorites-manager-list');wheel.replaceChildren();list.replaceChildren();manager.replaceChildren();
      favorites.forEach((preset,index)=>{
        const angle=(135+index*180/Math.max(1,favorites.length-1))*Math.PI/180,x=109+Math.cos(angle)*93,y=109+Math.sin(angle)*93;
        const b=document.createElement('button');b.type='button';b.className='wheel-favorite';b.style.left=`${x}px`;b.style.top=`${y}px`;b.style.setProperty('--ink',preset.color);b.title=`${brushNames[preset.brush]} · ${preset.size}`;b.setAttribute('aria-label',`お気に入り ${index+1} ${brushNames[preset.brush]} ${preset.color}`);b.innerHTML=preset.brush==='highlighter'?markerSvg:penSvg;b.classList.toggle('active',index===selectedFavorite);b.addEventListener('click',()=>{applyPreset(preset,index);closeOverlays();});wheel.appendChild(b);
        list.appendChild(favoriteListRow(preset,index));manager.appendChild(favoriteListRow(preset,index));
      });
      $('wheel-center').style.color=currentColor;favoriteCurrentColor.style.background=currentColor;favoriteCurrentColor.setAttribute('aria-label',`今のペンの色 ${currentColor} を変更`);
    };
"""
