"""Research-only finite admission over the unchanged cumulative provider ledger."""
from __future__ import annotations
from decimal import Decimal
import json
from pathlib import Path
import time

from src.adapters.capability_proposal import CumulativeProposalGate,append,sha
from src.adapters.deepseek_cost_gate import reservation,observed_peak_cost


class ResearchBudget:
    def __init__(self,limit):
        self.limit=Decimal(str(limit));self.spent=Decimal(0);self.pending={}
        if not self.limit.is_finite() or self.limit<0:raise ValueError('frontier_budget_invalid')

    def available(self,reserved):
        return self.spent+sum(self.pending.values(),Decimal(0))+reserved<=self.limit

    def book(self,rid,reserved):
        if rid in self.pending or not self.available(reserved):raise ValueError('frontier_budget_admission_changed')
        self.pending[rid]=reserved

    def finish(self,rid,cost):
        reserved=self.pending.pop(rid)
        # An unknown request remains fully reserved, including after failure.
        self.spent+=reserved if cost is None else cost


class StudyEpisodeRegistry:
    """Pre-book one measured acquisition episode including inner repairs.

    Initial exposure is frozen by the study. Actual intermediate pools and
    material acquisitions remain in the separate improvement journal.
    """
    def __init__(self,registry,path,owner_id,cell_id):
        self.registry=registry;self.path=Path(path).resolve();self.owner_id=owner_id;self.cell_id=cell_id;self.children=set()
        registry.register_owner(self.path,owner_id,cell_id=cell_id)

    def register_owner(self,path,owner_id,*,cell_id=None,category=None):
        path=Path(path).resolve()
        if not path.is_relative_to(self.path) or path==self.path or cell_id!=self.cell_id or category is not None or path in self.children:
            raise ValueError('frontier_episode_child_invalid')
        self.children.add(path)

    def owner_for_path(self,path):
        if Path(path).resolve() not in self.children:raise ValueError('frontier_episode_child_unregistered')
        return self.registry.owner_for_path(self.path)

    def bind_request(self,path,ledger_ref,request_id):
        self.owner_for_path(path);self.registry.bind_request(self.path,ledger_ref,request_id)


class FrontierGate(CumulativeProposalGate):
    def __init__(self,ledger_root,journal,*,deadline,study_registry=None):
        super().__init__(ledger_root,study_registry=study_registry)
        self.journal=Path(journal);self.deadline=deadline;self.budget=None;self.cell=None
        self.owners={};self.request_cells={};self.exact_costs={};self.budgets={}

    def activate(self,cell,limit):
        if self.current is not None:raise ValueError('frontier_active_attempt')
        self.cell=cell
        if cell not in self.budgets:
            budget=ResearchBudget(limit)
            if self.journal.exists():
                raw=self.journal.read_text(encoding='utf-8')
                if not raw.endswith('\n'):raise ValueError('frontier_budget_journal_incomplete')
                for row in map(json.loads,raw.splitlines()):
                    if row.get('cell')!=cell:continue
                    if row['event']=='cell_activated' and Decimal(row['budget_usd'])!=budget.limit:raise ValueError('frontier_budget_changed')
                    if row['event']=='request_booked':budget.book(row['request_id'],Decimal(row['reserved_upper_usd']))
                    if row['event']=='request_settled':budget.finish(row['request_id'],Decimal(row['observed_model_usd']) if row['observed_model_usd'] is not None else None)
            self.budgets[cell]=budget
        self.budget=self.budgets[cell]
        if self.budget.limit!=Decimal(str(limit)):raise ValueError('frontier_budget_changed')
        append(self.journal,{'event':'cell_activated','cell':cell,'budget_usd':str(self.budget.limit),'time':time.time()})

    def register_attempt(self,path,owner_id,*,category=None):
        path=str(Path(path).resolve())
        if path in self.owners:raise ValueError('frontier_owner_already_registered')
        if self.cell is None:raise ValueError('frontier_cell_required')
        self.owners[path]={'owner_id':owner_id,'cell':self.cell,'category':category}
        if self.study_registry:self.study_registry.register_owner(path,owner_id,cell_id=self.cell)
        if isinstance(self.study_registry,StudyEpisodeRegistry):self.owners[path]['study_episode_owner']=self.study_registry.owner_id
        append(self.journal,{'event':'owner_registered','path':path,**self.owners[path],'time':time.time()})

    def __enter__(self):
        super().__enter__();native_book,native_log=self.state.book,self.state.log
        def book(body):
            path=str(self.current)
            if path not in self.owners or self.owners[path]['cell']!=self.cell:raise ValueError('frontier_request_owner_unregistered')
            model,_,ceiling=reservation(body,max_output=self.state.output_cap,rates=self.state.rates)
            request=json.loads(body);input_rate,output_rate=self.state.rates[model]
            reserve=(Decimal(ceiling)*Decimal(str(input_rate))+Decimal(request['max_tokens'])*Decimal(str(output_rate)))/Decimal(1000000)
            if time.time()>=self.deadline or not self.budget.available(reserve):
                append(self.journal,{'event':'admission_denied','path':path,'cell':self.cell,
                    'reason':'deadline' if time.time()>=self.deadline else 'research_upper_reservation',
                    'reserved_upper_usd':str(reserve),'time':time.time()})
                return None
            result=native_book(body)
            if result:
                rid=result[0];self.budget.book(rid,reserve);self.request_cells[rid]=self.cell
                append(self.journal,{'event':'request_booked','request_id':rid,'ledger_ref':str(self.root/'cost-ledger.jsonl'),
                    **self.owners[path],'path':path,'body_sha256':sha(body),'reserved_upper_usd':str(reserve),'time':time.time()})
            return result
        def log(row):
            native_log(row);rid=row.get('request_id')
            if rid not in self.request_cells:return
            cell=self.request_cells[rid];cost=None;usage=row.get('response_usage',{})
            if row.get('response_status')==200:
                try:
                    observed_peak_cost(row['model'],usage,rates=self.state.rates,cache_rates=self.state.cache_rates)
                    ir,orr=self.state.rates[row['model']];hr=self.state.cache_rates[row['model']]
                    cost=(Decimal(usage['prompt_cache_hit_tokens'])*Decimal(str(hr))+
                          Decimal(usage['prompt_cache_miss_tokens'])*Decimal(str(ir))+
                          Decimal(usage['completion_tokens'])*Decimal(str(orr)))/Decimal(1000000)
                except (ValueError,KeyError):pass
            self.budgets[cell].finish(rid,cost);self.exact_costs[rid]=cost
            append(self.journal,{'event':'request_settled','request_id':rid,'cell':cell,
                'observed_model_usd':str(cost) if cost is not None else None,'time':time.time()})
        self.state.book,self.state.log=book,log
        return self

    def costs(self,attempt):
        result=super().costs(attempt);amounts=[self.exact_costs.get(rid) for rid in result['request_ids']]
        total=sum(amounts,Decimal(0)) if all(v is not None for v in amounts) else None
        return {**result,'observed_model_usd':float(total) if total is not None else None,
                'observed_model_usd_decimal':str(total) if total is not None else None,
                'research_cell':self.cell,'research_budget_usd':str(self.budget.limit)}
