// Read-only validation against current Cloudflare D1 inventory.
// Does not write inventory, scan logs, state or Telegram.
import {parseRows,parseDetail} from '../bir-history/worker.mjs';
const host='https://birby.by';
async function post(path,params){
  const r=await fetch(host+'/ajax/'+path,{method:'POST',headers:{
    'Content-Type':'application/x-www-form-urlencoded','X-Requested-With':'XMLHttpRequest',
    'Referer':host+'/','User-Agent':'Mozilla/5.0'},body:new URLSearchParams(params),
    signal:AbortSignal.timeout(25000)});
  if(!r.ok||!r.url.startsWith(host+'/ajax/'))throw Error('Bad endpoint status or redirect: '+r.status+' '+r.url);
  return r.text();
}
const form={'object[]':'Minsk World'};
const [raw,reverseRaw]=await Promise.all([
  post('get-search-objects-in-building/',{...form,orderby:'nomerPomeschenia',ascdesc:'ASC',limit:'5000'}),
  post('get-search-objects-in-building/',{...form,orderby:'nomerPomeschenia',ascdesc:'DESC',limit:'5000'})]);
const rows=parseRows(raw),reverse=parseRows(reverseRaw);
const ids=new Set(rows.map(x=>x.id));
if(rows.length===0||reverse.length!==rows.length||reverse.some(x=>!ids.has(x.id)))throw Error('Asymmetric Bir data');
console.log(JSON.stringify({phase:'parse',rows:rows.length,reverse:reverse.length,distinctIds:ids.size}));
for(const r of rows.slice(0,3)){
  const detail=parseDetail(await post('get-object-by-tablerow-click/',{objectid:r.id}),r.id,null);
  console.log(JSON.stringify({phase:'detail',id:r.id,project:detail.object,type:detail.vid}));
}
const {CF_ACCOUNT_ID,BIR_D1_DATABASE_ID,CF_D1_API_TOKEN}=process.env;
if(!CF_ACCOUNT_ID||!BIR_D1_DATABASE_ID||!CF_D1_API_TOKEN) throw Error('Missing read-only D1 query credentials');
const url='https://api.cloudflare.com/client/v4/accounts/'+encodeURIComponent(CF_ACCOUNT_ID)+'/d1/database/'+encodeURIComponent(BIR_D1_DATABASE_ID)+'/query';
const response=await fetch(url,{method:'POST',headers:{Authorization:'Bearer '+CF_D1_API_TOKEN,'Content-Type':'application/json'},body:JSON.stringify({sql:'SELECT id FROM bir_objects WHERE present=1'})});
const data=await response.json();
if(!response.ok||!data.success||!data.result?.[0]?.success)throw Error('Read-only D1 query failed: HTTP '+response.status);
const previous=data.result[0].results.map(x=>x.id);
const shared=previous.filter(id=>ids.has(id)).length;
const ratio=previous.length?shared/previous.length:0;
console.log(JSON.stringify({phase:'continuity',previousActive:previous.length,newRows:rows.length,shared,ratio}));
if(previous.length===0||ratio<0.9)throw Error('Insufficient ID continuity; DO NOT switch production');
console.log('READ_ONLY_COMPATIBILITY_OK');
