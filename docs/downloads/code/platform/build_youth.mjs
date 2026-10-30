/** Backward-compatible Youth entry point over the shared static renderer. */
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {youthPages} from '../src/platform/projects.js';
import {buildResearchPages,validateResearchContent} from './build_research_pages.mjs';
export {renderReportBlocks} from './build_research_pages.mjs';
export const validateYouthContent=expertise=>validateResearchContent(expertise,'youth_children',youthPages);
export const buildYouthPages=root=>buildResearchPages('youth_children',youthPages,root);
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))await buildYouthPages();
