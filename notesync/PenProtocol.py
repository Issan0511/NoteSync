"""Normalize standard pen events and measured Samsung Internet button events."""

PEN_PROTOCOL_SCRIPT = r"""
    class PenShortcutGesture {
      constructor() { this.reset(); }
      reset() { this.down=false; this.touched=false; this.started=0; this.lastClick=null; }
      update(signal, now) {
        let doubleClick=false;
        if (signal.barrel && !this.down) { this.started=now; this.touched=signal.contact; }
        if (signal.contact) { this.touched=true; this.lastClick=null; }
        if (!signal.barrel && this.down) {
          if (!this.touched && now-this.started<400) {
            if (this.lastClick!==null && now-this.lastClick<450) { doubleClick=true; this.lastClick=null; }
            else this.lastClick=now;
          } else this.lastClick=null;
        }
        this.down=signal.barrel;
        return doubleClick;
      }
    }
    class PenProtocol {
      constructor(userAgent = '') {
        this.samsung = /SamsungBrowser\//.test(userAgent);
        this.barrel = false;
        this.contact = false;
        this.events = new WeakMap();
      }
      reset() {
        this.barrel = false;
        this.contact = false;
        this.events = new WeakMap();
      }
      inherit(sample, event) {
        // Coalesced samples carry positions; use the dispatch event's buttons.
        this.events.set(sample, this.read(event));
      }
      read(e) {
        if (this.events.has(e)) return this.events.get(e);
        if (e.pointerType !== 'pen') return {barrel:false, eraser:false, contact:false};
        const buttons = typeof e.buttons === 'number' ? e.buttons : 0;
        const eraser = (buttons & 32) !== 0 || (e.buttons === undefined && e.button === 5);
        let barrel = (buttons & 2) !== 0 || (e.buttons === undefined && e.button === 2);
        if (this.samsung && !barrel && !eraser) {
          // Measured on Galaxy Tab S9: held barrel reports button=0/buttons=1
          // on every move, including hover. Normal tip moves report button=-1.
          if (['pointermove','pointerenter','pointerover'].includes(e.type)) {
            barrel = e.button === 0 && (buttons & 1) !== 0;
          } else if (e.type === 'pointerdown') {
            barrel = this.barrel;
          } else if (e.type === 'pointerup') {
            // Samsung emits buttons=0 on tip-up even with the barrel held.
            barrel = this.contact && this.barrel;
          } else if (e.type === 'pointerleave') {
            barrel = this.barrel;
          }
        }
        const contact = e.pressure > 0 || eraser || (!this.samsung && (buttons & 1) !== 0);
        this.barrel = barrel;
        this.contact = contact;
        const result = {barrel, eraser, contact};
        this.events.set(e, result);
        return result;
      }
    }
"""
