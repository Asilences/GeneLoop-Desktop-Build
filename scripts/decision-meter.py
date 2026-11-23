"""Host-only stdin bridge to the existing account metadata lock."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.adapters.decision_accounting import account
if __name__=='__main__':
    try:
        data=json.load(sys.stdin);print(json.dumps(account(data['context_file'],data['event'])))
    except Exception as e:
        print(json.dumps({'error':type(e).__name__+': '+str(e)}));sys.exit(1)
