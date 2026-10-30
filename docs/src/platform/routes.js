import {getProject,foundationPages,expertiseBlueprint,projectHref,completeProjectPages} from './projects.js';
export const familyPages=['overview','framework','logic','audit','targets','map','regions','finance','network','texts','domains','causal','proposals','lab','explorer','library','updates','projections','population','authors'];
const plannedPages=new Set([...foundationPages,...expertiseBlueprint].map(p=>p.id));
export function parseRoute(hash='') {
  const [path,query='']=String(hash).replace(/^#/,'').split('?');
  const parts=path.split('/').filter(Boolean);
  const nationalProject=parts[0]==='projects'?getProject(parts[1]).id:'family';
  const requested=parts[0]==='projects'?parts[2]:parts[0];
  const allowed=nationalProject==='family'?familyPages:completeProjectPages[nationalProject]?.map(p=>p.id)||plannedPages;
  const page=(Array.isArray(allowed)?allowed.includes(requested):allowed.has(requested))?requested:'overview';
  return {...Object.fromEntries(new URLSearchParams(query)),nationalProject,page,mode:'latest'};
}
export function switchProject(state,projectId){
  const p=getProject(projectId);
  const shared=['overview','explorer','library'];
  const completedPages=id=>id==='family'?familyPages:completeProjectPages[id]?.map(x=>x.id);
  const equivalent=completedPages(state.nationalProject)?.includes(state.page)&&completedPages(p.id)?.includes(state.page);
  const page=equivalent?state.page:state.nationalProject!=='family'&&p.id!=='family'&&foundationPages.some(x=>x.id===state.page)?state.page:shared.includes(state.page)?state.page:'overview';
  return projectHref(p.id,page);
}
