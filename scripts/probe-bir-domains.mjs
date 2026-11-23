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
