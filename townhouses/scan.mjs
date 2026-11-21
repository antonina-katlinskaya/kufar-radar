import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const __dirname=path.dirname(fileURLToPath(import.meta.url));
const stateFile=path.join(__dirname,'state.json');
const csvFile=path.join(__dirname,'current.csv');
const BASE='https://bir.by/ajax/';
const project='Minsk World';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const text=s=>String(s??'').replace(/&nbsp;|&#160;/gi,' ').replace(/&amp;/gi,'&').replace(/<[^>]*>/g,' ').replace(/\s+/g,' ').trim();

export function extractRows(html) {
  const out=[];
  const ids=new Set();
  for(const m of html.matchAll(/<tr\b([^>]*\bdata-loadobject=["']([0-9a-f-]{36})["'][^>]*)>([\s\S]*?)<\/tr\s*>/gi)){
    const id=m[2].toLowerCase();
    if(ids.has(id))throw Error('Duplicate Bir ID in snapshot');
    ids.add(id);
    const raw=m[3];
    const links=[...raw.matchAll(/<a\b([^>]*?)>/gi)];
    const isHouse=links.some(x=>/\bhousename\b/i.test(x[1]) && /href\s*=\s*["'][^"']*\/townhouses\//i.test(x[1]));
    const cells=[...raw.matchAll(/<td\b[^>]*>([\s\S]*?)<\/td\s*>/gi)].map(x=>text(x[1]));
    if(!cells.length)throw Error('Malformed source table');
    if(!isHouse){out.push({id,townhouse:false});continue;}
    const unit=cells.find(x=>/^16\.\d{2}$/.test(x))||cells.find(x=>/^\d{1,2}\.\d{1,2}$/.test(x));
    if(!unit)throw Error('Townhouse number not found for '+id);
    const area=Number((cells.find(x=>/^2\d{2}[.,]\d{1,2}$/.test(x))||'').replace(',','.'));
    if(!Number.isFinite(area)||area<100)throw Error('Townhouse area not valid '+id);
    const euros=[...raw.matchAll(/class\s*=\s*["'][^"']*\btprice\b[^"']*["'][^>]*>([\s\S]*?)<\/span\s*>/gi)].map(x=>Number(text(x[1]).replace(/[^\d,\.]/g,'').replace(',','.'))).filter(Number.isFinite);
    out.push({id,townhouse:true,unit,area,priceFastEur:euros.at(-1)||null,url:'https://bir.by/object/'+id,source:'Bir search table'});
  }
  if(out.length!==ids.size)throw Error('Source IDs inconsistent');
  return out;
}

export function validatePairs(asc,desc,previous){
  if(asc.length<100||desc.length!==asc.length)throw Error('Bir source incomplete');
  const set=new Set(asc.map(x=>x.id));
  if(desc.some(x=>!set.has(x.id)))throw Error('Ascending/descending Bir source mismatch');
  const found=asc.filter(x=>x.townhouse);
  if(!found.length && Object.values(previous?.items||{}).some(x=>x.present))throw Error('Townhouse selector returned zero; avoid false removal');
  if(new Set(found.map(x=>x.id)).size!==found.length)throw Error('Duplicate townhouse');
  return found;
}

export function reconcile(previous,found,now){
  if(previous.version!==1||!previous.items||!Array.isArray(previous.outbox))throw Error('Invalid previous townhouse state');
  const next=structuredClone(previous),events=[];
  const active=new Set(found.map(x=>x.id));
  for(const row of found){
    const old=next.items[row.id];
    if(!old){
      next.items[row.id]={...row,present:true,missingChecks:0,firstSeen:now,lastSeen:now};
      events.push({key:'new|'+row.id,kind:'new',id:row.id,unit:row.unit,area:row.area,priceFastEur:row.priceFastEur,url:row.url,observedAt:now,status:'pending'});
    }else{
      if(!old.present)events.push({key:'returned|'+row.id+'|'+now,kind:'returned',id:row.id,unit:row.unit,area:row.area,priceFastEur:row.priceFastEur,url:row.url,observedAt:now,status:'pending'});
      next.items[row.id]={...old,...row,present:true,missingChecks:0,lastSeen:now};
    }
  }
  for(const [id,row] of Object.entries(next.items))if(!active.has(id)){
    const misses=(row.missingChecks||0)+1;
    next.items[id]={...row,missingChecks:misses,present:misses<2&&row.present};
  }
  for(const e of events)if(!next.outbox.some(x=>x.key===e.key))next.outbox.push(e);
  next.checkedAt=now;
  return {next,events};
}

export function csvRows(items){
  const quote=x=>'"'+String(x??'').replace(/"/g,'""')+'"';
  const rows=[['Тип объекта','Номер таунхауса','Площадь м²','Спеццена €','Статус в поиске Bir','ID Bir','Ссылка Bir','Дата последнего появления']];
  for(const a of Object.values(items).sort((a,b)=>a.unit.localeCompare(b.unit,'ru')))
    rows.push(['Таунхаусы',a.unit,a.area,a.priceFastEur??'',a.present?'В выдаче Bir':'Нет в выдаче Bir',a.id,a.url,a.lastSeen]);
  return rows.map(r=>r.map(quote).join(',')).join('\n')+'\n';
}

async function post(pathName,form){
  let reason;
  for(let attempt=1;attempt<=3;attempt++){
    try{
      const r=await fetch(BASE+pathName,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded','X-Requested-With':'XMLHttpRequest','Referer':'https://bir.by/search-by-parameters/','User-Agent':'Mozilla/5.0'},body:new URLSearchParams(form),signal:AbortSignal.timeout(25000)});
      if(r.ok)return await r.text();
      reason=Error('Bir HTTP '+r.status);
    }catch(e){reason=e;}
    if(attempt<3)await sleep(attempt*1500);
  }
  throw Error('Source not accessible after 3 attempts: '+String(reason?.message).slice(0,110));
}

async function main(){
  const previous=JSON.parse(fs.readFileSync(stateFile,'utf8'));
  const base={'object[]':project,orderby:'nomerPomeschenia',limit:'5000'};
  const [a,d]=await Promise.all([post('get-search-objects-in-building/',{...base,ascdesc:'ASC'}),post('get-search-objects-in-building/',{...base,ascdesc:'DESC'})]);
  let found; let source='in_building';
  try { found=validatePairs(extractRows(a),extractRows(d),previous); }
  catch(firstError) {
    const broad={type:'live','object[]':project,orderby:'cena',limit:'5000'};
    const [x,y]=await Promise.all([post('get-search-objects-new/',{...broad,ascdesc:'ASC'}),post('get-search-objects-new/',{...broad,ascdesc:'DESC'})]);
    try { found=validatePairs(extractRows(x),extractRows(y),previous); source='search_new'; }
    catch(secondError) { throw Error('Both Bir sources unverified: '+firstError.message+'; '+secondError.message); }
  }
  const now=new Date().toISOString();
  const {next,events}=reconcile(previous,found,now);
  // Reduce repository writes: only save when availability, identity or prices change.
  const snapshot=x=>Object.fromEntries(Object.entries(x).map(([k,v])=>[k,{present:v.present,missingChecks:v.missingChecks,unit:v.unit,area:v.area,priceFastEur:v.priceFastEur}]));
  const changed=JSON.stringify(snapshot(next.items))!==JSON.stringify(snapshot(previous.items))||events.length;
  if(changed){fs.writeFileSync(stateFile,JSON.stringify(next,null,2)+'\n');fs.writeFileSync(csvFile,csvRows(next.items));}
  console.log(JSON.stringify({ok:true,source,totalRows:extractRows(a).length,townhouses:found.length,new:events.filter(x=>x.kind==='new').length,returned:events.filter(x=>x.kind==='returned').length,changed,saved:changed,now}));
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))main().catch(e=>{console.error('TOWNHOUSE_WATCH_FAILED '+e.message);process.exitCode=1});
