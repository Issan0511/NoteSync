"""Shared pen/touch drawing for S Pen, Apple Pencil, and desktop pointers."""

from notesync.PenProtocol import PEN_PROTOCOL_SCRIPT

INPUT_SCRIPT = PEN_PROTOCOL_SCRIPT + r"""
    let inkPointerId = null;
    let inkTool = null;
    let inkMeta = null;
    let inkLineMode = false;
    let penInRange = false;
    let penEraserActive = false;
    let penContactArmed = false;
    let quickReturnTool = 'pen';
    let quickReturnLineMode = false;
    let penButtonDown = false;
    const penProtocol = new PenProtocol(typeof navigator === 'undefined' ? '' : navigator.userAgent);
    const androidChrome = typeof navigator !== 'undefined' && /Android/.test(navigator.userAgent)
      && /Chrom(e|ium)\//.test(navigator.userAgent) && !/SamsungBrowser\//.test(navigator.userAgent);
    let penButtonMode = androidChrome ? 'toggle' : 'hold';
    try {
      const savedMode = localStorage.getItem('notesync_pen_button_mode');
      if (savedMode === 'hold' || savedMode === 'toggle') penButtonMode = savedMode;
    } catch (_) {}

    function barrelButtonPressed(e) {
      return penProtocol.read(e).barrel;
    }

    function isPenEraser(e) {
      const pen = penProtocol.read(e);
      return pen.eraser || (penButtonMode === 'hold' && pen.barrel);
    }

    function toggleQuickEraser() {
      if (currentTool === 'eraser') {
        selectTool(quickReturnTool);
        isLineMode = quickReturnLineMode;
        if (typeof updateLineModeUI === 'function') updateLineModeUI();
      } else {
        quickReturnTool = currentTool === 'highlighter' ? 'highlighter' : 'pen';
        quickReturnLineMode = isLineMode;
        selectTool('eraser');
      }
    }

    function observePenButton(e) {
      if (e.pointerType !== 'pen') return;
      const signal = penProtocol.read(e);
      const down = barrelButtonPressed(e);
      const pressed = down && !penButtonDown;
      penButtonDown = down;
      if (typeof handlePenButtonGesture === 'function' && handlePenButtonGesture(e, signal)) return;
      if (penButtonMode === 'toggle' && pressed) {
        toggleQuickEraser();
        if (typeof showToast === 'function') showToast(currentTool === 'eraser'
          ? '🧹 消しゴム：ボタンを離してからなぞってください' : '✏️ ペンに戻りました');
      }
    }

    function penHasContact(e) {
      return penProtocol.read(e).contact;
    }

    function updatePenShortcutUI() {
      if (typeof btnEraser !== 'undefined') btnEraser.classList.toggle('pen-button-active', penEraserActive);
      if (typeof quickEraser === 'undefined') return;
      quickEraser.classList.toggle('pen-button-active', penEraserActive);
      quickEraser.classList.toggle('active', currentTool === 'eraser');
      quickEraser.setAttribute('aria-pressed', String(penEraserActive || currentTool === 'eraser'));
      quickEraser.innerText = penEraserActive ? '🧹 消しゴム中' : currentTool === 'eraser' ? '✏️ ペンに戻る' : '🧹 消しゴム';
    }

    function setPenEraser(active) {
      if (penEraserActive === active) return;
      penEraserActive = active;
      updatePenShortcutUI();
      if (active && currentTool === 'pointer' && typeof updateLaserDot === 'function') {
        updateLaserDot(0, 0, false, false);
        sendWS({type:'pointer_move', normX:0, normY:0, visible:false, isDown:false});
      }
    }

    function finishInkStroke() {
      if (inkTool === 'eraser') sendWS({type:'erase_end'});
      if (isDrawing) {
        isDrawing = false;
        activeCtx.clearRect(0, 0, activeCanvas.width, activeCanvas.height);
        if (currentStrokePoints.length) {
          const stroke = {...inkMeta, points:currentStrokePoints};
          drawStroke(committedCtx, stroke);
          (isSketchbook ? sketchbookStrokes : slideStrokes).push(stroke);
        }
        currentStrokePoints = [];
        sendWS({type:'stroke_end'});
      }
      inkTool = null;
    }

    function finishActiveInput() {
      const pointerId = inkPointerId;
      inkPointerId = null;
      penContactArmed = false;
      isTrackingSwipe = false;
      finishInkStroke();
      setPenEraser(false);
      if (pointerId !== null && activeCanvas.hasPointerCapture && activeCanvas.hasPointerCapture(pointerId)) {
        activeCanvas.releasePointerCapture(pointerId);
      }
    }

    function swipePoint(e) {
      return {identifier:e.pointerId, clientX:e.clientX, clientY:e.clientY};
    }

    function getNotebookEraserMetrics() {
      const size = Math.trunc(Number(toolSizes.eraser) || 25);
      const baseRadius = Math.max(.008, size * .001);
      const displayedHeight = slideWrapper.getBoundingClientRect?.().height || slideWrapper.clientHeight || 1;
      const baseHeight = slideWrapper.clientHeight || displayedHeight;
      // CSS pixels stay fixed during paper zoom. The wire radius uses page
      // height units, so divide by the actual displayed (zoomed) paper height.
      const screenRadius = baseRadius * baseHeight;
      return {screenRadius, pageRadius:screenRadius / displayedHeight};
    }

    function eraseAt(pos) {
      sendWS({type:'erase', normX:pos.normX, normY:pos.normY,
        mode:eraserMode, size:toolSizes.eraser || 25, radius:getNotebookEraserMetrics().pageRadius});
    }

    function onInkStart(e) {
      if (typeof canEditNotebook === 'function' && !canEditNotebook()) return;
      if (currentTool === 'lasso' && !isPenEraser(e)) return;
      if (e.pointerType === 'pen') {
        penInRange = true;
        penContactArmed = true;
        setPenEraser(isPenEraser(e));
        // Pressing the barrel button in the air also fires pointerdown.
        if (!penHasContact(e)) { e.preventDefault(); return; }
      }
      if (currentTool === 'pointer' && !isPenEraser(e)) return;
      if (e.pointerType === 'touch' && penInRange) return;
      if (inkPointerId !== null) {
        // A pen takes precedence over a finger that was waiting for a swipe.
        if (e.pointerType === 'pen' && !isDrawing) finishActiveInput();
        else return;
      }
      if (e.pointerType === 'mouse' && e.button !== 0) return;
      e.preventDefault();
      inkPointerId = e.pointerId;
      if (e.pointerType === 'pen') penContactArmed = true;
      if (window.PointerEvent && activeCanvas.setPointerCapture) activeCanvas.setPointerCapture(e.pointerId);
      if ((!currentTool && !isPenEraser(e)) || (e.pointerType === 'touch' && penOnlyToggle.checked)) {
        startSwipe(swipePoint(e));
        return;
      }
      beginInkAt(getPointerNormPos(e), isPenEraser(e) ? 'eraser' : currentTool, inputPressure(e));
    }

    function inputPressure(e) {
      return e.pointerType === 'pen' && e.pressure > 0 ? Math.min(1, e.pressure) : 1;
    }

    function beginInkAt(pos, tool, pressure = 1) {
      inkTool = tool;
      if (inkTool === 'eraser') { sendWS({type:'erase_start'}); eraseAt(pos); return; }
      if (!inkTool || inkTool === 'pointer' || inkTool === 'lasso') return;
      inkLineMode = isLineMode;
      inkMeta = {color:currentColor, width_ratio:getCurrentWidthRatio(), opacity:getToolOpacity(),
        brush:typeof getCurrentBrush === 'function' ? getCurrentBrush() : inkTool === 'highlighter' ? 'highlighter' : 'pen'};
      isDrawing = true;
      const point = [pos.normX, pos.normY, pressure];
      currentStrokePoints = inkLineMode ? [point, point.slice()] : [point];
      drawStroke(activeCtx, {...inkMeta, points:currentStrokePoints});
      sendWS({type:'stroke_start', tool:inkTool, color:inkMeta.color,
        widthRatio:inkMeta.width_ratio, normX:pos.normX, normY:pos.normY,
        pressure, opacity:inkMeta.opacity, brush:inkMeta.brush, isLine:inkLineMode});
    }

    function onInkMove(e) {
      if (e.pointerType === 'pen') {
        setPenEraser(isPenEraser(e));
        if (e.pointerId === inkPointerId && !penHasContact(e)) {
          // Lifting the tip with the barrel button held does not fire pointerup.
          finishInkStroke();
          isTrackingSwipe = false;
          return;
        }
        if (inkPointerId === null && penContactArmed && penHasContact(e)) {
          onInkStart(e);
          return;
        }
      }
      if (e.pointerId !== inkPointerId) return;
      e.preventDefault();
      const pos = getPointerNormPos(e);
      const tool = isPenEraser(e) ? 'eraser' : currentTool;
      if (e.pointerType === 'pen' && tool !== inkTool && !isTrackingSwipe) {
        finishInkStroke();
        beginInkAt(pos, tool, inputPressure(e));
        return;
      }
      moveInkTo(pos, inputPressure(e));
    }

    function moveInkTo(pos, pressure = 1) {
      if (inkTool === 'eraser') { eraseAt(pos); return; }
      if (!isDrawing) return;
      let x = pos.normX, y = pos.normY;
      if (inkLineMode) {
        const first = currentStrokePoints[0];
        const dx = (x - first[0]) * slideWrapper.clientWidth;
        const dy = (y - first[1]) * slideWrapper.clientHeight;
        const angle = Math.abs(Math.atan2(dy, dx) * 180 / Math.PI);
        if (angle < 5 || angle > 175) y = first[1];
        else if (Math.abs(angle - 90) < 5) x = first[0];
        currentStrokePoints = [first, [x, y, pressure]];
        sendWS({type:'line_update', normX:x, normY:y});
      } else {
        const last = currentStrokePoints[currentStrokePoints.length - 1];
        const dx = (x - last[0]) * slideWrapper.clientWidth;
        const dy = (y - last[1]) * slideWrapper.clientHeight;
        if (dx * dx + dy * dy < 2.25) return;
        currentStrokePoints.push([x, y, pressure]);
        sendWS({type:'stroke_move', normX:x, normY:y, pressure});
      }
      activeCtx.clearRect(0, 0, activeCanvas.width, activeCanvas.height);
      drawStroke(activeCtx, {...inkMeta, points:currentStrokePoints});
    }

    function onInkEnd(e, cancelled = false) {
      if (e.pointerType === 'pen') {
        penContactArmed = false;
        setPenEraser(false);
        if (cancelled) penInRange = false;
      }
      if (e.pointerId !== inkPointerId) return;
      e.preventDefault();
      if (!cancelled) {
        if (isTrackingSwipe) checkSwipe(swipePoint(e));
        else if (isDrawing) moveInkTo(getPointerNormPos(e), currentStrokePoints.at(-1)?.[2] ?? 1);
      }
      finishActiveInput();
    }

    if (window.PointerEvent) {
      // Android Chrome can consume all contact events while the barrel button
      // is held. Toggle on the hover press, then draw with the button released.
      for (const name of ['pointerenter', 'pointerdown', 'pointermove', 'pointerup']) {
        activeCanvas.addEventListener(name, observePenButton, {capture:true});
        // Selection frames and handles sit above the ink canvas. Their hover
        // button events must use the same shortcut without observing ink twice.
        stage.addEventListener(name, e => {
          if (e.target !== activeCanvas && (e.target === stage
              || e.target?.closest?.('#slide-wrapper'))) observePenButton(e);
        }, {capture:true});
      }
      activeCanvas.addEventListener('pointerenter', e => { if (e.pointerType === 'pen') penInRange = true; });
      activeCanvas.addEventListener('pointerleave', e => {
        if (e.pointerType === 'pen') {
          penInRange = false;
          if (inkPointerId === null) { penContactArmed = false; setPenEraser(false); }
        }
      });
      activeCanvas.addEventListener('pointerdown', onInkStart);
      activeCanvas.addEventListener('pointermove', e => {
        if (e.pointerType === 'pen' && (e.pointerId !== inkPointerId || !penHasContact(e)
            || (isPenEraser(e) ? 'eraser' : currentTool) !== inkTool)) {
          onInkMove(e);
          return;
        }
        if (e.pointerId !== inkPointerId) return;
        const samples = e.getCoalescedEvents ? e.getCoalescedEvents() : [];
        for (const sample of samples.length ? samples : [e]) {
          if (sample !== e) penProtocol.inherit(sample, e);
          onInkMove(sample);
        }
      });
      activeCanvas.addEventListener('pointerup', e => onInkEnd(e));
      activeCanvas.addEventListener('pointercancel', e => {
        penButtonDown = false; penProtocol.reset(); onInkEnd(e, true);
        if (typeof resetPenButtonGesture === 'function') resetPenButtonGesture();
      });
      activeCanvas.addEventListener('lostpointercapture', e => onInkEnd(e, true));

      let stageSwipePointer = null;
      stage.addEventListener('pointerdown', e => {
        if (e.target !== stage || e.pointerType !== 'touch' || penInRange || inkPointerId !== null) return;
        stageSwipePointer = e.pointerId;
        stage.setPointerCapture(e.pointerId);
        startSwipe(swipePoint(e));
        e.preventDefault();
      });
      stage.addEventListener('pointerup', e => {
        if (e.pointerId !== stageSwipePointer) return;
        checkSwipe(swipePoint(e));
        stageSwipePointer = null;
      });
      stage.addEventListener('pointercancel', e => {
        if (e.pointerId !== stageSwipePointer) return;
        stageSwipePointer = null;
        isTrackingSwipe = false;
      });
    } else {
      // Older Safari: keep Touch Events only when Pointer Events are unavailable.
      function asPointer(touch, event) {
        return {pointerId:touch.identifier, pointerType:touch.touchType === 'stylus' ? 'pen' : 'touch',
          clientX:touch.clientX, clientY:touch.clientY, button:0, pressure:touch.force || 0,
          buttons:event.type === 'touchend' || event.type === 'touchcancel' ? 0 : 1,
          preventDefault:() => event.preventDefault()};
      }
      for (const [name, handler] of [['touchstart',onInkStart], ['touchmove',onInkMove],
        ['touchend',onInkEnd], ['touchcancel',e => onInkEnd(e, true)]]) {
        activeCanvas.addEventListener(name, event => {
          for (const touch of event.changedTouches) handler(asPointer(touch, event));
        }, {passive:false});
      }
      stage.addEventListener('touchstart', e => {
        if (e.target === stage && e.touches[0]) { startSwipe(e.touches[0]); e.preventDefault(); }
      }, {passive:false});
      stage.addEventListener('touchend', e => {
        if (e.target === stage && e.changedTouches[0]) checkSwipe(e.changedTouches[0]);
      }, {passive:false});
      stage.addEventListener('touchcancel', () => { isTrackingSwipe = false; });
    }
    activeCanvas.addEventListener('contextmenu', e => e.preventDefault());
    window.addEventListener('blur', () => {
      finishActiveInput(); penInRange = false; penButtonDown = false; penProtocol.reset();
      if (typeof resetPenButtonGesture === 'function') resetPenButtonGesture();
    });
    if (typeof quickEraser !== 'undefined') quickEraser.addEventListener('click', toggleQuickEraser);
    if (typeof penButtonModeSelect !== 'undefined') {
      penButtonModeSelect.value = penButtonMode;
      penButtonModeSelect.addEventListener('change', () => {
        finishActiveInput();
        penButtonDown = false;
        penProtocol.reset();
        penButtonMode = penButtonModeSelect.value === 'toggle' ? 'toggle' : 'hold';
        try { localStorage.setItem('notesync_pen_button_mode', penButtonMode); } catch (_) {}
      });
    }
"""
