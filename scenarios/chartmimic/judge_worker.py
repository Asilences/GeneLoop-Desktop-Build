"""Load the original official classes in the isolated original-SDK environment."""
import importlib.util
import json
from pathlib import Path
import sys
import types


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(job):
    chart = Path(job['official']) / 'chart2code'
    sys.path.insert(0, str(chart))
    # Avoid importing unrelated official LLM adapters and their heavyweight
    # optional dependencies. Executed source/classes remain byte-identical.
    package = types.ModuleType('agents')
    package.__path__ = [str(chart / 'agents')]
    sys.modules['agents'] = package
    from agents.gpt4evaluation_agent import GPT4EvaluationAgent
    OPENAI_GPT = load(chart / 'llm/openai.py', 'chartmimic_official_openai').OPENAI_GPT
    llm = OPENAI_GPT(engine='gpt-4o-2024-11-20', temperature=0.1,
                     max_tokens=4096, top_p=0.95, max_retry_iters=1,
                     retry_delays=1, context_length=128000)
    llm.client = llm.client.with_options(timeout=180, max_retries=0)
    agent = GPT4EvaluationAgent(llm, str(chart/'prompts/GPT4EvaluationAgent/gpt-4-vision-preview.json'))
    if job.get('preview'):
        conversation = llm._convert_conversation(agent._constract_conversation(job['reference'], job['generated']))
        print(json.dumps({'status': 'preview', 'messages': len(conversation),
                          'parts': [item['type'] for item in conversation[0]['content']]}))
        return
    response = agent.run(job['reference'], job['generated'])
    if response is None:
        raise RuntimeError('official_judge_no_response; original_exception_in_worker_log')
    Path(job['response']).write_text(response + '\n')
    data = json.loads(response)
    print(json.dumps({'status': 'responded', 'finish_reason': data['choices'][0]['finish_reason']}))


if __name__ == '__main__':
    run(json.loads(Path(sys.argv[1]).read_text()))
