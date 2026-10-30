import {json} from '../core/data.js';
import {createAsyncCache} from '../core/cache.js';
const foundations=createAsyncCache({maxEntries:2}),studies=createAsyncCache({maxEntries:2});
export function projectData(id){return foundations.getOrCreate(id,()=>Promise.all(['foundation','indicators','methods'].map(name=>json(`./data/projects/${id}/${name}.json`))).then(([foundation,indicators,methods])=>({foundation,indicators:indicators.items,methods:methods.items})));}
export const publications=()=>json('./data/projects/publications.json');
export const reviewedPage=(project,id)=>json(`./data/projects/published/${project}/${id}.json`);
/** One shared current snapshot per completed study; failed requests can retry. */
export function completeProjectData(id){
  return studies.getOrCreate(id,()=>Promise.all(['expertise','statistics','analytics','refresh-status','documentary'].map(name=>json(`./data/projects/${id}/${name}.json`))).then(([expertise,statistics,analytics,refresh,documentary])=>({expertise,statistics,analytics,refresh,documentary})));
}
export const currentReports=()=>json('data/current-reports.json');
export const youthData=()=>completeProjectData('youth_children');
export const personnelData=()=>completeProjectData('personnel');
export const longlifeData=()=>completeProjectData('long_active_life');

export const healthtechData=()=>completeProjectData('health_technologies');
export const infrastructureData=()=>completeProjectData('life_infrastructure');
export const environmentData=()=>completeProjectData('environment');
export const competitiveData=()=>completeProjectData('competitive_economy');
export const dataeconomyData=()=>completeProjectData('data_economy');
export const tourismData=()=>completeProjectData('tourism');
export const efficientTransportData=()=>completeProjectData('efficient_transport');
export const internationalExportData=()=>completeProjectData('international_export');
