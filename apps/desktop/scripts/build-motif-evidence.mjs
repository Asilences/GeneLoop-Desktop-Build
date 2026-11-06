import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
import {mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import Ajv2020 from 'ajv/dist/2020.js';
import standaloneCode from 'ajv/dist/standalone/index.js';
const app=fileURLToPath(new URL('../',import.meta.url));
const schema=JSON.parse(readFileSync(new URL('../../../config/motif-evidence-v1.schema.json',import.meta.url),'utf8'));
const ajv=new Ajv2020({allowUnionTypes:true,code:{source:true,esm:true}});
mkdirSync(new URL('../.local/',import.meta.url),{recursive:true});
writeFileSync(new URL('../.local/motif-validator.mjs',import.meta.url),standaloneCode(ajv,ajv.compile(schema)));
await build({absWorkingDir:app,entryPoints:['motif/view.ts'],outfile:'ui/desktop/motif-evidence.js',
  bundle:true,format:'esm',platform:'browser',target:'es2022',minify:true,legalComments:'eof'});
