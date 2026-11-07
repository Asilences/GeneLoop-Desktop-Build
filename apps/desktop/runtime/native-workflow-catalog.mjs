// Versioned allowlist shared by the model gateway and the local DSH scope.
// Actual argument schemas are discovered from the unchanged MCP providers.
export const workflowTools={
  gateway:['discover_tools','describe_tool','prepare_tool_call','execute_tool_call','inspect_tool_result'],
  management:['read_task','list_files','select_files','pin_file','read_file','collect_reads','hash_files','build_index','search_index','compare_snapshot','preview_actions',
    'execute_plan','inspect_plan_result','restore_plan','submit_report','pin_files','read_files','open_document','read_document_chunk','document_coverage','view_document_page','search_document',
    'discover_tools','describe_tool','prepare_tool_call','execute_tool_call','inspect_tool_result'],
  workspace:['list_files','read_file'],
  revision:['read_task_state','apply_revision_plan','triage_revision_audit','export_revision_report'],
  video:['list_assets','pin_asset','probe_media','probe_asset','read_source','inspect_render','write_source','render_composition','write_notes','render_source','run_command'],
  skill:['read_skill_entry','pin_source','read_source_page','convert_source','read_converted_source'],
  general:['runtime_capabilities','edit_text','create_text','execute_code'],
  report:['inspect_study','approve_analysis','run_analysis','verify_analysis','build_evidence','approve_presentation',
    'render_figures','verify_figures','submit_report_text','compose_report','layout_report','audit_layout','verify_report','deliver_report',
    'read_image_table','record_image_table','export_input_review'],
  paper:['list_inputs','pin_document','read_pinned_document','pin_paper_sources','read_pinned_paper_sources','export_review_report',
    'pin_paper_citations','read_pinned_paper_citations','read_pinned_citation_records','read_pinned_bibliography_page',
    'read_pinned_bibliography_first_page','collect_current_local_citation_evidence','fetch_pinned_cited_preprint_metadata',
    'fetch_pinned_formal_reference_metadata','recover_pinned_formal_reference_queries','read_current_audit','stage_current_audit',
    'stage_current_bibliography_assessments','finalize_current_audit','export_current_audit_pdf'],
  files:['read_task','list_files','pin_file','read_file','hash_files','build_index','search_index','compare_snapshot','preview_actions',
    'authorize_plan','execute_plan','restore_plan','submit_report'],
  ppt:['list_inputs','list_templates','pin_source','read_source','read_page','extract_figure','inspect_deck','deliver_deck',
    'read_deck_plan','list_restorable_decks','render_deck','restyle_deck','revise_deck','validate_deck','build_delivery',
    'render_delivery','revise_delivery','pin_deck_pages','read_pinned_deck_pages','read_pending_plan','repair_pending_plan'],
};
export const workflowKinds={chat:['general','workspace','gateway','report','paper','ppt','skill'],files:['files','management','gateway'],data:['report'],paper:['paper','revision'],ppt:['ppt','skill']};
export function workflowToolName(kind,name) {
  if(!workflowTools[kind]?.includes(name))throw Error('工作流工具未在当前版本准入。');
  return 'mcp__native_'+kind+'__'+name;
}
export const extendedWorkflowKinds=new Set(['workspace','revision','gateway','management']);
export function workflowSceneNames(scene,extended=true){return (scene==='video'?['video']:workflowKinds[scene]??[]).filter(kind=>extended||!extendedWorkflowKinds.has(kind)).flatMap(kind=>workflowTools[kind].map(name=>workflowToolName(kind,name)));}
