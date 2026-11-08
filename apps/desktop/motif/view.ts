import {evidenceView,usd} from './evidence-projection.ts';
import check from '../.local/motif-validator.mjs';
import checkRuntime from '../.local/motif-validator-v2.mjs';
export {usd};
/** 只投影展示证据，不登记工具、改变认证或授权执行。 */
export function readMotifEvidence(input: unknown) {
  return evidenceView(input,(input as any)?.format==='geneloop-motif-evidence-v2'?checkRuntime:check);
}
