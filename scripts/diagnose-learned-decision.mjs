/** Offline pure-expression diagnostics. Does not modify or execute task tools. */
import {readFileSync} from 'node:fs';
import {validateProgram} from '../src/adapters/paper_rsi_program.ts';
import {runLearnedProgram as runProgram} from '../src/adapters/learned_decision_program.ts';
const {candidate,context,values}=JSON.parse(readFileSync(0,'utf8'));
function evaluate(program,input){try{return {ok:true,value:runProgram(program,input)};}catch(error){return {ok:false,error:String(error)};}}
const wrap=(bindings,expression)=>bindings.reduceRight((p,b)=>['let',b[0],b[1],p],expression);
function letBindings(program,input){
 const bindings=[],rows=[];let expression=program;
 while(Array.isArray(expression)&&expression[0]==='let'){
  rows.push({name:expression[1],expression:expression[2],result:evaluate(wrap(bindings,expression[2]),input)});
  bindings.push([expression[1],expression[2]]);expression=expression[3];
 }
 return rows;
}
const conditions=[],bindings=[];let expression=candidate.guard;
let guardValidation;
try{validateProgram(expression);guardValidation={ok:true};}catch(error){guardValidation={ok:false,error:String(error)};}
while(Array.isArray(expression)&&expression[0]==='let'){
 bindings.push([expression[1],expression[2]]);
 conditions.push({kind:'guard_binding',name:expression[1],result:evaluate(wrap(bindings.slice(0,-1),expression[2]),context)});
 expression=expression[3];
}
if(Array.isArray(expression)&&['and','or'].includes(expression[0]))for(const [index,p]of expression.slice(1).entries())conditions.push({kind:'guard_condition',operator:expression[0],index,expression:p,result:evaluate(wrap(bindings,p),context)});
process.stdout.write(JSON.stringify({format:'geneloop-learned-expression-diagnostic-v1',offline_training_diagnostic_only:true,task_tools_executed:false,candidate_modified:false,
 guard_validation:guardValidation,guard:evaluate(candidate.guard,context),guard_subexpressions:conditions,
 request_expression:evaluate(candidate.request,context),request_bindings:letBindings(candidate.request,context),binding_expression:evaluate(candidate.bind,{...context,answers:values}),binding_bindings:letBindings(candidate.bind,{...context,answers:values})})+'\n');
