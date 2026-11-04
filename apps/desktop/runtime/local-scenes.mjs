const common = ['local_list', 'local_read', 'local_search', 'local_save_report'];
const extra = {
  files: [],
  data: ['local_data_summarize'],
  paper: ['local_paper_read_page', 'local_paper_check_citations'],
};

export function localSceneTools(scene) {
  return typeof scene === 'string' && Object.hasOwn(extra, scene) ? [...common, ...extra[scene]] : null;
}
