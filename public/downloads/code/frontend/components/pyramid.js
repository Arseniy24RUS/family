import { svg, fmt, bindTip } from '../core/dom.js';
/** Five-year display groups only; computation and exports retain all 101 ages. */
export function pyramidChart(age, baseline, {label='Половозрастная структура', height=570,width=850}={}) {
 const w=width, left=w*.08,right=w*.92,mid=w/2,top=50,bottom=height-48;
 const groups=Array.from({length:21},(_,i)=>({start:i*5,end:i===20?101:i*5+5,label:i===20?'100+':`${i*5}–${i*5+4}`}));
 const sum=(a,g)=>a.slice(g.start,g.end).reduce((v,x)=>v+x,0);
 const max=Math.max(1,...groups.flatMap(g=>['male','female'].flatMap(s=>[sum(age[s],g),sum(baseline[s],g)])))*1.08;
 const scale=(mid-left-30)/max,dy=(bottom-top)/groups.length;
 const node=svg('svg',{viewBox:`0 0 ${w} ${height}`,class:'chart-svg',role:'img','aria-label':label},svg('title',{},label),svg('desc',{},'Слева мужчины, справа женщины. Заливка — выбранный месяц, контур — базовая структура. Все значения доступны в таблице и CSV.'));
 node.dataset.exportLegend=JSON.stringify([{name:'Мужчины · выбранный месяц',color:'#2947A0'},{name:'Женщины · выбранный месяц',color:'#539D96'},{name:'Контур · базовая структура',color:'#647087'}]);
 node.append(svg('text',{x:w*.27,y:24,'text-anchor':'middle','font-size':14,fill:'#2947A0'},'Мужчины'),svg('text',{x:w*.73,y:24,'text-anchor':'middle','font-size':14,fill:'#539D96'},'Женщины'));
 const nt=w<500?2:4;
 for(let j=0;j<=nt;j++){
  const v=max*j/nt,x=v*scale;for(const s of[-1,1]){if(!j)continue;const xx=mid+s*(x+24);node.append(svg('line',{x1:xx,x2:xx,y1:top-8,y2:bottom+3,stroke:'#D9DEE8'}),svg('text',{x:xx,y:bottom+25,'text-anchor':'middle','font-size':11,fill:'#647087'},fmt(v,0)));}
 }
 for(let i=0;i<groups.length;i++){
  const g=groups[i],y=bottom-(i+1)*dy+2,bh=dy-4;
  node.append(svg('text',{x:mid,y:y+bh/2+4,'text-anchor':'middle','font-size':10,fill:'#3D4A60'},g.label));
  for(const s of['male','female']){
   const value=sum(age[s],g),base=sum(baseline[s],g),sgn=s==='male'?-1:1;
   const x=value*scale,bx=base*scale,pad=24;
   const rect=svg('rect',{x:sgn<0?mid-pad-x:mid+pad,y,width:x,height:bh,fill:s==='male'?'#2947A0':'#539D96',rx:1,tabindex:0});
   const outline=svg('rect',{x:sgn<0?mid-pad-bx:mid+pad,y:y-1,width:bx,height:bh+2,fill:'none',stroke:'#647087','stroke-width':.8,'pointer-events':'none'});
   bindTip(rect,`${s==='male'?'Мужчины':'Женщины'} · ${g.label}`,['Выбранный месяц: '+fmt(value,0),'Базовая дата: '+fmt(base,0)]);node.append(rect,outline);
  }
 }
 node.append(svg('text',{x:mid,y:height-4,'font-size':11,fill:'#647087','text-anchor':'middle'},'Численность, человек · контур — базовое население'));
 return node;
}
