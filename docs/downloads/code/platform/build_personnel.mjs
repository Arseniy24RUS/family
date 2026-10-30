/** Source-linked counterparts of all Personnel research pages. */
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {personnelPages} from '../src/platform/projects.js';
import {buildResearchPages,validateResearchContent} from './build_research_pages.mjs';
export const validatePersonnelContent=expertise=>validateResearchContent(expertise,'personnel',personnelPages);
export const buildPersonnelPages=root=>buildResearchPages('personnel',personnelPages,root);
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))await buildPersonnelPages();
