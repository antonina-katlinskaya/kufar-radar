// Kufar Radar — Demand UI module, 2026-11-09.
// Front-end only. Uses existing CAT/CUBE daily increments AFTER removeRobot().
// Do not confuse openings of the phone number with calls or unique leads.
const DEM={period:"today",mode:"all",group:"exact",metric:"views",from:"",to:"",opened:null,shown:40};
const DEM_AREA=[0,30,35,40,45,50,55,60,65,70,75,80,90,100,120,140,160,180,200,250,300,Infinity];
const DEM_PRICE=[0,45000,50000,55000,60000,65000,70000,80000,90000,100000,120000,140000,160000,180000,200000,250000,300000,400000,500000,750000,Infinity];
function demDates(){
 const today=todayStr();let from=today,to=today;
 if(DEM.period==="yesterday")from=to=addDays(today,-1);
 else if(DEM.period==="custom"){from=DEM.from||addDays(today,-6);to=DEM.to||today;}
 else if(/^\d+$/.test(DEM.period))from=addDays(today,-Math.min(90,Number(DEM.period))+1);
 const recorded=Object.keys(CUBE.days).sort(),first=recorded[0]||today,last=recorded.at(-1)||today;
 const days=[];
 if(from<=to)for(let d=from;d<=to&&days.length<120;d=addDays(d,1))if(CUBE.days[d])days.push(d);
 return {from,to,days,first,last};
}
function demPrice(a){
 const euro=Number(a.pe),usd=Number(a.pu);
 if(euro>0&&Number.isFinite(euro))return {value:Math.round(euro*100)/100,currency:"€"};
 if(usd>0&&Number.isFinite(usd))return {value:Math.round(usd*100)/100,currency:"$"};
 return null;
}
function demBand(n,edges){
 for(let i=0;i<edges.length-1;i++)if(n>=edges[i]&&n<edges[i+1])return {low:edges[i],high:edges[i+1]};
 return null;
}
function demDescriptor(a){
 const area=Number(a.a),price=demPrice(a);
 if(DEM.group==="area"){
  if(!(area>0))return null;
  const b=demBand(area,DEM_AREA);return b&&{key:"area|"+b.low,group:"area",...b};
 }
 if(!price)return null;
 if(DEM.group==="price"){
  const edges=DEM_PRICE;
  const b=demBand(price.value,edges);
  return b&&{key:"price|"+price.currency+"|"+b.low,group:"price",currency:price.currency,...b};
 }
 if(!(area>0))return null;
 const exactArea=Math.round(area*100)/100;
 return {key:"exact|"+exactArea+"|"+price.value.toFixed(2)+"|"+price.currency,group:"exact",area:exactArea,price:price.value,currency:price.currency};
}
function demLabel(g){
 const n=x=>fmt1(x);
 if(g.group==="exact")return n(g.area)+" м² · "+n(g.price)+" "+g.currency;
 const units=g.group==="area"?" м²":" тыс. "+g.currency;
 const scaled=x=>g.group==="area"?fmt(x):fmt(x/1000);
 return (g.low===0?"до "+scaled(g.high):g.high===Infinity?"от "+scaled(g.low):scaled(g.low)+"–"+scaled(g.high))+units;
}
function demPaid(day,id,views,opens){
 const e=day.pe&&day.pe[id];
 let pv=0,pp=0;
 if(e&&typeof e==="object"){
  for(const x of Object.values(e))if(Array.isArray(x)){pv+=Math.max(0,Number(x[0])||0);pp+=Math.max(0,Number(x[1])||0);}
 }else if(day.pr&&day.pr[id]){pv=views;pp=opens;}
 return [Math.min(views,pv),Math.min(opens,pp)];
}
function demAggregate(){
 const period=demDates(),byId=new Map(),counts={unknown:0,days:period.days.length};
 for(const day of period.days){
  const D=CUBE.days[day];
  for(const [id,raw]of Object.entries(D.a||{})){
   const ad=CAT.ads[id];if(!ad||!adOk(id,ad))continue;
   let views=Math.max(0,Number(raw[0])||0),opens=Math.max(0,Number(raw[1])||0);
   const paid=demPaid(D,id,views,opens);
   if(DEM.mode==="paid"){views=paid[0];opens=paid[1];}
   else if(DEM.mode==="free"){views-=paid[0];opens-=paid[1];}
   if(!views&&!opens)continue;
   let item=byId.get(id);
   if(!item){item={id,a:ad,dv:0,dp:0};byId.set(id,item);}
   item.dv+=views;item.dp+=opens;
  }
 }
 const groups=new Map();
 for(const item of byId.values()){
  const descr=demDescriptor(item.a);
  if(!descr){counts.unknown++;continue;}
  let g=groups.get(descr.key);
  if(!g){g={...descr,views:0,opens:0,items:new Map()};groups.set(descr.key,g);}
  g.views+=item.dv;g.opens+=item.dp;g.items.set(item.id,item);
 }
 const records=[...groups.values()].map(g=>({...g,count:g.items.size,ratio:g.views?100*g.opens/g.views:null}));
 records.sort((a,b)=>demValue(b)-demValue(a)||b.opens-a.opens||b.views-a.views||a.key.localeCompare(b.key,"ru"));
 return {period,records,unpriced:counts.unknown,ids:new Set(records.flatMap(g=>[...g.items.keys()]))};
}
function demValue(x){
 if(DEM.metric==="opens")return x.opens;
 if(DEM.metric==="ratio")return x.views>=20?100*x.opens/x.views:-1;
 return x.views;
}
function demPareto(records){
 const total=records.reduce((v,g)=>v+(DEM.metric==="views"?g.views:g.opens),0);
 let seen=0,count=0;const ads=new Set();
 if(DEM.metric!=="ratio"&&total>0)for(const g of records){
  if(seen>=total*.8)break;
  count++;seen+=DEM.metric==="views"?g.views:g.opens;
  for(const id of g.items.keys())ads.add(id);
 }
 return {total,count,ads:ads.size,share:total?100*seen/total:0};
}
function demCards(g){
 const value=x=>DEM.metric==="opens"?x.dp:DEM.metric==="ratio"?(x.dv>=10?100*x.dp/x.dv:-1):x.dv;
 return [...g.items.values()].sort((a,b)=>value(b)-value(a)||b.dp-a.dp||b.dv-a.dv||String(a.id).localeCompare(String(b.id),"ru")).slice(0,30).map(x=>{
  const a=x.a,placed=a.lt0||a.fs||a.lt;
  return adCard({id:x.id,a,dv:x.dv,dp:x.dp,emp:empName(empKey(a)),placed,lastRaise:a.lt&&placed&&a.lt-placed>600?a.lt:null,raises:0},null,{plus:true,total:true});
 }).join("");
}
function demChip(attr,value,label,current){
 return '<button type="button" class="dem-chip'+(current===value?' is-on':'')+'" data-dem-'+attr+'="'+esc(value)+'" aria-pressed="'+(current===value?'true':'false')+'">'+esc(label)+'</button>';
}
function demHeader(){
 const periods=[["today","Сегодня"],["yesterday","Вчера"],["7","7 дней"],["14","14 дней"],["30","30 дней"],["90","90 дней"],["custom","Свой период"]];
 const groups=[["exact","По сумме просмотров"],["price","По стоимости"],["area","По площадям"]];
 const modes=[["all","Все"],["free","Органика"],["paid","Продвижение"]];
 const metrics=[["views","Просмотры"],["opens","Открытия номера"],["ratio","Доля открытий"]];
 const chipList=(name,opts,selected)=>opts.map(x=>demChip(name,x[0],x[1],selected)).join("");
 const custom=DEM.period==="custom"?'<div class="dem-custom"><label>От <input id="demFrom" type="date" value="'+esc(DEM.from||addDays(todayStr(),-6))+'"></label><label>До <input id="demTo" type="date" value="'+esc(DEM.to||todayStr())+'"></label></div>':"";
 return '<div class="dem-head"><div><h2>Спрос</h2><p>Что привлекает просмотры и что побуждает открыть номер?</p></div></div>'
 +'<div class="dem-controls"><div class="dem-control dem-period"><span>Период</span><div class="dem-chips">'+chipList("period",periods,DEM.period)+'</div></div>'
 +'<div class="dem-control dem-group"><span>Рейтинг</span><div class="dem-chips">'+chipList("group",groups,DEM.group)+'</div></div>'
 +custom
 +'<div class="dem-control dem-mode"><span>Объявления</span><div class="dem-chips">'+chipList("mode",modes,DEM.mode)+'</div></div>'
 +'<div class="dem-control dem-metric"><span>Интерес</span><div class="dem-chips">'+chipList("metric",metrics,DEM.metric)+'</div></div></div>';
}
function viewDemand(){
 const data=demAggregate(),{period,records,ids}=data,pareto=demPareto(records);
 const totalV=records.reduce((sum,g)=>sum+g.views,0),totalP=records.reduce((sum,g)=>sum+g.opens,0);
 const base=DEM.metric==="views"?"просмотров":"открытий";
 const available=period.days.length?period.days[0]+" — "+period.days.at(-1):"нет данных";
 const coverage=period.from<period.first||period.to>period.last?' · доступная история: '+period.first+" — "+period.last:"";
 const pref=DEM.metric==="ratio"?'Для сравнения доли открытий в группе нужно не менее 20 просмотров. ":"";
 const note='Период: '+period.from+' — '+period.to+' · учтены дни: '+fmt(period.days.length)+' ('+available+').'+coverage
 +' Вычтены обнаруженные роботизированные открытия номера. Цена берётся из текущей карточки, её прошлые изменения не восстановлены. '+pref
 +(data.unpriced?' Не хватает площади или цены для группировки: '+fmt(data.unpriced)+' объявлений.':'');
 const kpi=(value,label,sub)=>'<div class="dem-kpi"><b>'+esc(value)+'</b><span>'+esc(label)+'</span><small>'+esc(sub)+'</small></div>';
 const ratio=totalV?(100*totalP/totalV).toLocaleString("ru-RU",{maximumFractionDigits:1})+'%':"—";
 let stats='<div class="dem-stats">'
 +kpi(fmt(totalV),"Просмотры за период","Прирост после фильтра")
 +kpi(fmt(totalP),"Открытий номера","Это не количество звонков")
 +kpi(ratio,"Открытий / просмотров","Относительный показатель")
 +kpi(fmt(ids.size),"Объявлений",fmt(records.length)+" групп предложений")
 +kpi(DEM.metric==="ratio"?"—":pareto.share.toLocaleString("ru-RU",{maximumFractionDigits:1})+'%',"Группы, дающие 80%",DEM.metric==="ratio"?"80/20 неприменимо к доле":fmt(pareto.count)+" групп · "+fmt(pareto.ads)+" объявлений")
 +'</div>';
 const top=records.slice(0,12),max=Math.max(1,...top.map(g=>Math.max(0,demValue(g))));
 const chartHead='<div class="dem-chart-head"><span>Диапазон / предложение</span><span>Интерес по группам</span><span>Показатель</span></div>';
 let chart=top.map((g,i)=>{
  const score=demValue(g),len=score>=0?Math.max(0,score/max)*100:0;
  const col='rgb('+Math.round(145+i*5)+','+Math.round(190+i*3.2)+','+Math.round(216+i*2.2)+')';
  const value=DEM.metric==="ratio"?(score<0?"—":score.toLocaleString("ru-RU",{maximumFractionDigits:1})+'%'):fmt(score);
  const label=DEM.metric==="ratio"?" просмотров / "+fmt(g.opens)+" открытий":' объявлений';
  return '<div class="dem-chart-row"><div class="dem-chart-label"><b>'+esc(demLabel(g))+'</b><small>'+fmt(g.count)+label+'</small></div><div class="dem-track"><div class="dem-fill" style="width:'+len.toFixed(2)+'%;background:'+col+'"></div></div><strong>'+esc(value)+'</strong></div>';
 }).join('');
 const title=DEM.group==="exact"?"Интерес к сочетаниям площади и цены":DEM.group==="area"?"Интерес по диапазонам площади":"Интерес по диапазонам стоимости";
 const summary=DEM.metric==="ratio"?"Рейтинг по доле открытий; показатель 80/20 не применяется к процентам.":'80% '+base+' обеспечивают '+fmt(pareto.count)+' из '+fmt(records.length)+' групп ('+pct(pareto.count,records.length)+').';
 const rows=records.slice(0,DEM.shown).flatMap((g,i)=>{
  const key=g.key,open=DEM.opened===key,score=demValue(g);
  const fraction=DEM.metric==="ratio"?"—":pct(DEM.metric==="views"?g.views:g.opens,pareto.total);
  const rate=g.views?(100*g.opens/g.views).toLocaleString('ru-RU',{maximumFractionDigits:1})+'%':"—";
  const button='<button type="button" class="dem-expand" data-dem-expand="'+esc(key)+'" aria-expanded="'+open+'">'+(open?'Свернуть':'Топ-'+Math.min(30,g.count)+' с фото')+' ▾</button>';
  const row='<tr><td>'+(i+1)+'</td><td><b>'+esc(demLabel(g))+'</b></td><td class="num">'+fmt(g.count)+'</td><td class="num">'+fmt(g.views)+'</td><td class="num">'+fmt(g.opens)+'</td><td class="num">'+rate+'</td><td>'+button+'</td></tr>';
  if(!open)return [row];
  const gallery='<tr class="dem-gallery-row"><td colspan="7"><div class="dem-gallery-title"><b>'+esc(demLabel(g))+' · топ-'+Math.min(30,g.count)+'</b><span>Отсортировано по '+(DEM.metric==="views"?"просмотрам":DEM.metric==="opens"?"открытиям номера":"доле открытий")+' за период</span></div><div class="cgrid dem-gallery">'+demCards(g)+'</div></td></tr>';
  return [row,gallery];
 });
 const table=records.length?'<div class="tbl-wrap dem-table-wrap"><table><thead><tr><th>№</th><th>Группа</th><th>Объявлений</th><th>Просмотры</th><th>Открытия</th><th>На 100 просм.</th><th>Карточки</th></tr></thead><tbody>'+rows.join('')+'</tbody></table></div>':'<p class="note">За выбранный период нет подтверждённых данных для анализа.</p>';
 const more=records.length>DEM.shown?'<button class="btn dem-more" data-dem-more="1">Показать ещё '+fmt(Math.min(40,records.length-DEM.shown))+' групп</button>':'';
 return '<div class="dem-panel">'+demHeader()+'<p class="dem-note">'+esc(note)+'</p>'+stats
 +'<div class="dem-section-title"><h3>'+esc(title)+'</h3><span>'+esc(summary)+'</span></div>'
 +(top.length?'<div class="dem-chart">'+chartHead+chart+'</div>':'<p class="note">Нет данных.</p>')
 +'<details class="dem-details" open><summary>Подробная таблица групп · '+fmt(records.length)+'</summary>'+table+more+'</details>'
 +'<p class="dem-note">Просмотры и открытия номера — прибавка счётчиков Kufar, а не уникальные люди. Для органики и продвижения используются раздельные показатели за дни, когда статус известен. Показатель «открытий / просмотров» нельзя считать подтверждённой долей позвонивших.</p></div>';
}
