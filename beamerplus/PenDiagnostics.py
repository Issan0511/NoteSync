"""Temporary, Tailnet-only pen event probe, independent of the running notebook.

Run with ``python -m beamerplus.PenDiagnostics``. Keeps only bounded input flags
in memory; notebook content, coordinates, keystrokes, and API keys aren't read.
"""

import argparse
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import math
import threading
from urllib.parse import urlsplit

from beamerplus.ConnectionPolicy import ConnectionPolicy, websocket_origin_allowed
from beamerplus.PenProtocol import PEN_PROTOCOL_SCRIPT


HTML = r"""<!doctype html><html lang="ja"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>S Pen入力確認・修正版</title><style>
*{box-sizing:border-box}body{margin:0;background:#171d24;color:#eef2f7;font:16px system-ui;padding:20px}
main{max-width:880px;margin:auto}h1{font-size:23px;margin:0 0 12px}li{margin:6px 0}
p,li{line-height:1.6}#pad{display:block;width:100%;height:40vh;min-height:200px;background:#fff;
border:3px solid #39b79b;border-radius:12px;touch-action:none;user-select:none;-webkit-user-select:none}
output{display:block;padding:12px 0;font-weight:600;color:#8fe2cf}pre{white-space:pre-wrap;
font-size:13px;background:#0e1319;padding:12px;border-radius:8px;max-height:27vh;overflow:auto}
small{color:#b5c0cd}button{padding:10px;background:#28323d;color:white;border:1px solid #718399;border-radius:8px}
</style><main><h1>S Pen入力確認・修正版</h1>
<p>白い枠で順番に試してください。ノートの内容は変わりません。</p>
<ol><li>普通に短い線を書く。</li><li>ペン先を画面の近くで浮かせ、ボタンを押して離す。</li>
<li>ボタンを押したまま線を書く。</li></ol>
<canvas id="pad" width="1000" height="500" aria-label="ペン入力を試す白い枠"></canvas>
<output id="status" role="status">まだ入力を受け取っていません</output>
<small id="upload">ボタン・接触の情報を、このノートを動かすPCへ送ります。筆跡・座標・APIキーは送りません。</small>
<pre id="log">入力すると、受け取った情報がここに表示されます。</pre>
<button id="done" type="button">確認を終えてノートへ戻る</button></main>
<script>
__PEN_PROTOCOL__
const pad=document.querySelector('#pad'),ctx=pad.getContext('2d');
const status=document.querySelector('#status'),log=document.querySelector('#log'),upload=document.querySelector('#upload');
const ua=navigator.userAgent;
const browser=/SamsungBrowser\//.test(ua)?'Samsung Internet':/Firefox\//.test(ua)?'Firefox':/Chrom(e|ium)\//.test(ua)?'Chrome':'other';
const protocol=new PenProtocol(ua),lastRecords=new Map();
let queue=[],lines=[],posting=false,received=0;
const drawn=new Map();
function record(e){
  const touch=e.changedTouches&&e.changedTouches[0];
  const sample={event:e.type,pointer:e.pointerType||(touch?(touch.touchType==='stylus'?'pen':'touch'):'mouse'),
    button:Number.isInteger(e.button)?e.button:-1,buttons:Number.isInteger(e.buttons)?e.buttons:-1,
    pressure:typeof e.pressure==='number'?e.pressure:touch&&typeof touch.force==='number'?touch.force:0};
  const pen=protocol.read(e);
  if(e.pointerType==='pen')status.textContent=`${browser} / ${pen.barrel?'ボタン押下を検出':'ボタンOFF'} / ${pen.contact?'接触中':'空中'}`;
  const signature=JSON.stringify(sample),now=performance.now(),last=lastRecords.get(e.type);
  if(e.type.endsWith('move')&&last&&signature===last.signature&&now-last.at<150)return;
  lastRecords.set(e.type,{signature,at:now});received++;
  queue.push(sample);if(queue.length>40)queue.shift();
  const line=`${sample.event} ${sample.pointer} button=${sample.button} buttons=${sample.buttons} pressure=${sample.pressure.toFixed(2)}`;
  lines.unshift(line);lines=lines.slice(0,22);log.textContent=lines.join('\n');
  if(!window.PointerEvent)status.textContent=`${browser} / 受信 ${received}件 / ${sample.pointer} / buttons=${sample.buttons}`;
}
for(const name of ['pointerenter','pointerleave','pointerdown','pointermove','pointerup','pointercancel',
  'mousedown','mousemove','mouseup','contextmenu','touchstart','touchmove','touchend','touchcancel']){
  pad.addEventListener(name,record,{capture:true,passive:true});
}
pad.addEventListener('contextmenu',e=>e.preventDefault());
function draw(e){
  const pen=protocol.read(e),contact=e.pointerType==='pen'?pen.contact:(e.buttons&1)!==0;
  if(!contact){drawn.delete(e.pointerId);return;}
  const rect=pad.getBoundingClientRect(),x=(e.clientX-rect.left)/rect.width*pad.width,y=(e.clientY-rect.top)/rect.height*pad.height;
  const previous=drawn.get(e.pointerId);ctx.beginPath();ctx.lineWidth=pen.barrel?35:4;ctx.strokeStyle='#126f62';ctx.lineCap='round';
  ctx.globalCompositeOperation=pen.barrel?'destination-out':'source-over';
  ctx.moveTo(previous?previous[0]:x,previous?previous[1]:y);ctx.lineTo(x,y);ctx.stroke();drawn.set(e.pointerId,[x,y]);
  e.preventDefault();
}
pad.addEventListener('pointerdown',draw);pad.addEventListener('pointermove',draw);
for(const name of ['pointerup','pointercancel','pointerleave'])pad.addEventListener(name,e=>drawn.delete(e.pointerId));
async function flush(){
  if(posting||!queue.length)return;posting=true;const events=queue.splice(0,40);
  try{const response=await fetch('/events',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({browser,events}),keepalive:true});
    if(!response.ok)throw Error('upload');upload.textContent='✓ 入力情報はPCに届いています。筆跡・座標・APIキーは送っていません。';
  }catch(_){queue=events.concat(queue).slice(-40);upload.textContent='入力情報の送信待ちです。ページを開いたままにしてください。';}
  finally{posting=false;}
}
setInterval(flush,500);document.addEventListener('visibilitychange',flush);window.addEventListener('blur',flush);
document.querySelector('#done').addEventListener('click',async()=>{await flush();location.href=`http://${location.hostname}:8080/`;});
</script></html>""".replace('__PEN_PROTOCOL__', PEN_PROTOCOL_SCRIPT)

EVENTS = frozenset(('pointerenter', 'pointerleave', 'pointerdown', 'pointermove', 'pointerup', 'pointercancel',
                    'mousedown', 'mousemove', 'mouseup', 'contextmenu', 'touchstart', 'touchmove', 'touchend', 'touchcancel'))


def sanitize(payload):
    """Accept only input flags; discard any extra fields supplied by the client."""
    if not isinstance(payload, dict) or payload.get('browser') not in ('Chrome', 'Samsung Internet', 'Firefox', 'other'):
        raise ValueError('browser')
    events = payload.get('events')
    if not isinstance(events, list) or not 1 <= len(events) <= 40:
        raise ValueError('events')
    clean = []
    for event in events:
        if not isinstance(event, dict) or event.get('event') not in EVENTS:
            raise ValueError('event')
        if event.get('pointer') not in ('pen', 'touch', 'mouse', 'unknown'):
            raise ValueError('pointer')
        if any(type(event.get(key)) is not int or not -1 <= event[key] <= 255 for key in ('button', 'buttons')):
            raise ValueError('button')
        pressure = event.get('pressure')
        if type(pressure) not in (float, int) or not math.isfinite(pressure) or not 0 <= pressure <= 1:
            raise ValueError('pressure')
        clean.append({key: event[key] for key in ('event', 'pointer', 'button', 'buttons', 'pressure')})
    return {'browser': payload['browser'], 'events': clean}


def make_handler(policy, samples, lock):
    visits = deque(maxlen=16)
    rejected_posts = deque(maxlen=16)

    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, body=b'', content_type='application/json'):
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Security-Policy', "frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not policy.passwordless(self.client_address[0]):
                self.reply(403)
            elif self.path == '/':
                agent = self.headers.get('User-Agent', '')
                browser = 'Samsung Internet' if 'SamsungBrowser/' in agent else 'Firefox' if 'Firefox/' in agent else 'Chrome' if 'Chrome/' in agent else 'other'
                with lock:
                    visits.append({'peer': self.client_address[0], 'browser': browser})
                self.reply(200, HTML.encode(), 'text/html; charset=utf-8')
            elif self.path == '/api/samples' and ipaddress.ip_address(self.client_address[0]).is_loopback:
                with lock:
                    body = json.dumps(list(samples)).encode()
                self.reply(200, body)
            elif self.path == '/api/health' and ipaddress.ip_address(self.client_address[0]).is_loopback:
                with lock:
                    body = json.dumps({'visits': list(visits), 'rejected_posts': list(rejected_posts)}).encode()
                self.reply(200, body)
            else:
                self.reply(404)

        def do_POST(self):
            if not policy.passwordless(self.client_address[0]) or not websocket_origin_allowed(
                    self.headers.get('Origin'), self.headers.get('Host', ''), self.server.server_port):
                with lock:
                    rejected_posts.append({'peer': self.client_address[0], 'code': 403})
                self.reply(403)
                return
            if self.path != '/events':
                self.reply(404)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16384:
                    raise ValueError('size')
                sample = sanitize(json.loads(self.rfile.read(length)))
            except (ValueError, TypeError, UnicodeError):
                with lock:
                    rejected_posts.append({'peer': self.client_address[0], 'code': 400})
                self.reply(400)
                return
            sample['peer'] = self.client_address[0]
            with lock:
                samples.append(sample)
            self.reply(204)

        def log_message(self, *args):
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8081)
    args = parser.parse_args()
    samples = deque(maxlen=80)
    server = ThreadingHTTPServer(('0.0.0.0', args.port), make_handler(ConnectionPolicy(), samples, threading.Lock()))
    print(f'Pen diagnostics ready on port {server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
