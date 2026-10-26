import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';

const script=fs.readFileSync(new URL('../beamerplus/TabletText.py',import.meta.url),'utf8')
  .split('NOTE_TEXT_SCRIPT = r"""')[1].split('"""')[0];

test('typed tutor text stays literal and uses the same lines and geometry when zoomed',()=>{
  const calls=[];
  const ctx={save(){},restore(){},fillText(...args){calls.push({args,font:this.font,color:this.fillStyle});}};
  const context=vm.createContext({ctx});
  vm.runInContext(script,context);
  vm.runInContext(`drawNoteTexts(ctx,[{text:'<script>literal</script>\\n次は x ≠ 0',norm_x:.5,norm_y:.25,size:18,color:'#3478dc'}],1600,1200)`,context);
  assert.equal(calls[0].args[0],'<script>literal</script>');
  assert.equal(calls[0].args[1],800);
  assert.equal(calls[0].args[2],332);
  assert.equal(calls[1].args[0],'次は x ≠ 0');
  assert.equal(calls[1].args[2],378.4);
  assert.equal(calls[0].font,'32px sans-serif');
  assert.equal(calls[0].color,'#3478dc');
});
