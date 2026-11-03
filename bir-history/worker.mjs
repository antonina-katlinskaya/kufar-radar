const BASE = 'https://bir.by/ajax/';
const PROJECT = 'Minsk World';
const RESIDENTIAL = new Set(['Апартаменты', 'Квартира', 'Пентхаус']);
const DETAIL_LIMIT = 24;
const norm = s => String(s ?? '').replace(/&nbsp;|&#160;/gi, ' ').replace(/&amp;/gi, '&').replace(/&quot;/gi, '"').replace(/&#39;/gi, "'").replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();

const BIR_REQUEST_TIMEOUT_MS = 15000;
const BIR_REQUEST_ATTEMPTS = 3;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function bir(path, params) {
  let lastError;
  for (let attempt = 1; attempt <= BIR_REQUEST_ATTEMPTS; attempt++) {
    try {
      const response = await fetch(BASE + path, {
        method:'POST',
        headers:{
          'Content-Type':'application/x-www-form-urlencoded',
          'X-Requested-With':'XMLHttpRequest',
          'Referer':'https://bir.by/',
          'User-Agent':'Mozilla/5.0'
        },
        body:new URLSearchParams(params),
        signal:AbortSignal.timeout(BIR_REQUEST_TIMEOUT_MS)
      });
      if (response.ok) return response.text();
      const error = Error(`Bir ${path}: HTTP ${response.status}`);
      if (response.status < 500 && response.status !== 429) throw error;
      lastError = error;
    } catch (error) {
      lastError = error;
      if (attempt === BIR_REQUEST_ATTEMPTS) break;
    }
    await sleep(attempt * 1000);
  }
  throw lastError ?? Error(`Bir ${path}: request failed`);
}

export function parseRows(html) {
  const rows = [];
  for (const row of html.matchAll(/<tr\b[^>]*data-loadobject="([0-9a-f-]{36})"[^>]*>[\s\S]*?<\/tr>/gi)) {
    const cells = [...row[0].matchAll(/<td\b[^>]*>([\s\S]*?)<\/td>/gi)].map(x => norm(x[1]));
    if (cells.length < 7 || !cells[1]) throw Error('Unexpected Bir row structure');
    const prices_eur=[...row[0].matchAll(/<span\b[^>]*\btprice\b[^>]*>([\s\S]*?)<\/span>/gi)]
      .map(x=>Number(norm(x[1]).replace(/[^0-9.,]/g,'').replace(',','.')));
    if(!prices_eur.length || prices_eur.some(x=>!Number.isFinite(x))) throw Error('Cannot verify Bir EUR prices');
    rows.push({id:row[1],house:cells[1],number:cells[0],floor:cells[3],area:cells[5],rooms:cells[6],prices_eur,raw_cells_json:JSON.stringify(cells),raw_html:row[0]});
  }
  if (rows.length !== new Set(rows.map(x=>x.id)).size) throw Error('Duplicate Bir ID');
  return rows;
}

function listing(r, seen) {
  return {id:r.id,house:r.house,number:r.number,area:r.area,floor:r.floor,rooms:r.rooms,prices_eur:r.prices_eur,raw_cells_json:r.raw_cells_json,raw_html:r.raw_html,seen_utc:seen};
}

export function parseDetail(raw, id, oldDetail) {
  const d=JSON.parse(raw);
  if (!d || d.id !== id || d.object !== PROJECT) throw Error('Wrong ID or project in Bir detail');
  const image=d.image;
  if (typeof image === 'string') {
    d.image_metadata={present:image.startsWith('data:'),encoded_characters:image.length};
    if (oldDetail?.image && typeof oldDetail.image === 'object') d.image=oldDetail.image;
    else delete d.image;
  }
  return d;
}

function event(db, id, now, scanId, type, field=null, oldValue=null, newValue=null) {
  return db.prepare('INSERT INTO bir_events(object_id,observed_at,event_type,field,old_value,new_value,scan_id) VALUES(?,?,?,?,?,?,?)')
    .bind(id,now,type,field,oldValue,newValue,scanId);
}
async function batches(db, statements) {
  for(let i=0;i<statements.length;i+=40) await db.batch(statements.slice(i,i+40));
}

// Always advance the oldest-card queue. Listing HTML (including BYN and
// presentation-only changes) must never restart the queue at the first 24 IDs.
export function detailTargets(previous, seen, limit=DETAIL_LIMIT) {
  return previous.filter(x=>seen.has(x.id))
    .sort((a,b)=>String(a.detail_fetched_at??'').localeCompare(String(b.detail_fetched_at??'')) || a.id.localeCompare(b.id))
    .slice(0,limit);
}

async function refreshDetail(db, old, now, scanId) {
  const before=old.detail_json?JSON.parse(old.detail_json):null;
  const detail=parseDetail(await bir('get-object-by-tablerow-click/',{objectid:old.id}),old.id,before);
  if(!RESIDENTIAL.has(detail.vid)) throw Error('Previously residential ID now has non-residential type');
  const updates=[db.prepare('UPDATE bir_objects SET detail_json=?,detail_fetched_at=? WHERE id=? AND (detail_fetched_at IS NULL OR detail_fetched_at<=?)')
    .bind(JSON.stringify(detail),now,old.id,now)];
  if(before) for(const key of new Set([...Object.keys(before),...Object.keys(detail)])) {
    if(key==='image'||key==='image_metadata') continue;
    if(JSON.stringify(before[key]??null)!==JSON.stringify(detail[key]??null))
      updates.push(event(db,old.id,now,scanId,'detail_changed',key,JSON.stringify(before[key]??null),JSON.stringify(detail[key]??null)));
  }
  await batches(db,updates);
}

// Runs in GitHub Actions, outside the Workers free-plan subrequest budget.
// Every active card is fetched; failed requests leave the previous record and
// timestamp untouched and fail the job, rather than reporting a successful sweep.
export async function refreshAllDetails(env) {
  const db=env.BIR_DB, startedAt=new Date().toISOString(), scanId=crypto.randomUUID();
  const rows=(await db.prepare('SELECT * FROM bir_objects WHERE present=1').all()).results;
  let cursor=0, details=0; const errors=[];
  await db.prepare('INSERT OR REPLACE INTO service_state(key,value,updated_at) VALUES(?,?,?)')
    .bind('bir_detail_refresh',JSON.stringify({status:'running',startedAt,total:rows.length}),startedAt).run();
  await Promise.all(Array.from({length:4},async()=>{
    while(cursor<rows.length) {
      const old=rows[cursor++];
      try { await refreshDetail(db,old,new Date().toISOString(),scanId); details++; }
      catch(error) {
        // Stop issuing requests on a quota failure. Other errors are retried by
        // the next oldest-first scan, and remain visible in the failed job.
        errors.push({id:old.id,error:String(error)});
        if(/quota|daily.*limit|free tier/i.test(String(error))) cursor=rows.length;
      }
      if(details && details%100===0) console.log(JSON.stringify({detailProgress:details,total:rows.length}));
    }
  }));
  const result={ok:details===rows.length&&errors.length===0,scanId,startedAt,finishedAt:new Date().toISOString(),total:rows.length,details,errors};
  await db.prepare('INSERT OR REPLACE INTO service_state(key,value,updated_at) VALUES(?,?,?)')
    .bind('bir_detail_refresh',JSON.stringify({...result,status:result.ok?'ok':'failed'}),result.finishedAt).run();
  return result;
}

export async function scan(env) {
  if (!env.BIR_DB) throw Error('BIR_DB binding missing');
  const db=env.BIR_DB, now=new Date().toISOString(), scanId=crypto.randomUUID();
  let count=null, parsed=0;
  const log=async(status,error=null)=>db.prepare('INSERT INTO bir_scans(scan_id,house,checked_at,source_count,parsed_count,status,error) VALUES(?,?,?,?,?,?,?)')
    .bind(scanId,PROJECT,now,count,parsed,status,error).run();
  try {
    const form={'object[]':PROJECT};
    const [counter,html,reverseHtml]=await Promise.all([
      bir('get-number-of-objects-for-pc/',form),
      bir('get-search-objects-in-building/',{...form,orderby:'nomerPomeschenia',ascdesc:'ASC',limit:'5000'}),
      bir('get-search-objects-in-building/',{...form,orderby:'nomerPomeschenia',ascdesc:'DESC',limit:'5000'})
    ]);
    count=Number(counter.trim());
    const rows=parseRows(html); parsed=rows.length;
    const reverse=parseRows(reverseHtml);
    const ids=new Set(rows.map(r=>r.id));
    if (!Number.isInteger(count) || count<parsed || !parsed || parsed>5000 ||
        parsed!==reverse.length || reverse.some(r=>!ids.has(r.id)))
      throw Error(`Incomplete Bir table: counter=${count}, asc=${parsed}, desc=${reverse.length}`);
    const previous=(await db.prepare('SELECT * FROM bir_objects').all()).results;
    const byId=new Map(previous.map(x=>[x.id,x]));
    const excluded=new Set((await db.prepare('SELECT id FROM bir_excluded').all()).results.map(x=>x.id));
    const active=previous.filter(x=>x.present).length;
    if(parsed < active * 0.9) throw Error(`Suspicious drop: rows=${parsed}, active=${active}`);
    const seen=new Set();
    const writes=[];let appeared=0, changed=0, excludedNew=0;
    for(const r of rows) {
      if(excluded.has(r.id)) continue;
      const old=byId.get(r.id);
      if(!old) {
        // New houses are accepted; only the detail card can confirm the project and property type.
        const detail=parseDetail(await bir('get-object-by-tablerow-click/',{objectid:r.id}),r.id,null);
        if(!RESIDENTIAL.has(detail.vid)) {
          writes.push(db.prepare('INSERT OR IGNORE INTO bir_excluded(id,project,type,first_seen) VALUES(?,?,?,?)').bind(r.id,detail.object,String(detail.vid??''),now));
          excludedNew++;
          continue;
        }
        writes.push(db.prepare('INSERT INTO bir_objects(id,house,listing_json,detail_json,first_seen,last_seen,present,missing_checks,detail_fetched_at) VALUES(?,?,?,?,?,?,1,0,?)')
          .bind(r.id,r.house,JSON.stringify(listing(r,now)),JSON.stringify(detail),now,now,now));
        writes.push(event(db,r.id,now,scanId,'appeared')); appeared++;
        seen.add(r.id);
        continue;
      }
      seen.add(r.id);
      const before=JSON.parse(old.listing_json), after=listing(r,before.seen_utc);
      const fields=['house','number','area','floor','rooms','raw_cells_json'];
      const deltas=fields.filter(k=>String(before[k]??'')!==String(after[k]??''));
      const htmlChanged=before.raw_html!==r.raw_html;
      if(deltas.length || htmlChanged || !old.present || old.missing_checks) {
        after.seen_utc=now;
        writes.push(db.prepare('UPDATE bir_objects SET house=?,listing_json=?,last_seen=?,present=1,missing_checks=0 WHERE id=?')
          .bind(r.house,JSON.stringify(after),now,r.id));
        for(const k of deltas) writes.push(event(db,r.id,now,scanId,'field_changed',k,JSON.stringify(before[k]??null),JSON.stringify(after[k]??null)));
        if(!deltas.length && htmlChanged) writes.push(event(db,r.id,now,scanId,'listing_changed','raw_html'));
        if(!old.present) writes.push(event(db,r.id,now,scanId,'returned'));
        changed++;
      }
    }
    for(const old of previous) if(!seen.has(old.id)) {
      const misses=old.missing_checks+1;
      writes.push(db.prepare('UPDATE bir_objects SET missing_checks=?,present=? WHERE id=?')
        .bind(misses,misses>=2?0:old.present,old.id));
      if(misses===2 && old.present) writes.push(event(db,old.id,now,scanId,'disappeared_from_listing'));
    }
    await batches(db,writes);
    const targets=detailTargets(previous,seen);
    let details=0,detailErrors=0;
    for(const r of targets) {
      const old=byId.get(r.id);
      try {
        await refreshDetail(db,old,now,scanId); details++;
      } catch(_) { detailErrors++; }
    }
    await log('ok',detailErrors?`Detail retries needed: ${detailErrors}`:null);
    return {ok:true,scanId,sourceCount:count,parsed,appeared,changed,excludedNew,details,detailErrors};
  } catch(e) {
    await log('rejected',String(e));
    throw e;
  }
}

export default {
  async fetch(request,env) {
    const path=new URL(request.url).pathname;
    if(path==='/health') return Response.json({ok:true,service:'bir-history-residential',project:PROJECT});
    if(path!=='/scan'||request.method!=='POST') return new Response('Not found',{status:404});
    if(!env.BIR_SCAN_TOKEN||request.headers.get('authorization')!==`Bearer ${env.BIR_SCAN_TOKEN}`) return new Response('Unauthorized',{status:401});
    try{return Response.json(await scan(env));}catch(e){return Response.json({ok:false,error:String(e)},{status:503});}
  },
  async scheduled(_event,env,ctx) {ctx.waitUntil(scan(env));}
};
