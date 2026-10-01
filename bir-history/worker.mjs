const BASE = 'https://bir.by/ajax/';
const PROJECT = 'Minsk World';
const RESIDENTIAL = new Set(['Апартаменты', 'Квартира', 'Пентхаус']);
const DETAIL_LIMIT = 24;
const norm = s => String(s ?? '').replace(/&nbsp;|&#160;/gi, ' ').replace(/&amp;/gi, '&').replace(/&quot;/gi, '"').replace(/&#39;/gi, "'").replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();

async function bir(path, params) {
  const response = await fetch(BASE + path, {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded','X-Requested-With':'XMLHttpRequest','Referer':'https://bir.by/','User-Agent':'Mozilla/5.0'}, body:new URLSearchParams(params)});
  if (!response.ok) throw Error(`Bir ${path}: HTTP ${response.status}`);
  return response.text();
}

export function parseRows(html) {
  const rows = [];
  for (const row of html.matchAll(/<tr\b[^>]*data-loadobject="([0-9a-f-]{36})"[^>]*>[\s\S]*?<\/tr>/gi)) {
    const cells = [...row[0].matchAll(/<td\b[^>]*>([\s\S]*?)<\/td>/gi)].map(x => norm(x[1]));
    if (cells.length < 7 || !cells[1]) throw Error('Unexpected Bir row structure');
    rows.push({id:row[1],house:cells[1],number:cells[0],floor:cells[3],area:cells[5],rooms:cells[6],raw_cells_json:JSON.stringify(cells),raw_html:row[0]});
  }
  if (rows.length !== new Set(rows.map(x=>x.id)).size) throw Error('Duplicate Bir ID');
  return rows;
}

function listing(r, seen) {
  return {id:r.id,house:r.house,number:r.number,area:r.area,floor:r.floor,rooms:r.rooms,raw_cells_json:r.raw_cells_json,raw_html:r.raw_html,seen_utc:seen};
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
    const refresh=[];
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
        if(deltas.length || htmlChanged) refresh.push(r);
      }
    }
    for(const old of previous) if(!seen.has(old.id)) {
      const misses=old.missing_checks+1;
      writes.push(db.prepare('UPDATE bir_objects SET missing_checks=?,present=? WHERE id=?')
        .bind(misses,misses>=2?0:old.present,old.id));
      if(misses===2 && old.present) writes.push(event(db,old.id,now,scanId,'disappeared_from_listing'));
    }
    await batches(db,writes);
    // Refresh changed cards first, then the stalest details. All fields remain in detail_json.
    const refreshIds=new Set(refresh.map(x=>x.id));
    const periodic=previous.filter(x=>seen.has(x.id)&&!refreshIds.has(x.id))
      .sort((a,b)=>String(a.detail_fetched_at??'').localeCompare(String(b.detail_fetched_at??'')) ||
        Number(JSON.parse(a.listing_json).area)-Number(JSON.parse(b.listing_json).area));
    const targets=[...refresh,...periodic.map(x=>({id:x.id}))].slice(0,DETAIL_LIMIT);
    let details=0,detailErrors=0;
    for(const r of targets) {
      const old=byId.get(r.id);
      try {
        const before=old?.detail_json?JSON.parse(old.detail_json):null;
        const detail=parseDetail(await bir('get-object-by-tablerow-click/',{objectid:r.id}),r.id,before);
        if(!RESIDENTIAL.has(detail.vid)) throw Error('Previously residential ID now has non-residential type');
        const updates=[db.prepare('UPDATE bir_objects SET detail_json=?,detail_fetched_at=? WHERE id=?').bind(JSON.stringify(detail),now,r.id)];
        if(before) for(const key of new Set([...Object.keys(before),...Object.keys(detail)])) {
          if(key==='image'||key==='image_metadata') continue;
          if(JSON.stringify(before[key]??null)!==JSON.stringify(detail[key]??null))
            updates.push(event(db,r.id,now,scanId,'detail_changed',key,JSON.stringify(before[key]??null),JSON.stringify(detail[key]??null)));
        }
        await batches(db,updates); details++;
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

