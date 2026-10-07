const API='https://cre-api.kufar.by/ads-search/v1/engine/v2/search/rendered-paginated';
const MARKET_PAGES=3;
const HOUSE_ADDRESS={
 'Дом 4.2':'Николы Теслы ул, 33, Минск','Дом 11.1':'Игоря Лученка ул, 18, Минск','Дом 11.2':'Игоря Лученка ул, 22, Минск',
 'Дом 11.5':'Михаила Савицкого ул, 25, Минск','Дом 16.39':'Михаила Савицкого ул, 24, Минск','Дом 18.1':'Белградская ул, 1, Минск',
 'Дом 21.1':'Брилевская ул, 54, Минск','Дом 22.7':'проспект Мира, 8, Минск',
 'Дом 24.2.1':'площадь Старый Аэропорт, 2, Минск','Дом 24.2.2':'площадь Старый Аэропорт, 2, Минск',
 'Дом 24.2.3':'площадь Старый Аэропорт, 2, Минск','Дом 24.2.4':'площадь Старый Аэропорт, 2, Минск',
 'Дом 24.2.5':'площадь Старый Аэропорт, 2, Минск','Дом 27.5':'Леонида Левина ул, 3, Минск',
 'Дом 27.6':'Игоря Лученка ул, 4, Минск','Дом 27.11.1':'Михаила Савицкого ул, 9, Минск'
};
function param(rows,key) {const p=(rows||[]).find(x=>x?.p===key);return Array.isArray(p?.v)?p.v[0]:p?.v??null;}
function label(rows,key) {const p=(rows||[]).find(x=>x?.p===key);return Array.isArray(p?.vl)?p.vl[0]:p?.vl??null;}
function num(v) {const n=Number(v);return v==null||v===''||!Number.isFinite(n)?null:n;}
function price(ad,currency) {const p=(ad.calculator||[]).find(x=>x.currency===currency);return p?.price!=null?Number(p.price)/100:null;}
function claimed(ad) {const p=ad.ad_parameters||[];const s=[label(p,'re_district'),label(p,'new_buildings_apartment_complex'),ad.subject].join(' ').toLowerCase();return /минск[ -]мир|minsk world/.test(s);}
function parsed(ad,profile) {const p=ad.ad_parameters||[],account=ad.account_parameters||[];return {id:String(ad.ad_id),profile,price_eur:price(ad,'EUR'),price_byn:price(ad,'BYN'),area:num(param(p,'size')),rooms:num(param(p,'rooms')),floor:num(param(p,'floor')),address:param(account,'address'),title:ad.subject||null,url:ad.ad_link||`https://re.kufar.by/vi/${ad.ad_id}`,list_time:ad.list_time||null,raw_json:JSON.stringify(ad)};}
async function fetchPage(profile,cursor) {const u=new URL(API);for(const [k,v] of Object.entries({atid:profile,lang:'ru',size:'45',typ:'sell',prn:'1000',sort:'lst.d'}))u.searchParams.set(k,v);if(cursor)u.searchParams.set('cursor',cursor);const r=await fetch(u.toString(),{headers:{'User-Agent':'Mozilla/5.0'}});if(!r.ok)throw Error(`Kufar ${profile}: HTTP ${r.status}`);const d=await r.json();if(!Array.isArray(d.ads))throw Error('Kufar ads missing');const next=(d.pagination?.pages||[]).find(x=>x.label==='next')?.token||null;return {ads:d.ads,next,total:Number(d.total)||null};}
async function fetchMarket(cursor) {const u=new URL(API);for(const [k,v] of Object.entries({cat:'1010',red:'170',cmp:'1',lang:'ru',size:'45',typ:'sell',sort:'lst.d'}))u.searchParams.set(k,v);if(cursor)u.searchParams.set('cursor',cursor);const r=await fetch(u.toString(),{headers:{'User-Agent':'Mozilla/5.0'}});if(!r.ok)throw Error(`Kufar market: HTTP ${r.status}`);const d=await r.json();if(!Array.isArray(d.ads))throw Error('Kufar market ads missing');return {ads:d.ads,next:(d.pagination?.pages||[]).find(x=>x.label==='next')?.token||null,total:Number(d.total)||null};}
async function batches(db,statements) {for(let i=0;i<statements.length;i+=35)await db.batch(statements.slice(i,i+35));}
async function ensureSchema(db) {
 await db.prepare("CREATE TABLE IF NOT EXISTS kufar_bridge_seen_state(profile_id TEXT PRIMARY KEY,seen_ids_json TEXT NOT NULL,pending_missing_json TEXT NOT NULL)").run();
}
function event(db,id,now,scanId,type,field=null,oldValue=null,newValue=null) {return db.prepare('INSERT INTO kufar_bridge_events(ad_id,observed_at,event_type,field,old_value,new_value,scan_id) VALUES(?,?,?,?,?,?,?)').bind(id,now,type,field,oldValue,newValue,scanId);}
const addressTokens=s=>String(s||'').toLowerCase().replaceAll('ё','е').match(/[а-яa-z0-9]+/g)?.filter(x=>!['минск','ул','улица','дом','д','площадь','пл','проспект','пр'].includes(x))||[];
function addressMatch(a,b) {const aa=addressTokens(a),bb=addressTokens(b),nums=new Set(aa.filter(x=>/\d/.test(x)));return !!(nums.size && bb.some(x=>nums.has(x)) && aa.some(x=>bb.includes(x)&&!/\d/.test(x)));}
async function propose(db,r,now) {
 if(r.area==null||r.rooms==null||r.floor==null)return;
 const query=await db.prepare("SELECT id,house,CAST(json_extract(detail_json,'$.obschPloschad') AS REAL) AS area FROM bir_objects WHERE present=1 AND json_extract(detail_json,'$.comnat')=? AND json_extract(detail_json,'$.etaj')=? AND CAST(json_extract(detail_json,'$.obschPloschad') AS REAL) BETWEEN ? AND ?").bind(r.rooms,r.floor,r.area-0.11,r.area+0.11).all();
 const candidates=query.results.filter(x=>Number(x.area)===r.area || Math.round((Number(x.area)+1e-9)*10)/10===r.area);
 const addressed=candidates.filter(x=>addressMatch(r.address,HOUSE_ADDRESS[x.house]));
 let level='NO_MATCH',selected=null;
 if(addressed.length===1){level='ADDRESS_UNIQUE';selected=addressed[0];}
 else if(addressed.length>1)level='AMBIGUOUS_ADDRESS';
 else if(candidates.length===1){level='UNIQUE_NO_ADDRESS';selected=candidates[0];}
 else if(candidates.length>1)level='AMBIGUOUS';
 await db.prepare('INSERT INTO kufar_match_proposals(ad_id,proposed_bir_id,level,candidate_count,address_count,area,rooms,floor,address,computed_at) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(ad_id) DO UPDATE SET proposed_bir_id=excluded.proposed_bir_id,level=excluded.level,candidate_count=excluded.candidate_count,address_count=excluded.address_count,area=excluded.area,rooms=excluded.rooms,floor=excluded.floor,address=excluded.address,computed_at=excluded.computed_at')
 .bind(r.id,selected?.id||null,level,candidates.length,addressed.length,r.area,r.rooms,r.floor,r.address||null,now).run();
}
async function scanProfile(env,profile) {
 const db=env.BIR_DB,now=new Date().toISOString(),scanId=crypto.randomUUID();
 let total=null,seen=0,mw=0;
 const log=async(status,error=null)=>db.prepare('INSERT INTO kufar_import_scans(scan_id,observed_at,profile_id,api_total,seen_total,mw_total,status,error) VALUES(?,?,?,?,?,?,?,?)').bind(scanId,now,profile,total,seen,mw,status,error).run();
 try {
  const state=(await db.prepare('SELECT cursor,page_number FROM kufar_bridge_state WHERE profile_id=?').bind(profile).first())||{cursor:null,page_number:1};
  const cycleState=await db.prepare('SELECT seen_ids_json,pending_missing_json FROM kufar_bridge_seen_state WHERE profile_id=?').bind(profile).first();
  const seenIds=new Set(state.cursor?JSON.parse(cycleState?.seen_ids_json||'[]'):[]);
  const pendingMissing=new Set(JSON.parse(cycleState?.pending_missing_json||'[]'));
  const newest=await fetchPage(profile,null);total=newest.total;
  let cursor=state.cursor||newest.next,page=state.cursor?state.page_number:2;
  const all=new Map(newest.ads.map(ad=>[String(ad.ad_id),ad]));seen+=newest.ads.length;
  for(let i=0;i<2&&cursor;i++) {const d=await fetchPage(profile,cursor);seen+=d.ads.length;for(const ad of d.ads)all.set(String(ad.ad_id),ad);cursor=d.next;page++;}
  const accountId=newest.ads[0]?.account_id;
  if(accountId)await db.prepare('UPDATE kufar_profiles SET account_id=?,last_seen=? WHERE profile_id=? AND (account_id IS NULL OR account_id=?)').bind(accountId,now,profile,accountId).run();
  const rows=[...all.values()].filter(claimed).map(ad=>parsed(ad,profile));mw=rows.length;
  for(const r of rows)seenIds.add(r.id);
  const ids=rows.map(x=>x.id);const previous=new Map();
  for(let i=0;i<ids.length;i+=100){const part=ids.slice(i,i+100);const q=await db.prepare(`SELECT ad_id,price_eur,price_byn,area,rooms,floor,address,title,present FROM kufar_ads_live WHERE ad_id IN (${part.map(()=>'?').join(',')})`).bind(...part).all();for(const x of q.results)previous.set(x.ad_id,x);}
  const writes=[],proposalRows=[];let added=0,changed=0;
  for(const r of rows){const old=previous.get(r.id),fields=['price_eur','price_byn','area','rooms','floor','address','title'];
   if(!old){writes.push(db.prepare('INSERT INTO kufar_ads_live(ad_id,profile_id,observed_at,list_time,price_eur,price_byn,area,rooms,floor,address,title,url,raw_json,first_seen,last_seen,present) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)').bind(r.id,profile,now,r.list_time,r.price_eur,r.price_byn,r.area,r.rooms,r.floor,r.address,r.title,r.url,r.raw_json,now,now));writes.push(event(db,r.id,now,scanId,'appeared'));proposalRows.push(r);added++;}
   else {const diffs=fields.filter(k=>String(old[k]??'')!==String(r[k]??''));const returned=!old.present;
    if(diffs.length||returned){writes.push(db.prepare('UPDATE kufar_ads_live SET observed_at=?,last_seen=?,price_eur=?,price_byn=?,area=?,rooms=?,floor=?,address=?,title=?,url=?,raw_json=?,present=1 WHERE ad_id=?').bind(now,now,r.price_eur,r.price_byn,r.area,r.rooms,r.floor,r.address,r.title,r.url,r.raw_json,r.id));for(const k of diffs)writes.push(event(db,r.id,now,scanId,'field_changed',k,JSON.stringify(old[k]??null),JSON.stringify(r[k]??null)));if(returned)writes.push(event(db,r.id,now,scanId,'returned'));if(returned||diffs.some(k=>['area','rooms','floor','address'].includes(k)))proposalRows.push(r);changed++;}
    /* Unchanged ads are already in the snapshot; avoid one D1 write per ad per scan. */}
  }
  let nextPending=[...pendingMissing];
  if(!cursor){const missing=(await db.prepare('SELECT ad_id FROM kufar_ads_live WHERE profile_id=? AND present=1').bind(profile).all()).results.filter(x=>!seenIds.has(x.ad_id));nextPending=missing.map(x=>x.ad_id);for(const x of missing){if(!pendingMissing.has(x.ad_id))continue;writes.push(db.prepare('UPDATE kufar_ads_live SET present=0 WHERE ad_id=?').bind(x.ad_id));writes.push(event(db,x.ad_id,now,scanId,'disappeared'));}}
  await batches(db,writes);
  for(const r of proposalRows)await propose(db,r,now);
  await db.prepare('INSERT INTO kufar_bridge_state(profile_id,cursor,page_number,last_cycle_at,last_success_at) VALUES(?,?,?,?,?) ON CONFLICT(profile_id) DO UPDATE SET cursor=excluded.cursor,page_number=excluded.page_number,last_cycle_at=COALESCE(excluded.last_cycle_at,kufar_bridge_state.last_cycle_at),last_success_at=excluded.last_success_at')
   .bind(profile,cursor,page,cursor?null:now,now).run();
  await db.prepare('INSERT INTO kufar_bridge_seen_state(profile_id,seen_ids_json,pending_missing_json) VALUES(?,?,?) ON CONFLICT(profile_id) DO UPDATE SET seen_ids_json=excluded.seen_ids_json,pending_missing_json=excluded.pending_missing_json')
   .bind(profile,JSON.stringify(cursor?[...seenIds]:[]),JSON.stringify(nextPending)).run();
  await log('ok');return {profile,apiTotal:total,fetched:seen,mw,added,changed,nextPage:page};
 }catch(e){await log('rejected',String(e));throw e;}
}
async function marketAccounts(db, ads) {
 const ids=[...new Set([...ads.values()].map(ad=>ad.account_id).filter(id=>id!=null))];
 const accounts=new Map();
 for(let i=0;i<ids.length;i+=100) {
  const page=ids.slice(i,i+100);
  const rows=(await db.prepare(`SELECT profile_id,account_id FROM kufar_profiles WHERE account_id IN (${page.map(()=>'?').join(',')})`).bind(...page).all()).results;
  for(const row of rows) accounts.set(row.account_id,row.profile_id);
 }
 return accounts;
}
async function scanMarket(env) {
 const db=env.BIR_DB,now=new Date().toISOString(),scanId=crypto.randomUUID();let cursor=null,total=null,seen=0,mw=0,added=0,changed=0;
 try {
  const state=(await db.prepare("SELECT cursor,page_number FROM kufar_bridge_state WHERE profile_id='market'").first())||{cursor:null,page_number:MARKET_PAGES+1};
  const ads=new Map();for(let i=0;i<MARKET_PAGES;i++){const p=await fetchMarket(cursor);total=p.total;seen+=p.ads.length;for(const ad of p.ads)if(ad.company_ad&&claimed(ad))ads.set(String(ad.ad_id),ad);cursor=p.next;if(!cursor)break;}
  let deepCursor=state.cursor||cursor,deepPage=state.cursor?state.page_number:MARKET_PAGES+1;
  for(let i=0;i<MARKET_PAGES&&deepCursor;i++){const p=await fetchMarket(deepCursor);seen+=p.ads.length;for(const ad of p.ads)if(ad.company_ad&&claimed(ad))ads.set(String(ad.ad_id),ad);deepCursor=p.next;deepPage++;}
  mw=ads.size;const accounts=await marketAccounts(db,ads);
  const ids=[...ads.keys()],prior=new Map();for(let i=0;i<ids.length;i+=100){const q=await db.prepare(`SELECT ad_id,price_eur,price_byn,area,rooms,floor,address,title FROM kufar_ads_live WHERE ad_id IN (${ids.slice(i,i+100).map(()=>'?').join(',')})`).bind(...ids.slice(i,i+100)).all();for(const x of q.results)prior.set(x.ad_id,x);}
  const writes=[],proposals=[],newProfiles=new Map();
  for(const ad of ads.values()){const account=ad.account_id,profile=accounts.get(account)||`account:${account}`,r=parsed(ad,profile),old=prior.get(r.id);if(!accounts.has(account))newProfiles.set(account,ad);
   if(!old){writes.push(db.prepare('INSERT INTO kufar_ads_live(ad_id,profile_id,observed_at,list_time,price_eur,price_byn,area,rooms,floor,address,title,url,raw_json,first_seen,last_seen,present) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)').bind(r.id,profile,now,r.list_time,r.price_eur,r.price_byn,r.area,r.rooms,r.floor,r.address,r.title,r.url,r.raw_json,now,now));writes.push(event(db,r.id,now,scanId,'appeared'));proposals.push(r);added++;}
   else {const diffs=['price_eur','price_byn','area','rooms','floor','address','title'].filter(k=>String(old[k]??'')!==String(r[k]??''));if(diffs.length){writes.push(db.prepare('UPDATE kufar_ads_live SET observed_at=?,last_seen=?,price_eur=?,price_byn=?,area=?,rooms=?,floor=?,address=?,title=?,url=?,raw_json=?,present=1 WHERE ad_id=?').bind(now,now,r.price_eur,r.price_byn,r.area,r.rooms,r.floor,r.address,r.title,r.url,r.raw_json,r.id));for(const k of diffs)writes.push(event(db,r.id,now,scanId,'field_changed',k,JSON.stringify(old[k]??null),JSON.stringify(r[k]??null)));if(diffs.some(k=>['area','rooms','floor','address'].includes(k)))proposals.push(r);changed++;}}
  }
  for(const [account,ad] of newProfiles){const p=ad.account_parameters||[];await db.prepare('INSERT OR IGNORE INTO kufar_profiles(profile_id,account_id,company,contact_names,source,enabled,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?)').bind(`account:${account}`,account,param(p,'name'),param(p,'contact_person'),'market_discovery',1,now,now).run();}
  await batches(db,writes);for(const r of proposals)await propose(db,r,now);
  await db.prepare("INSERT INTO kufar_bridge_state(profile_id,cursor,page_number,last_cycle_at,last_success_at) VALUES('market',?,?,?,?) ON CONFLICT(profile_id) DO UPDATE SET cursor=excluded.cursor,page_number=excluded.page_number,last_cycle_at=excluded.last_cycle_at,last_success_at=excluded.last_success_at").bind(deepCursor,deepPage,deepCursor?null:now,now).run();
  await db.prepare('INSERT INTO kufar_import_scans(scan_id,observed_at,profile_id,api_total,seen_total,mw_total,status,error) VALUES(?,?,?,?,?,?,?,NULL)').bind(scanId,now,'market',total,seen,mw,'ok').run();
  return {apiTotal:total,fetched:seen,mw,added,changed,discoveredProfiles:newProfiles.size,nextPage:deepPage};
 }catch(e){await db.prepare('INSERT INTO kufar_import_scans(scan_id,observed_at,profile_id,api_total,seen_total,mw_total,status,error) VALUES(?,?,?,?,?,?,?,?)').bind(scanId,now,'market',total,seen,mw,'rejected',String(e)).run();throw e;}
}
export async function scan(env,group=null,priorityProfiles=[]) {if(!env.BIR_DB)throw Error('BIR_DB missing');await ensureSchema(env.BIR_DB);const profiles=(await env.BIR_DB.prepare("SELECT profile_id FROM kufar_profiles WHERE enabled=1 AND source='v7_census' ORDER BY profile_id").all()).results.map(x=>x.profile_id);const resolvedGroup=group??Math.floor(new Date().getUTCMinutes()/15)%2;const priority=new Set((priorityProfiles||[]).map(String));const selected=profiles.filter((profile,i)=>i%2===resolvedGroup||priority.has(profile));const results=[];for(const profile of selected)results.push(await scanProfile(env,profile));return {ok:true,group:resolvedGroup,profilesTotal:profiles.length,selectedProfiles:selected.length,priorityProfiles:[...priority],results,market:await scanMarket(env)};}
export default {async fetch(request,env){const u=new URL(request.url),path=u.pathname;if(path==='/health')return Response.json({ok:true,service:'kufar-bir-bridge',profileCoverage:'v7-census-plus-market'});if(path!=='/scan'||request.method!=='POST')return new Response('Not found',{status:404});if(!env.BRIDGE_SCAN_TOKEN||request.headers.get('authorization')!==`Bearer ${env.BRIDGE_SCAN_TOKEN}`)return new Response('Unauthorized',{status:401});try{const g=u.searchParams.get('group');return Response.json(await scan(env,g==='0'||g==='1'?Number(g):null));}catch(e){return Response.json({ok:false,error:String(e)},{status:503});}},async scheduled(_event,env,ctx){ctx.waitUntil(scan(env));}};
