"""Opt-in Kouri Luna route through Harness's public pi-ai adapter.

Official specs: https://developers.openai.com/api/docs/models/gpt-6-luna
Chat Completions function calls require reasoning_effort=none. Prices in the
isolated model config are official reference estimates, never Kouri billing.
"""

MODEL = 'gpt-6-luna'
PROVIDER = 'kouri-luna'
MAX_TOKENS = 128000


def harness_patch(base_url):
    return {'id':'llm-pi-ai',
        'config':{'providers':{PROVIDER:{'api':'openai-completions',
            'apiKeyEnv':'DEEPSEEK_API_KEY','baseURL':base_url,'reasoning':'off',
            'compat':{'thinkingFormat':'openai','supportsReasoningEffort':True,
                      'maxTokensField':'max_completion_tokens','supportsStore':False},
            'models':[{'id':MODEL,'name':'GPT-6 Luna','contextWindow':1050000,
                'maxTokens':MAX_TOKENS,'input':['text','image'],
                'reasoningEfforts':{'off':'none','low':'low','high':'high','max':'max'}}]}}}}
