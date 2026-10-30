/** Longlife static research pages share the validated source-linked renderer. */
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {longlifePages} from '../src/platform/projects.js';
import {buildResearchPages,validateResearchContent,renderReportBlocks} from './build_research_pages.mjs';
export {renderReportBlocks};
export const validateLonglifeContent=expertise=>validateResearchContent(expertise,'long_active_life',longlifePages);
export const buildLonglifePages=root=>buildResearchPages('long_active_life',longlifePages,root);
if(process.argv[1]&&fileURLToPath(import.meta.url)===path.resolve(process.argv[1]))await buildLonglifePages();
