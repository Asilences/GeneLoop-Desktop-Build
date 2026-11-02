/** Read-only host bridge; validates committed evidence with the existing Store. */
import {readFileSync} from 'node:fs';
import {createCapabilityStore} from '../src/adapters/capability_store.ts';
import {extendCapabilitySeed} from '../src/adapters/capability_materials.ts';
const [directory,seedPath,materialsPath]=process.argv.slice(2);
if(!directory||!seedPath)throw Error('usage: export-capability-construction-library.mjs STORE SEED.json');
const seed=JSON.parse(readFileSync(seedPath,'utf8'));
const forbidden=async()=>{throw Error('construction_export_is_read_only');};
const store=createCapabilityStore({directory,owner:seed.owner,runValidation:forbidden,
 validator:{id:'read-only-export',sha256:'0'.repeat(64),check:forbidden}});
const materials=materialsPath?extendCapabilitySeed(seed,JSON.parse(readFileSync(materialsPath,'utf8'))):{snapshot:seed,catalog:[]};
process.stdout.write(JSON.stringify({...store.constructionLibrary(materials.snapshot),material_catalog:materials.catalog}));
