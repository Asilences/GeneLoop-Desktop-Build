const common = ['local_list', 'local_read', 'local_search', 'local_save_report', 'local_document_pin', 'local_document_read'];
const extra = {
  chat: [],
  ppt: ['local_ppt_create', 'local_paper_read_page', 'local_ppt_master_guide', 'local_ppt_master_export', 'local_ppt_read_material', 'local_ppt_fill_template', 'local_ppt_edit_template', 'local_ppt_pin_source', 'local_ppt_read_source'],
  video: ['local_video_probe', 'local_video_render', 'hybrid_video_render'],
  files: ['local_files_export'],
  data: ['local_data_summarize', 'local_data_inspect', 'local_data_analyze'],
  paper: ['local_paper_read_page', 'local_paper_check_citations', 'local_paper_audit_sources'],
};

export function localSceneTools(scene) {
  return typeof scene === 'string' && Object.hasOwn(extra, scene) ? [...common, ...extra[scene]] : null;
}
