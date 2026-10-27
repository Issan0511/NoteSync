import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';

function model(file,name){
  const source=fs.readFileSync(new URL('../notesync/'+file,import.meta.url),'utf8').split(name+' = r"""')[1].split('"""')[0];
  const context=vm.createContext({});vm.runInContext(source,context);return code=>vm.runInContext(code,context);
}
const geometry=model('TabletSelection.py','SELECTION_GEOMETRY_SCRIPT');
const view=model('TabletNavigation.py','VIEW_MODEL_SCRIPT');
const polygon=[[.2,.2],[.6,.2],[.6,.6],[.2,.6]];

test('lasso selects dots and whole sparse strokes crossing its boundary',()=>{
  const strokes=[{points:[[.3,.3,.7]]},{points:[[.1,.4,.2],[.8,.4,.6]]},{points:[[.8,.8,1],[.9,.9,1]]}];
  const selected=geometry(`InkSelectionGeometry.selected(${JSON.stringify(strokes)},${JSON.stringify(polygon)})`);
  assert.deepEqual(Array.from(selected),[0,1]);
});
test('lasso rejects short paths and handles a concave boundary',()=>{
  assert.equal(geometry('InkSelectionGeometry.selected([{points:[[.3,.3]]}],[[0,0],[1,1]]).length'),0);
  assert.equal(geometry('InkSelectionGeometry.inside([.7,.7],[[0,0],[1,0],[1,.3],[.3,.3],[.3,1],[0,1]])'),false);
  assert.equal(geometry('InkSelectionGeometry.inside([.1,.7],[[0,0],[1,0],[1,.3],[.3,.3],[.3,1],[0,1]])'),true);
});
test('collinear polygon edge contact counts, separated collinear segments do not',()=>{
  assert.equal(geometry('InkSelectionGeometry.intersects([0,0],[.5,0],[.3,0],[.8,0])'),true);
  assert.equal(geometry('InkSelectionGeometry.intersects([0,0],[.2,0],[.3,0],[.8,0])'),false);
});
test('transform preview keeps pressure, brush, and opacity and scales line width',()=>{
  const stroke={points:[[.1,.2,.7],[.2,.4,.9]],width_ratio:.005,brush:'fountain',opacity:.4,color:'#123456'};
  const result=JSON.parse(geometry(`JSON.stringify(InkSelectionGeometry.transform(${JSON.stringify(stroke)},[2,0,0,2,.1,.2],2))`));
  assert.deepEqual(result.points[0],[.30000000000000004,.6000000000000001,.7]);
  assert.equal(result.width_ratio,.01);assert.equal(result.brush,'fountain');assert.equal(result.opacity,.4);
  assert.deepEqual(stroke.points[0],[.1,.2,.7]);
});
test('rotation accounts for page aspect so physical length stays constant',()=>{
  const result=JSON.parse(geometry('JSON.stringify(InkSelectionGeometry.transform({width_ratio:.01,points:[[.6,.5,.8]]},InkSelectionGeometry.rotation(Math.PI/2,{x:.5,y:.5},2)))'));
  assert.ok(Math.abs(result.points[0][0]-.5)<1e-10);assert.ok(Math.abs(result.points[0][1]-.7)<1e-10);
});
test('bounds of a single dot still have draggable handles',()=>{
  assert.ok(geometry('InkSelectionGeometry.bounds([{points:[[.3,.4,1]]}]).width')>0);
  assert.equal(geometry('InkSelectionGeometry.bounds([])'),null);
});
test('zoom keeps the point under the cursor stationary',()=>{
  const result=JSON.parse(view('const v=new NotebookViewTransform();v.zoomAt(2,{x:300,y:250},{x:500,y:400});JSON.stringify(v)'));
  assert.deepEqual(result,{scale:2,x:200,y:150});
});
test('zoom limits and fit reset cannot leave the paper offscreen',()=>{
  assert.equal(view('v.zoomAt(99,{x:300,y:250},{x:500,y:400});v.scale'),5);
  const result=JSON.parse(view('v.zoomAt(.1,{x:300,y:250},{x:500,y:400});JSON.stringify(v)'));
  assert.deepEqual(result,{scale:1,x:0,y:0});
});
test('panning is constrained against the transformed page and viewport',()=>{
  const result=JSON.parse(view('v.scale=2;v.x=100000;v.y=-100000;v.constrain(1000,600,900,550);JSON.stringify(v)'));
  assert.equal(result.x,520);assert.equal(result.y,-370);
});
