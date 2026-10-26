import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';

const source=fs.readFileSync(new URL('../beamerplus/TabletText.py',import.meta.url),'utf8');
const drawScript=source.split('NOTE_TEXT_SCRIPT = r"""')[1].split('"""')[0];
const installScript=source.split('INSTALL_TEXT_SCRIPT = r"""')[1].split('"""')[0];
const svg='<svg xmlns="http://www.w3.org/2000/svg" width="64" height="40"><text>研究 x²</text></svg>';
const item=(extra={})=>({id:'text-1',text:'研究 $x^2$',norm_x:.25,norm_y:.3,size:18,color:'#3478dc',renderedSvg:svg,renderedWidth:2,renderedHeight:1.25,...extra});

function harness(){
  const context=vm.createContext({TextEncoder,btoa,structuredClone});
  vm.runInContext(`
    const images=[],frames=new Map(),calls=[],baseRenders=[];
    let frameSequence=0,frameRequests=0,publicRenders=0,currentDocumentId='a',noteTexts=[],width=800,height=600;
    let sketchbookStrokes=[{id:'selected',points:[[.1,.1,.5],[.3,.3,.8]]},{id:'other',points:[[.7,.7,.4],[.8,.8,.6]]}];
    let selectedInk=[],selectionBackgroundSplit=false,selectionDrag=null,selectionRequest=null,selectionPending=null;
    const selectionLayer={style:{transform:''}};
    class Image {
      constructor(){this.index=images.length;images.push(this);}
      set src(value){this.url=value;}
      get src(){return this.url;}
    }
    const document={createElement(){throw new Error('SVG must not be inserted into the DOM');}};
    function requestAnimationFrame(fn){frameRequests++;const id=++frameSequence;frames.set(id,fn);return id;}
    function flushFrames(){const callbacks=[...frames.values()];frames.clear();for(const fn of callbacks)fn();}
    const ctx={
      transform:[2,0,0,2,0,0],font:'original font',fillStyle:'#123456',textBaseline:'middle',stack:[],
      save(){this.stack.push({transform:this.transform.slice(),font:this.font,fillStyle:this.fillStyle,textBaseline:this.textBaseline});},
      restore(){Object.assign(this,this.stack.pop());},
      setTransform(){throw new Error('annotation paint must preserve the canvas transform');},
      clearRect(){calls.push({type:'clear'});},
      fillText(...args){calls.push({type:'text',args,font:this.font,color:this.fillStyle,transform:this.transform.slice()});},
      drawImage(image,...args){calls.push({type:'image',image:image.index,args,transform:this.transform.slice()});}
    };
    function renderBaseInk(strokes){baseRenders.push({noteId:currentDocumentId,strokes:structuredClone(strokes),width,height});ctx.clearRect();drawNoteTexts(ctx,noteTexts,width,height);}
    function renderAllStrokes(strokes){publicRenders++;if(selectionDrag)throw new Error('public render cancels the current drag');renderBaseInk(strokes);}
  `+drawScript+installScript,context);
  const run=code=>vm.runInContext(code,context);
  const read=code=>JSON.parse(run(`JSON.stringify((${code})??null)`));
  const texts=items=>run('(items)=>{noteTexts=items;}')(items);
  const draw=(items)=>{if(items)texts(items);run('drawNoteTexts(ctx,noteTexts,width,height)');};
  const load=(index=0)=>run(`images[${index}].onload()`);
  const fail=(index=0)=>run(`images[${index}].onerror()`);
  const flush=()=>run('flushFrames()');
  return {run,read,texts,draw,load,fail,flush};
}

test('math SVG is decoded as a UTF-8 Image data URL and stays blank until the image loads',()=>{
  const h=harness();h.draw([item()]);
  assert.equal(h.read('images.length'),1);assert.deepEqual(h.read('calls'),[]);
  const url=h.read('images[0].src');assert.match(url,/^data:image\/svg\+xml;base64,/);assert.equal(Buffer.from(url.split(',')[1],'base64').toString('utf8'),svg);
  h.load();assert.equal(h.read('frames.size'),1);h.flush();
  assert.deepEqual(h.read("calls.filter(call=>call.type==='image')[0].args"),[200,180,32,20]);
});

test('cached image scales to the latest page size without another image request',()=>{
  const h=harness();h.draw([item()]);h.load();h.flush();h.run('width=1600;height=1200;calls.length=0');h.draw();
  assert.equal(h.read('images.length'),1);assert.deepEqual(h.read("calls.find(call=>call.type==='image').args"),[400,360,64,40]);
});

test('annotations preserve the canvas density transform and prior text state',()=>{
  const h=harness();h.draw([item()]);h.load();h.flush();
  assert.deepEqual(h.read("calls.find(call=>call.type==='image').transform"),[2,0,0,2,0,0]);
  assert.deepEqual(h.read('ctx.transform'),[2,0,0,2,0,0]);assert.equal(h.read('ctx.font'),'original font');assert.equal(h.read('ctx.fillStyle'),'#123456');assert.equal(h.read('ctx.textBaseline'),'middle');assert.equal(h.read('ctx.stack.length'),0);
});

test('an image loaded after switching notes cannot paint annotations from the previous note',()=>{
  const h=harness();h.draw([item()]);h.run("currentDocumentId='b';noteTexts=[]");h.load();h.flush();
  assert.equal(h.read('baseRenders.length'),0);assert.equal(h.read('calls.length'),0);
});

test('a queued image repaint is canceled logically when its annotation is removed',()=>{
  const h=harness();h.draw([item()]);h.load();h.texts([]);h.flush();
  assert.equal(h.read('baseRenders.length'),0);assert.equal(h.read('calls.length'),0);
});

test('late image loading uses the latest coordinates and latest ink rather than captured scene data',()=>{
  const h=harness();h.draw([item()]);h.load();h.texts([item({norm_x:.6,norm_y:.1})]);
  h.run("width=1200;height=900;sketchbookStrokes.push({id:'new-ink',points:[[.4,.5,.5]]})");h.flush();
  assert.deepEqual(h.read("calls.find(call=>call.type==='image').args"),[720,90,48,30]);assert.equal(h.read('baseRenders[0].strokes.length'),3);assert.equal(h.read('baseRenders[0].width'),1200);
});

test('multiple image completions coalesce into a single latest-scene repaint',()=>{
  const h=harness();h.draw([item(),item({id:'text-2',renderedSvg:svg.replace('x²','y³')})]);h.load(0);h.load(1);
  assert.equal(h.read('frameRequests'),1);assert.equal(h.read('frames.size'),1);h.flush();
  assert.equal(h.read('baseRenders.length'),1);assert.equal(h.read("calls.filter(call=>call.type==='image').length"),2);
});

test('image load preserves drag pointers and cached selection transform while repainting only unselected ink',()=>{
  const h=harness();h.draw([item()]);h.run("selectedInk=[0];selectionBackgroundSplit=true;selectionDrag={pointer:7};selectionLayer.style.transform='matrix(1,0,0,1,200,60)'");h.load();h.flush();
  assert.deepEqual(h.read('baseRenders[0].strokes.map(stroke=>stroke.id)'),['other']);assert.equal(h.read('publicRenders'),0);assert.deepEqual(h.read('selectionDrag'),{pointer:7});assert.deepEqual(h.read('selectedInk'),[0]);assert.equal(h.read('selectionLayer.style.transform'),'matrix(1,0,0,1,200,60)');
});

test('a completed optimistic selection stays in its cached layer until its acknowledgement',()=>{
  const h=harness();h.draw([item()]);h.run("selectedInk=[0];selectionBackgroundSplit=true;selectionRequest='edit-1';selectionPending={optimistic:true};selectionLayer.style.transform='matrix(1,0,0,1,200,60)';sketchbookStrokes[0].points[0]=[.3,.2,.5]");h.load();h.flush();
  assert.deepEqual(h.read('baseRenders[0].strokes.map(stroke=>stroke.id)'),['other']);assert.equal(h.read('selectionRequest'),'edit-1');assert.deepEqual(h.read('selectionPending'),{optimistic:true});assert.equal(h.read('selectionLayer.style.transform'),'matrix(1,0,0,1,200,60)');
});

test('clearing selection before image completion restores all latest ink to the background',()=>{
  const h=harness();h.draw([item()]);h.run('selectedInk=[0];selectionBackgroundSplit=true');h.load();h.run('selectedInk=[];selectionBackgroundSplit=false');h.flush();
  assert.deepEqual(h.read('baseRenders[0].strokes.map(stroke=>stroke.id)'),['selected','other']);
});

test('failed images use literal text without retrying the same SVG or inserting markup',()=>{
  const h=harness();h.draw([item({text:'<script>literal</script> $x^2$'})]);h.fail();h.flush();h.draw();
  assert.equal(h.read('images.length'),1);assert.equal(h.read("calls.some(call=>call.type==='image')"),false);assert.equal(h.read("calls.find(call=>call.type==='text').args[0]"),'<script>literal</script> $x^2$');
});

test('the image cache is bounded and plain text does not create Image instances',()=>{
  const h=harness();h.draw([item({renderedSvg:undefined})]);assert.equal(h.read('images.length'),0);
  for(let i=0;i<130;i++)h.draw([item({renderedSvg:svg.replace('x²','x'+i)})]);
  assert.equal(h.read('noteTextImageCache.size'),128);
});

test('a note with more math blocks than the history cache limit does not reload its own images forever',()=>{
  const h=harness();h.draw(Array.from({length:130},(_,index)=>item({id:'text-'+index,renderedSvg:svg.replace('x²','x'+index)})));
  for(let index=0;index<130;index++)h.load(index);h.flush();
  assert.equal(h.read('images.length'),130);assert.equal(h.read('frames.size'),0);assert.equal(h.read("calls.filter(call=>call.type==='image').length"),130);
  h.draw([item({renderedSvg:undefined})]);assert.equal(h.read('noteTextImageCache.size'),128);
});
