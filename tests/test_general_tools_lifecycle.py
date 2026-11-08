"""Actual stdio MCP lifecycle diagnostics. No model calls or memory claims."""
import asyncio,json,sys
from pathlib import Path
from uuid import uuid4
import pytest
from src.adapters.general_tools import Gateway,ROOT,FORMAT,save


@pytest.fixture
def gateway_files():
    root=ROOT/'.local/general-lifecycle-tests'/uuid4().hex
    work=root/'work';work.mkdir(parents=True)
    service=root/'service.py'
    service.write_text('''import asyncio,json,os,sys
from pathlib import Path
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
trace=Path(sys.argv[1]);pid=os.getpid()
with trace.open('a',encoding='utf8') as f:f.write(json.dumps({'pid':pid,'provider':sys.argv[2]})+'\\n')
s=MCPServer('lifecycle diagnostic')
async def inspect(delay:float=0):
    await asyncio.sleep(delay)
    return {'pid':pid,'provider':sys.argv[2]}
s.add_tool(inspect,annotations=ToolAnnotations(readOnlyHint=True))
if __name__=='__main__':s.run()
''',encoding='utf8')
    rows=[{'id':name,'description':name+' diagnostic','transport':'stdio','command':sys.executable,
           'args':[str(service),str(root/'starts.jsonl'),name],'policy':'read_only','cost':'local_no_model'}
          for name in ['alpha','beta','gamma']]
    registry=root/'providers.json';save(registry,{'format':FORMAT,'providers':rows})
    return work,registry,root/'starts.jsonl'


def test_discovery_never_starts_services_and_selected_catalog_only(gateway_files):
    work,registry,trace=gateway_files
    async def run():
        g=Gateway(work,{},public_registry=registry,config=work/'none.json')
        try:
            found=await g.discover_tools('a tool name unknown until connection')
            assert len(found['providers'])==3 and not trace.exists()
            assert all(p['available'] is None and p['connection_status']=='not_started' for p in found['providers'])
            selected=asyncio.create_task(g.describe_tool('beta'));await asyncio.sleep(0)
            during=next(p for p in (await g.discover_tools())['providers'] if p['provider_id']=='beta')
            assert during['available'] is None and during['connection_status']=='starting'
            actual=await selected
            assert [t['name'] for t in actual['tools']]==['inspect']
            assert [json.loads(line)['provider'] for line in trace.read_text().splitlines()]==['beta']
            cached=await g.discover_tools('inspect')
            beta=next(p for p in cached['providers'] if p['provider_id']=='beta')
            assert beta['catalog_source']=='cached_hint' and beta['tools'][0]['name']=='inspect'
            assert len(trace.read_text().splitlines())==1
        finally:await g.close()
    asyncio.run(run())


def test_idle_process_exits_and_old_preparation_cannot_run(gateway_files):
    work,registry,trace=gateway_files
    async def run():
        g=Gateway(work,{},public_registry=registry,config=work/'none.json',idle_seconds=.08)
        try:
            q=await g.prepare_tool_call('alpha','inspect',{})
            original=next(iter(g.clients.values()))
            await asyncio.wait_for(asyncio.shield(original.task),5)
            assert original.closing and original.task.done()
            assert (await g.discover_tools())['providers'][0]['connection_status']=='not_started'
            with pytest.raises(Exception,match='expired'):await g.execute_tool_call(q['request_id'])
            fresh=await g.prepare_tool_call('alpha','inspect',{})
            result=await g.execute_tool_call(fresh['request_id'])
            assert result['status']=='completed'
            await asyncio.wait_for(asyncio.shield(next(iter(g.clients.values())).task),5)
            assert await g.execute_tool_call(fresh['request_id'])==result
            starts=[json.loads(line) for line in trace.read_text().splitlines()]
            assert len(starts)==2 and starts[0]['pid']!=starts[1]['pid']
        finally:await g.close()
    asyncio.run(run())


def test_connection_cap_reuses_idle_slot_without_killing_busy_tool(gateway_files):
    work,registry,trace=gateway_files
    async def run():
        g=Gateway(work,{},public_registry=registry,config=work/'none.json',connection_limit=1,idle_seconds=.04)
        try:
            q=await g.prepare_tool_call('alpha','inspect',{'delay':.18})
            original=next(iter(g.clients.values()))
            running=asyncio.create_task(g.execute_tool_call(q['request_id']))
            await asyncio.sleep(.03)
            selected=asyncio.create_task(g.describe_tool('beta'))
            canceled=asyncio.create_task(g.describe_tool('gamma'))
            await asyncio.sleep(0);canceled.cancel()
            with pytest.raises(asyncio.CancelledError):await canceled
            await asyncio.sleep(.06)
            assert len(trace.read_text().splitlines())==1 and not original.task.done()
            assert (await running)['status']=='completed'
            await selected
            assert original.task.done() and len(g.clients)==1
            assert [json.loads(x)['provider'] for x in trace.read_text().splitlines()]==['alpha','beta']
            # Reconnecting cannot accidentally execute a prepared request against
            # a different provider instance even when its schema is unchanged.
            await g.describe_tool('gamma')
            assert len(g.clients)==1
        finally:await g.close()
    asyncio.run(run())


def test_shutdown_reaps_running_provider_and_does_not_replay_unknown_effects(gateway_files):
    work,registry,trace=gateway_files
    async def run():
        g=Gateway(work,{},public_registry=registry,config=work/'none.json')
        try:
            q=await g.prepare_tool_call('alpha','inspect',{'delay':30})
            client=next(iter(g.clients.values()))
            running=asyncio.create_task(g.execute_tool_call(q['request_id']))
            for _ in range(100):
                if g.request(q['request_id'])[0]['status']=='executing':break
                await asyncio.sleep(.01)
            assert g.request(q['request_id'])[0]['status']=='executing'
            await asyncio.wait_for(g.close(),5)
            result=await asyncio.wait_for(running,5)
            assert client.task.done() and result['status']=='transport_error'
            assert await g.execute_tool_call(q['request_id'])==result
            assert len(trace.read_text().splitlines())==1
        finally:await g.close()
    asyncio.run(run())
