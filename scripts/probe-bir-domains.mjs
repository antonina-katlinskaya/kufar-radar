// Read-only compatibility probe. No Cloudflare/D1 writes and no Telegram notifications.
// Usage: node scripts/probe-bir-domains.mjs
const domains=['https://bir.by','https://birby.by','https://minskworld.by'];
const endpoints=['get-number-of-objects-for-pc/','get-search-objects-in-building/'];
async function request(host,path,body) {
  try {
    const response=await fetch(host+'/ajax/'+path,{
      method:'POST',redirect:'follow',
      headers:{'Content-Type':'application/x-www-form-urlencoded','X-Requested-With':'XMLHttpRequest','Referer':host+'/','User-Agent':'Mozilla/5.0'},
      body:new URLSearchParams(body),signal:AbortSignal.timeout(12000)
    });
    const raw=await response.text();
    const ids=[...raw.matchAll(/data-loadobject="([0-9a-f-]{36})"/gi)].map(x=>x[1]);
    return {ok:response.ok,status:response.status,finalUrl:response.url,
      length:raw.length,objects:ids.length,uniqueIds:[...new Set(ids)],
      count:path.startsWith('get-number')?Number(raw.trim()):null,
      looksHtml:/<tr\b/i.test(raw),contentType:response.headers.get('content-type')};
  }catch(e){return {ok:false,error:String(e)};}
}
const results={};
for(const host of domains){
  const count=await request(host,endpoints[0],{'object[]':'Minsk World'});
  const listing=await request(host,endpoints[1],{'object[]':'Minsk World',orderby:'nomerPomeschenia',ascdesc:'ASC',limit:'5000'});
  results[host]={count,listing};
  console.log(JSON.stringify({host,count,listing:{...listing,uniqueIds:undefined,
    sampleIds:listing.uniqueIds?.slice(0,3)}}));
}
const keys=domains.filter(h=>results[h].listing.uniqueIds?.length);
for(let i=0;i<keys.length;i++)for(let j=i+1;j<keys.length;j++){
  const a=new Set(results[keys[i]].listing.uniqueIds);
  const b=new Set(results[keys[j]].listing.uniqueIds);
  const shared=[...a].filter(id=>b.has(id)).length;
  console.log(JSON.stringify({compare:[keys[i],keys[j]],shared,left:a.size,right:b.size,
    overlapOfSmaller:shared/Math.min(a.size,b.size)}));
}
if(!results['https://birby.by'].listing.uniqueIds?.length) process.exitCode=1;

const roomUrl='https://birby.by/ajax/get-search-objects-new/';
const roomForm=new URLSearchParams([['type','live'],['object[]','Minsk World'],['comnat[]','1-room'],['cenaOt',''],['cenaZaKvOt',''],['obschPloschadOt',''],['orderby','cena'],['ascdesc','ASC'],['limit','5000']]);
const roomResponse=await fetch(roomUrl,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8','X-Requested-With':'XMLHttpRequest','Referer':'https://birby.by/search-by-parameters/','User-Agent':'Mozilla/5.0'},body:roomForm,signal:AbortSignal.timeout(20000)});
const roomHtml=await roomResponse.text();
const roomRows=[...roomHtml.matchAll(/data-loadobject="([0-9a-f-]{36})"/gi)].length;
console.log(JSON.stringify({phase:'room_search',status:roomResponse.status,finalUrl:roomResponse.url,rows:roomRows,bodyLength:roomHtml.length}));
if(!roomResponse.ok||!roomResponse.url.startsWith('https://birby.by/ajax/')||roomRows===0)process.exitCode=1;
