import {evidenceView,usd} from '../../../src/adapters/motif_evidence_projection.ts';
import check from '../.local/motif-validator.mjs';
export {usd};
/** 只投影展示证据，不登记工具、改变认证或授权执行。 */
export function readMotifEvidence(input: unknown) {
  return evidenceView(input,check);
}
