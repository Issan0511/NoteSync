import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';
const source=fs.readFileSync(new URL('../notesync/TabletStorage.py',import.meta.url),'utf8').split('STORAGE_SCRIPT = r"""')[1].split('"""')[0];
test('browser preferences copy once without overwriting new choices or moving other data',()=>{
  const data=new Map([['beamerplus_favorite_pens','saved pens'],['beamerplus_current_pen','old'],['notesync_current_pen','new'],['unrelated','keep']]);
  vm.runInNewContext(source,{localStorage:{getItem:k=>data.get(k)??null,setItem:(k,v)=>data.set(k,v)}});
  assert.equal(data.get('notesync_favorite_pens'),'saved pens');
  assert.equal(data.get('beamerplus_favorite_pens'),'saved pens');
  assert.equal(data.get('notesync_current_pen'),'new');
  assert.equal(data.size,5);
});
test('storage-disabled browser can still initialize',()=>{
  assert.doesNotThrow(()=>vm.runInNewContext(source,{localStorage:{getItem(){throw Error('disabled');}}}));
});
