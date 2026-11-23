/** Offline compiler bridge. Executes pure JSON programs only, never model/API calls. */
import {readFileSync} from 'node:fs';
import {prepareLearnedAction,bindLearnedDecision,validateLearnedDecision} from '../src/adapters/learned_decision_program.ts';
import {acceptDecision,validateDecisionPacket} from '../src/adapters/typed_decisions.ts';
import {validateProgram} from '../src/adapters/paper_rsi_program.ts';
const v=JSON.parse(readFileSync(0,'utf8'));
function syntaxIssues(node,path){
 try{validateProgram(node);return [];}catch(error){
  const children=[];
  if(Array.isArray(node)&&!['lit','var'].includes(node[0])){
   if(node[0]==='object'&&node[1]&&typeof node[1]==='object'&&!Array.isArray(node[1])){
    for(const [key,value]of Object.entries(node[1]))children.push(...syntaxIssues(value,[...path,1,key]));
   }else for(let i=1;i<node.length;i++){
    if(node[0]==='let'&&i===1||['map','filter'].includes(node[0])&&i===2)continue;
    children.push(...syntaxIssues(node[i],[...path,i]));
   }
  }
  return children.length?children:[{path,error:String(error),operation:Array.isArray(node)?node[0]:typeof node,
   members:Array.isArray(node)?node.length:null}];
 }
}
let stage='validation';
try{
 if(v.decision_packet){
  const packet=validateDecisionPacket(v.decision_packet);
  process.stdout.write(JSON.stringify({ok:true,decision:acceptDecision(packet,v.result,v.threshold)}));
 }else{
 validateLearnedDecision(v.candidate);
 stage='preparation';
 const prepared=prepareLearnedAction(v.candidate,v.context),request=prepared?.request??null;
 stage='binding';
 const binding=!v.prepare_only&&request&&(prepared.kind==='direct'||v.values)?bindLearnedDecision(v.candidate,v.context,v.values??{}):null;
 process.stdout.write(JSON.stringify({ok:true,request,binding,...(prepared?.kind==='direct'?{execution_mode:'direct'}:{})}));
 }
}catch(error){
 const syntax=v.candidate?['guard','request','bind'].flatMap(k=>syntaxIssues(v.candidate[k],[k])):[];
 process.stdout.write(JSON.stringify({ok:false,stage,error:String(error)+(syntax.length?'; syntax locations: '+JSON.stringify(syntax):'')}));process.exitCode=1;
}
