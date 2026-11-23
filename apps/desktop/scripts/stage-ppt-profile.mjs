import {cpSync,mkdirSync} from 'node:fs';
import {join} from 'node:path';
export function stagePptProfile(app,bundle){
  mkdirSync(join(bundle,'skills'),{recursive:true});
  cpSync(join(app,'skills/geneloop-ppt'),join(bundle,'skills/geneloop-ppt'),{recursive:true});
}
