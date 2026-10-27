"""Visible tablet eraser radius, including temporary S Pen button erasing."""


ERASER_CURSOR_SCRIPT = r"""
    const notebookEraserCursor = (() => {
      const ring = document.createElement('div');
      ring.id = 'eraser-cursor';
      ring.hidden = true;
      ring.setAttribute('aria-hidden', 'true');
      ring.style.cssText = 'position:fixed;pointer-events:none;z-index:75;box-sizing:border-box;'
        + 'border:1px solid rgba(69,81,103,.85);border-radius:50%;'
        + 'box-shadow:0 0 0 1px rgba(255,255,255,.85);background:rgba(106,133,171,.07);'
        + 'transform:translate(-50%,-50%);';
      document.body.appendChild(ring);
      let last = null;

      function hide(forget = false) {
        ring.hidden = true;
        if (forget) last = null;
      }

      function overlayOpen() {
        return !!document.querySelector('.overlay:not([hidden])')
          || (typeof canEditNotebook === 'function' && !canEditNotebook());
      }

      function refresh() {
        if (!last || overlayOpen()) { hide(); return; }
        const signal = last.signal;
        const erasing = currentTool === 'eraser' || (last.pointerType === 'pen'
          && (signal.eraser || (penButtonMode === 'hold' && signal.barrel)));
        const touchErasing = last.pointerType !== 'touch'
          || (typeof inkTool !== 'undefined' && inkTool === 'eraser'
            && typeof inkPointerId !== 'undefined' && inkPointerId === last.pointerId);
        if (!erasing || !touchErasing) { hide(); return; }
        const paperRect = slideWrapper.getBoundingClientRect();
        const stageRect = stage.getBoundingClientRect();
        const {x, y} = last;
        if (!(paperRect.width > 0 && paperRect.height > 0)
            || x < Math.max(paperRect.left, stageRect.left)
            || x > Math.min(paperRect.right, stageRect.right)
            || y < Math.max(paperRect.top, stageRect.top)
            || y > Math.min(paperRect.bottom, stageRect.bottom)) { hide(); return; }
        // Share the exact radius sent by eraseAt; paper zoom never enlarges
        // this screen-space circle, including on portrait paper.
        const diameter = getNotebookEraserMetrics().screenRadius * 2;
        ring.style.width = `${diameter}px`;
        ring.style.height = `${diameter}px`;
        ring.style.left = `${x}px`;
        ring.style.top = `${y}px`;
        ring.hidden = false;
      }

      function observe(e) {
        // A palm must not replace the hovering pen's cursor position.
        if (e.pointerType === 'touch' && typeof penInRange !== 'undefined' && penInRange) return;
        if (!Number.isFinite(e.clientX) || !Number.isFinite(e.clientY)) return;
        // Cache the existing classifier's result once for the dispatch event.
        // Refreshes after changing zoom or size must never reclassify old input.
        const signal = e.pointerType === 'pen' ? {...penProtocol.read(e)}
          : {barrel:false, eraser:false, contact:false};
        last = {x:e.clientX, y:e.clientY, pointerId:e.pointerId,
          pointerType:e.pointerType, signal};
        refresh();
      }

      function leave(e) {
        if (!last || e.pointerId === last.pointerId) hide(true);
      }

      for (const name of ['pointerenter','pointerdown','pointermove']) {
        activeCanvas.addEventListener(name, observe);
      }
      activeCanvas.addEventListener('pointerup', e => {
        if (e.pointerType === 'touch') leave(e);
        else observe(e);
      });
      for (const name of ['pointerleave','pointercancel','lostpointercapture']) {
        activeCanvas.addEventListener(name, leave);
      }
      document.addEventListener('pointerdown', e => {
        if (e.target !== activeCanvas) hide(true);
      }, {capture:true});
      window.addEventListener('blur', () => hide(true));
      window.addEventListener('resize', refresh);
      stage.addEventListener('scroll', refresh, {passive:true});
      window.visualViewport?.addEventListener('resize', refresh);
      window.visualViewport?.addEventListener('scroll', refresh);

      // Tool switching and barrel-button changes already update these controls.
      // Keep the circle in sync without adding an animation loop or poller.
      if (typeof updatePenUI === 'function') {
        const previous = updatePenUI;
        updatePenUI = function(...args) { const result = previous.apply(this, args); refresh(); return result; };
      }
      if (typeof updatePenShortcutUI === 'function') {
        const previous = updatePenShortcutUI;
        updatePenShortcutUI = function(...args) { const result = previous.apply(this, args); refresh(); return result; };
      }
      for (const id of ['eraser-size', 'pen-button-mode']) {
        document.getElementById(id)?.addEventListener('input', refresh);
        document.getElementById(id)?.addEventListener('change', refresh);
      }
      if (typeof openOverlay === 'function') {
        const previous = openOverlay;
        openOverlay = function(...args) { hide(true); return previous.apply(this, args); };
      }
      if (typeof openFavorites === 'function') {
        const previous = openFavorites;
        openFavorites = function(...args) { hide(true); return previous.apply(this, args); };
      }
      if (typeof MutationObserver !== 'undefined') {
        const observer = new MutationObserver(() => {
          if (overlayOpen()) hide(true);
          else refresh();
        });
        observer.observe(slideWrapper, {attributes:true, attributeFilter:['style']});
        for (const overlay of document.querySelectorAll('.overlay')) {
          observer.observe(overlay, {attributes:true, attributeFilter:['hidden','style']});
        }
      }
      return {refresh, hide};
    })();
    function refreshEraserCursor() { notebookEraserCursor.refresh(); }
    function hideEraserCursor() { notebookEraserCursor.hide(true); }
"""
