"""New official-rubric evaluation with an explicitly substituted pinned judge.

This is not a reproduction of retired GPT-4 Vision historical scores. Original
agent, rubric and image ordering are retained; no pass threshold is introduced.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def ref(path):
    path=Path(path).absolute()
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def run(args):
    root=args.output.resolve();root.mkdir(parents=True,mode=0o700,exist_ok=False)
    runtime=args.runtime.resolve()
    os.environ['KOURI_MODELS_FILE']=str(runtime/'config/research-chartmimic-judge.json')
    if args.call_model:
        for line in args.env_file.read_text().splitlines():
            if line.startswith('KOURI_API_KEY='):
                os.environ.setdefault('KOURI_API_KEY',line.split('=',1)[1].strip().strip('"').strip("'"))
    sys.path.insert(0,str(runtime))
    from src.adapters.harness.capability.capability_proposal import CumulativeProposalGate
    chart=args.official.resolve()/'chart2code'
    worker=Path(__file__).with_name('judge_worker.py')
    effective={'format':'chartmimic_substitute_judge_v1','label':'official_rubric_with_GPT4o_2024_11_20_new_evaluation',
        'historical_GPT4V_comparable':False,'official_evaluator_modified':False,
        'model':'gpt-4o-2024-11-20','reasoning_effort':'provider_default','max_tokens':4096,
        'temperature':0.1,'top_p':0.95,'sdk_max_retries':0,'official_max_retry_iters':1,
        'request_timeout_seconds':180,'reference':ref(args.reference),'generated':ref(args.generated),
        'image_order':['reference','generated'],'rubric':ref(chart/'prompts/GPT4EvaluationAgent/gpt-4-vision-preview.json'),
        'agent':ref(chart/'agents/gpt4evaluation_agent.py'),'llm':ref(chart/'llm/openai.py'),
        'profile':ref(runtime/'config/research-chartmimic-judge.json'),'gate':ref(runtime/'src/adapters/harness/capability/capability_proposal.py'),
        'worker':ref(worker),'driver':ref(__file__),'model_request_and_cost_limits':None,
        'pricing':'official_OpenAI_reference_not_Kouri_invoice','quality_threshold':None,
        'python_launcher':str(args.python.absolute()),
        'dependencies':subprocess.check_output([str(args.python),'-m','pip','freeze'],text=True).splitlines()}
    (root/'effective.json').write_text(json.dumps(effective,indent=2)+'\n')
    job={'official':str(args.official.resolve()),'reference':str(args.reference.resolve()),
         'generated':str(args.generated.resolve()),'response':str(root/'response.json'),'preview':not args.call_model}
    (root/'job.json').write_text(json.dumps(job,indent=2)+'\n')
    result={'status':'failed','quality':'requires_reading_original_judge_response','billing_usd':None}
    started=time.monotonic()
    def invoke(env):
        child_env={key:value for key,value in os.environ.items() if key!='KOURI_API_KEY'}
        child_env.update(OPENAI_BASE_URL=env['DEEPSEEK_BASE_URL'],OPENAI_API_KEY=env['DEEPSEEK_API_KEY'])
        with (root/'worker.log').open('x') as stream:
            return subprocess.run([str(args.python),str(worker),str(root/'job.json')],
                env=child_env,stdout=stream,stderr=subprocess.STDOUT,timeout=240).returncode
    try:
        if args.call_model:
            with CumulativeProposalGate(args.ledger_root,model=effective['model'],max_tokens=4096,
                                        reasoning_effort='provider_default') as gate:
                gate.current=root
                try:
                    code=invoke(gate.environment())
                finally:
                    result.update(gate.costs(root))
        else:
            code=invoke({'DEEPSEEK_BASE_URL':'http://127.0.0.1:1/v1','DEEPSEEK_API_KEY':'preview-no-request'})
        result.update(status=('responded' if args.call_model else 'preview') if code==0 else 'failed',returncode=code)
        if (root/'response.json').exists():result['response']=ref(root/'response.json')
    except Exception as error:
        result['error']=type(error).__name__+':'+str(error)
    finally:
        result['elapsed_seconds']=time.monotonic()-started
        (root/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('runtime','official','reference','generated','output','python','ledger-root','env-file'):
        parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--call-model',action='store_true')
    print(json.dumps(run(parser.parse_args()),indent=2))
