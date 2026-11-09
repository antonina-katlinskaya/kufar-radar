/* Regression checks for standalone Kufar Demand UI logic. Run with node demand-test-v1.cjs. */
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const src=fs.readFileSync(__dirname+'/demand-ui-v1.js','utf8');
new vm.Script(src);
const ads={
 A:{a:48.5,pe:100000,pu:115000,t:'A',ad:'Street A',img:'https://example.com/a.jpg',v:150,p:9,r:1,fs:1794200000},
 B:{a:48.5,pe:100000,pu:115000,t:'B',ad:'Street B',v:170,p:7,r:2,fs:1794100000},
 C:{a:48.5,pe:105000,pu:118000,t:'C',ad:'Street C',v:230,p:30,r:2,fs:1794050000},
 D:{a:90,pe:120000,pu:140000,t:'D',ad:'Street D',v:700,p:14,r:3,fs:1794040000}
};
const CUBE={days:{'2026-11-09':{
 a:{A:[20,4],B:[8,1],C:[12,3],D:[2,0]},
 pe:{A:{1:[10,1]},C:{2:[4,2]}},
 pr:{A:1,C:2},
 ev:[],ph:[],vh:[]
}}};
const ctx={CAT:{ads},CUBE,S:{newOnly:false},Date,Map,Set,Math,Number,String,Array,Object,Infinity,
 adOk:()=>true,fmt:x=>String(Math.round(x)),fmt1:x=>String(x),pct:(a,b)=>b?String(100*a/b)+'%':'—',
 todayStr:()=> '2026-11-09',addDays:(day,n)=>{const v=Date.parse(day+'T00:00:00Z')+n*86400000;return new Date(v).toISOString().slice(0,10)},
 esc:x=>String(x).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;'),
 empKey:()=> 'u',empName:()=> 'Agent',adCard:r=>'<article class="acard">'+r.id+'</article>',dtLocal:()=>'',number:x=>Number(x)
};
vm.createContext(ctx);vm.runInContext(src,ctx);
const set=(k,v)=>{const varValue=JSON.stringify(v);vm.runInContext('DEM.'+k+'='+varValue,ctx)};
const calc=()=>vm.runInContext('demAggregate()',ctx);
let a=calc();assert.equal(a.records.reduce((x,y)=>x+y.views,0),42);assert.equal(a.records.reduce((x,y)=>x+y.opens,0),8);
assert.equal(a.records.length,3);assert.equal(a.ids.size,4);
set('mode','paid');a=calc();assert.equal(a.records.reduce((x,y)=>x+y.views,0),14);assert.equal(a.records.reduce((x,y)=>x+y.opens,0),3);
set('mode','free');a=calc();assert.equal(a.records.reduce((x,y)=>x+y.views,0),28);assert.equal(a.records.reduce((x,y)=>x+y.opens,0),5);
set('mode','all');set('group','price');a=calc();assert.equal(a.records.length,2);assert.equal(a.records.find(x=>x.low===100000)?.views,40);
set('group','area');a=calc();assert.equal(a.records.length,2);assert.equal(a.records.find(x=>x.low===45)?.views,40);
set('group','exact');set('metric','opens');a=calc();assert.equal(a.records[0].opens,5);
set('metric','ratio');a=calc();assert.equal(a.records[0].views>=20,true);assert.equal(vm.runInContext('demValue({views:5,opens:5})',ctx),-1);
set('metric','views');a=calc();const p=vm.runInContext('demPareto',ctx)(a.records);assert.ok(p.share>=80);assert.ok(p.count>=1);
const full=vm.runInContext('viewDemand()',ctx);
for(const label of ['Спрос','Сегодня','Вчера','7 дней','14 дней','30 дней','90 дней','Свой период','Органика','Продвижение','По стоимости','По площадям','Просмотры','Открытия номера','Доля открытий','Подробная таблица','На 100 просм.','Топ-'])assert.ok(full.includes(label),label);
assert.ok(!full.includes('Накоплено'));assert.ok(full.includes('dem-chart-row'));
let items=new Map();for(let i=0;i<36;i++)items.set(String(i),{id:String(i),a:ads.A,dv:i,dp:i});
let cards=vm.runInContext('demCards',ctx)({items});assert.equal((cards.match(/<article/g)||[]).length,30);assert.ok(cards.indexOf('35')<cards.indexOf('34'));
console.log(JSON.stringify({result:'PASS',tests:['all=paid+organic','exact grouping','price ranges','area ranges','opens','ratio threshold','Pareto','UI controls','top30'],totals:{v:42,p:8}}));
