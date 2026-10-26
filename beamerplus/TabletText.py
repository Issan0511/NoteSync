"""Tablet annotation rendering with cached, image-only server math SVGs."""


NOTE_TEXT_SCRIPT = r"""
    const noteTextImageCache=new Map();
    const noteTextImageCacheLimit=128;
    let requestLatestNoteTextPaint=()=>{};
    function noteTextRenderedSvg(item){
      return typeof item?.renderedSvg==='string'&&item.renderedSvg.length>0
        &&Number.isFinite(item.renderedWidth)&&item.renderedWidth>0
        &&Number.isFinite(item.renderedHeight)&&item.renderedHeight>0?item.renderedSvg:null;
    }
    function noteTextSvgDataUrl(svg){
      const bytes=new TextEncoder().encode(svg);let binary='';
      for(let offset=0;offset<bytes.length;offset+=8192)binary+=String.fromCharCode(...bytes.subarray(offset,offset+8192));
      return 'data:image/svg+xml;base64,'+btoa(binary);
    }
    function trimNoteTextImageCache(pinned){
      for(const svg of noteTextImageCache.keys()){
        if(noteTextImageCache.size<=noteTextImageCacheLimit)break;
        if(!pinned.has(svg))noteTextImageCache.delete(svg);
      }
    }
    function noteTextImage(svg,pinned){
      let entry=noteTextImageCache.get(svg);
      if(entry){noteTextImageCache.delete(svg);noteTextImageCache.set(svg,entry);return entry;}
      const image=new Image();entry={image,state:'loading'};noteTextImageCache.set(svg,entry);
      trimNoteTextImageCache(pinned);
      image.onload=()=>{entry.state='ready';requestLatestNoteTextPaint(svg);};
      image.onerror=()=>{entry.state='failed';requestLatestNoteTextPaint(svg);};
      image.src=noteTextSvgDataUrl(svg);return entry;
    }
    function drawPlainNoteText(ctx,item,width,height,pixels){
      ctx.font=`${pixels}px sans-serif`;ctx.fillStyle=item.color;
      item.text.split('\n').forEach((line,index)=>ctx.fillText(line,item.norm_x*width,item.norm_y*height+pixels+index*pixels*1.45));
    }
    function drawNoteTexts(ctx,texts,width,height){
      // Keep all images used by this scene until its next repaint; otherwise a
      // large note can repeatedly evict images that are still decoding.
      const pinned=new Set(texts.map(noteTextRenderedSvg).filter(Boolean));trimNoteTextImageCache(pinned);
      ctx.save();
      try{
        ctx.textBaseline='alphabetic';
        for(const item of texts){
          const pixels=Math.max(1,Math.round(Math.min(width,height)*item.size*.0015)),svg=noteTextRenderedSvg(item);
          if(!svg){drawPlainNoteText(ctx,item,width,height,pixels);continue;}
          const entry=noteTextImage(svg,pinned);
          if(entry.state==='ready')ctx.drawImage(entry.image,item.norm_x*width,item.norm_y*height,item.renderedWidth*pixels,item.renderedHeight*pixels);
          else if(entry.state==='failed')drawPlainNoteText(ctx,item,width,height,pixels);
        }
      }finally{ctx.restore();}
    }
"""


INSTALL_TEXT_SCRIPT = r"""
    let noteTextImageFrame=null;
    const noteTextReadyImages=new Set();
    requestLatestNoteTextPaint=function(svg){
      if(!Array.isArray(noteTexts)||!noteTexts.some(item=>noteTextRenderedSvg(item)===svg))return;
      noteTextReadyImages.add(svg);
      if(noteTextImageFrame!==null)return;
      noteTextImageFrame=requestAnimationFrame(()=>{
        noteTextImageFrame=null;const ready=new Set(noteTextReadyImages);noteTextReadyImages.clear();
        // Images may finish after switching notes, deleting text, zooming, or
        // moving selected ink. Repaint only the latest background scene.
        if(!Array.isArray(noteTexts)||!noteTexts.some(item=>ready.has(noteTextRenderedSvg(item))))return;
        const strokes=Array.isArray(sketchbookStrokes)?sketchbookStrokes:[];
        const split=typeof selectionBackgroundSplit!=='undefined'&&selectionBackgroundSplit;
        const indices=split&&typeof selectedInk!=='undefined'?new Set(selectedInk):null;
        const background=indices?strokes.filter((_,index)=>!indices.has(index)):strokes;
        if(typeof renderBaseInk==='function')renderBaseInk(background);
        else renderAllStrokes(background);
      });
    };
"""
