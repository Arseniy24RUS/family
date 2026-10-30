import {getProject} from './projects.js';
const family=['#2947A0','#539D96','#6280D9','#031E4F','#67AEA7','#7F92BB','#315C83','#A7DBD6'];
const familyRamp=['#EEF3F9','#D7EFEB','#A7DBD6','#67AEA7','#539D96','#446BA4','#2947A0','#192F70','#031E4F'];
export const C=[...family];
export const fieldColors={HH:C[0],LL:C[7],HL:C[2],LH:C[1],NS:'#EEF3F9'};
let current='family',stops=[...familyRamp];
const rgb=hex=>hex.replace('#','').match(/.{2}/g).map(v=>parseInt(v,16));
export function mix(a,b,t){const aa=rgb(a),bb=rgb(b);return '#'+aa.map((v,i)=>Math.round(v+(bb[i]-v)*t).toString(16).padStart(2,'0')).join('').toUpperCase();}
export function luminance(hex){return rgb(hex).map(v=>{const s=v/255;return s<=.04045?s/12.92:((s+.055)/1.055)**2.4;}).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);}
export const labelColor=fill=>luminance(fill)<.32?'#FFFFFF':'#0A132D';
export function ramp(t){t=Math.max(0,Math.min(1,Number.isFinite(t)?t:0));const u=t*(stops.length-1),i=Math.min(stops.length-2,Math.floor(u));return mix(stops[i],stops[i+1],u-i);}
export const forecastFill=()=>current==='family'?'#DCE7F6':mix(C[0],'#FFFFFF',.85);
export function applyTheme(projectId,root=globalThis.document?.documentElement){
  const p=getProject(projectId);current=p.id;
  const palette=current==='family'?family:[p.color,mix(p.color,'#101A26',.28),mix(p.color,'#FFFFFF',.28),mix(p.color,'#101A26',.60),mix(p.color,'#FFFFFF',.48),mix(p.color,'#101A26',.44),mix(p.color,'#FFFFFF',.64),mix(p.color,'#FFFFFF',.78)];
  C.splice(0,C.length,...palette);
  stops=current==='family'?familyRamp:[mix(p.color,'#FFFFFF',.94),mix(p.color,'#FFFFFF',.75),mix(p.color,'#FFFFFF',.46),p.color,mix(p.color,'#101A26',.62)];
  Object.assign(fieldColors,{HH:C[0],LL:C[7],HL:C[2],LH:C[1],NS:current==='family'?'#EEF3F9':mix(p.color,'#FFFFFF',.94)});
  let accessible=p.color;for(let i=0;luminance(accessible)>.14&&i<12;i++)accessible=mix(accessible,'#0A132D',.13);
  const vars={'--project-color':p.color,'--project-accent':current==='family'?p.color:accessible,'--project-dark':C[3],'--project-soft':current==='family'?'#DCE7F6':mix(p.color,'#FFFFFF',.90),'--project-tint':current==='family'?'#EEF3F9':mix(p.color,'#FFFFFF',.97),'--teal':C[1],'--teal-mid':C[4],'--aqua':C[7],'--blue-mid':C[2],'--blue-deep':current==='family'?'#192F70':C[3],'--green':accessible,'--blue':accessible,'--forest':C[3],'--navy':C[3],'--accent':forecastFill(),'--yellow':C[7]};
  if(root){root.dataset.project=current;for(const [k,v] of Object.entries(vars))root.style.setProperty(k,v);}
  return {project:p,palette:[...C],variables:vars};
}
