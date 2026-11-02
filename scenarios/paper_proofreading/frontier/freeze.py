"""Freeze task text, corpus, evaluator and research budgets before model calls."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from src.adapters.capability_scene import reference,ROOT
from scenarios.paper_proofreading.frontier.oracle import bibliography,latex,audit,compare,canonical,sha


DETAILS={
'bib':'''Read geneloop-project.json inside the ZIP for the project root. Inspect EVERY .bib in the archive (including ones not used by the root). Output exactly bib_files:[{path,sha256}], entries:[{path,key,sha256}]. Each file sha256 hashes its original bytes. Each entry hash hashes its complete raw brace-delimited @type{key,...} entry stripped of surrounding whitespace, UTF-8 encoded. Preserve duplicate keys as separate entries. Skip @comment, @string and @preamble. Handle nested braces, escaped characters and quoted field values. Do not execute TeX or expand BibTeX macros. Return compact JSON; do not emit source text or bibliography bodies.''',
'tex':'''Read geneloop-project.json inside the ZIP. Follow reachable literal input/include commands from its root; resolve paths from archive root and add .tex if absent. Inspect each reachable file once even for cycles. Collect literal bibliography/addbibresource edges (.bib suffix if absent), but do not parse bibliography entries. Ignore unescaped % comments; escaped percent signs remain text. Supported citation names: cite,citep,citet,citeauthor,citeyear,parencite,textcite,autocite, optional star and optional bracket arguments. Split literal comma-separated keys, deduplicate per (path,key), exclude wildcard * and arguments containing #, backslash or nested braces (macro expansion is out of scope). Output exactly root:string, tex_files:[{path,sha256}], includes:[{parent,child,exists}], bibliography:[{parent,child,exists}], citations:[{path,key}], unresolved:[missing include or bibliography path strings]. Record file hashes over original bytes. For a missing dependency record its edge with exists:false. Do not run TeX or read outside the ZIP.''',
'C':'''Build a higher-level citation-consistency capability from the certified bibliography and LaTeX extraction primitives. Preserve their parsing behavior; any new program may supply missing relational computation, not replace both parsers. Join bibliography entries ONLY from the existing bibliography edges in the reachable TeX result; inactive .bib files must not introduce false duplicates or unused entries. Output exactly root,files,includes,bibliography,citations,entries,missing,duplicates,unused,unresolved. files are reachable tex_files plus ACTIVE bib_files, each {path,sha256,kind:"tex"|"bib"}. includes,bibliography,citations,unresolved come from the reachable TeX analysis. entries retain active bibliography rows including duplicates. missing is the unique cited-key set minus active entry-key set; duplicates contains keys with more than one active entry; unused contains active entry keys with no literal citation. All three are lists of strings. This creates a joint consistency decision, not just two concatenated parser outputs. Arrays are collections; preserve multiplicity of duplicate entry records.''',
'D':'''Construct a reusable cross-version citation-consistency system. Input before and after are paths of two independent project ZIP versions. You may compose visible capabilities or write a complete ordinary Python program; use of C is optional and is NOT a success criterion. Output exactly before_root,after_root,changed_files,changed_entry_keys,affected_tex_files,before_files_digest,after_files_digest,after_has_errors,introduced_missing,resolved_missing,introduced_duplicates,resolved_duplicates,newly_unused,now_used. Use the C report semantics described in task.audit_semantics even if C is not visible. changed_files is paths with changed/added/removed hashes in the covered files collections. changed_entry_keys compares each key's sorted multiset of (path,entry sha256) records across versions. affected_tex_files includes directly changed covered .tex files, all .tex files citing a changed entry key in EITHER version, and their transitive ancestors through existing input/include/bibliography edges in EITHER version; do not mark every file affected merely because one key changed. introduced/resolved sets compare respective missing/duplicate key sets; newly_unused=after.unused-before.unused, now_used=before.unused-after.unused. after_has_errors is bool(after.missing or after.duplicates or after.unresolved), not unused warnings. For file digests: sort files records by their canonical JSON (sort dictionary keys, UTF-8, ensure_ascii=False, separators=(',',':')), then SHA256 the canonical JSON of that sorted array. The report must couple version changes to global citation/dependency effects, not concatenate two audits.'''}


def schema(example):
    if isinstance(example,dict):return {'type':'object','properties':{k:schema(v) for k,v in example.items()},'required':list(example),'additionalProperties':False}
    if isinstance(example,list):return {'type':'array'}
    return {'type':'boolean' if isinstance(example,bool) else 'number' if isinstance(example,(int,float)) else 'string'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);inputs=a.inputs.resolve()
    oracle_values={'bib':bibliography(inputs/'atc-v0.zip'),'tex':latex(inputs/'atc-v0.zip'),
                   'C':audit(inputs/'atc-v0.zip'),'D':compare(inputs/'atc-v0.zip',inputs/'atc-v1.zip')}
    refs={}
    for kind in DETAILS:
        interface={'modes':['paths'],'paths':['/work/inputs/project.zip'],
                   'archive_layout':'ZIP members retain original relative paths. geneloop-project.json contains root.'}
        input_schema={'type':'object','properties':{'project':{'type':'string'}},'required':['project'],'additionalProperties':False}
        if kind=='C':interface={'modes':['json'],'paths':['/work/inputs/value.json'],
            'value_context':'JSON object {bibliography:<bibliography extraction value>,latex:<LaTeX extraction value>}; actual native examples supplied after primitive certification.'}
        if kind=='D':
            interface={'modes':['paths','json'],'paths':['/work/inputs/before.zip','/work/inputs/after.zip'],
                'json_path':'/work/inputs/value.json','value_context':'JSON object {before:<audit report>,after:<audit report>}. Actual training examples supplied symmetrically after C certification.'}
            input_schema={'type':'object','properties':{'before':{'type':'string'},'after':{'type':'string'}},'required':['before','after'],'additionalProperties':False}
        task={'id':'frontier-'+kind,'instruction':DETAILS[kind],
              'contract':{'input_schema':input_schema,'output_schema':schema(oracle_values[kind]),'effects':['read']},
              'program_interface':interface,'literal_scope':'Static literal commands only; no TeX expansion or factual reference validation.'}
        if kind=='D':task['audit_semantics']=DETAILS['C']
        path=a.output/('task-'+kind+'.json');path.write_text(json.dumps(task,ensure_ascii=False,indent=2));refs[kind]=reference(path)
    files=['scenarios/paper_proofreading/frontier/oracle.py','src/adapters/paper_bibliography.py']
    plan={'format':'frontier_protocol_freeze_v1','experiment_id':'capability-frontier-20261103',
        'input_manifest':reference(inputs/'manifest.json'),'tasks':refs,'evaluator_files':[reference(ROOT/f) for f in files],
        'deadline_utc':'2026-11-02T23:48:00Z','phase_C_research_budget_usd':'2.00',
        'D_cell_research_budget_usd':'1.00','D_arms':['flat_without_C','hierarchical_with_C'],
        'D_replicates':[0,1],'D_order':['hierarchical_with_C/0','flat_without_C/0','flat_without_C/1','hierarchical_with_C/1'],
        'D_baseline_ordinary_python_allowed':True,'force_C':False,'model':'deepseek-flash','reasoning_effort':'off',
        'max_tokens':393216,'platform_cap_usd':None,'platform_request_limit':None,'reset_cumulative_ledger':False,
        'program_safety':'Existing admitted read-only Python subset, same in all arms',
        'candidate_timeout_seconds':45,'native_certification_timeout_seconds':180,
        'C_cost_scope':'Separate initial acquisition, including primitives and failed attempts; never claim a conditional D saving amortizes C',
        'D_cost_scope':'All D construction proposals, material acquisition, repair and validation; CPU/maintenance tracked but not monetized',
        'final_feedback_policy':'No final-test results enter repair; every frozen final case remains in the denominator',
        'final_test_inputs':[reference(inputs/f'qlora-v{i}.zip') for i in range(3)],
        'conditions_versioning':'Infrastructure fixes use new immutable code directories and new condition IDs; tasks and quality hashes stay fixed',
        'Direct_agent':'Not separately duplicated when identical to the no-high-level-C arm; both arms allow ordinary Python construction',
        'status':'frozen_before_any_frontier_model_call'}
    (a.output/'protocol.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2))
    print(json.dumps({'protocol':reference(a.output/'protocol.json'),'task_ids':list(refs),'evaluator_sha256':reference(ROOT/files[0])['sha256']}))


if __name__=='__main__':main()
