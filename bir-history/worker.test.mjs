import {test} from 'node:test';
import assert from 'node:assert/strict';
import {detailTargets,refreshAllDetails,parseRows} from './worker.mjs';

test('catalog EUR signature excludes BYN recalculations',()=>{
  const html=by=>`<tr data-loadobject="25b23ad0-a8a8-47ee-8c03-bda52db2bf6e"><td>528</td><td>24.2.2</td><td>x</td><td>4</td><td>1с</td><td>49.62</td><td>1</td><td><p>${by} BYN</p><span class="tprice">66 540 €</span></td></tr>`;
  assert.deepEqual(parseRows(html(123))[0].prices_eur,[66540]);
  assert.deepEqual(parseRows(html(456))[0].prices_eur,[66540]);
});

test('repeated listing changes cannot starve oldest cards',()=>{
  const rows=Array.from({length:60},(_,i)=>({id:String(i).padStart(3,'0'),detail_fetched_at:i<24?'2026-11-03':'2026-09-28'}));
  const seen=new Set(rows.map(r=>r.id));
  const first=detailTargets(rows,seen);
  assert.equal(first.length,24);
  assert.ok(first.every(r=>r.detail_fetched_at==='2026-09-28'));
  for(const r of first) r.detail_fetched_at='2026-11-04';
  assert.ok(detailTargets(rows,seen).every(r=>!first.includes(r)));
});

test('missing cards never enter refresh queue; null timestamps come first',()=>{
  const rows=[{id:'gone',detail_fetched_at:null},{id:'old',detail_fetched_at:'2026-09-28'},{id:'never',detail_fetched_at:null}];
  assert.deepEqual(detailTargets(rows,new Set(['old','never'])).map(r=>r.id),['never','old']);
});

test('nightly refresh replaces validated detail, preserves old data on wrong ID and reports failure',async()=>{
  const original=globalThis.fetch;
  const writes=[];
  const db={prepare(sql){return {all:async()=>({results:[{id:'good',detail_json:'{}'},{id:'bad',detail_json:'{}'}]}),bind(...params){return {run:async()=>{writes.push({sql,params});},statement:{sql,params}};}};},batch:async(statements)=>{writes.push(...statements.map(s=>s.statement));}};
  globalThis.fetch=async(_url,args)=>new Response(JSON.stringify({id:new URLSearchParams(args.body).get('objectid')==='good'?'good':'wrong',object:'Minsk World',vid:'Квартира',Rassrochka10_cena:66540}));
  try {
    const result=await refreshAllDetails({BIR_DB:db});
    assert.equal(result.ok,false); assert.equal(result.details,1);assert.equal(result.errors.length,1);
    const updates=writes.filter(x=>x.sql.startsWith('UPDATE bir_objects'));
    assert.equal(updates.length,1);assert.equal(updates[0].params[2],'good');
    assert.equal(JSON.parse(updates[0].params[0]).Rassrochka10_cena,66540);
  } finally {globalThis.fetch=original;}
});
