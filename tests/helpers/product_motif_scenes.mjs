/** Actual repository products admitted by the original loader; no model/tools. */
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
export function loadedProductMotifScenes(){
  const root=fileURLToPath(new URL('../../',import.meta.url));
  const script=`import json,sys\nfrom pathlib import Path\nfrom src.adapters.harless_rsi_bundle import load_product_bundle\nroot=Path(sys.argv[1]).resolve()\nrows=[]\nfor row in json.loads((root/'config/harless-scenes.json').read_text(encoding='utf-8'))['scenes']:\n if row.get('rsi',{}).get('runtime_bundle'):\n  loaded=load_product_bundle(root,root/row['rsi']['runtime_bundle'],row['id'])\n  library=json.loads(Path(loaded['runtime_library']).read_text(encoding='utf-8'))\n  tools=[x['name'] for x in loaded.get('certified_tool_schemas',[])] or list(library.get('contracts',{}))\n  rows.append({**loaded,'id':row['id'],'label':row['label'],'preset':'sss-'+row['id'],'allowed_tools':tools})\nprint(json.dumps(rows))`;
  return JSON.parse(execFileSync(process.env.SSS_PYTHON??process.env.SSS_PURE_CODE_PYTHON??(process.platform==='win32'?'python':'python3'),['-c',script,root],
    {cwd:root,encoding:'utf8',env:{...process.env,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8'}}));
}
