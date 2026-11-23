// Names only: shared by packaging, the gateway allowlist, and the native host.
export const commonToolNames=['web_search','web_fetch','bash','pwsh','job_list','job_output','job_kill','read','read_image',
  'write','edit','glob','grep','ask_user_question','todo_write','skill','present','subagent','exit_plan_mode','get_goal','update_goal'];
// Registered only by the upstream DSH child driver when outputSchema is used.
export const childToolNames=['structured_output'];
export const nativeCommonPackages=['dsh-fs-local','dsh-fs-observation-policy','dsh-tool-fs','dsh-tool-fs-search',
  'dsh-bash-sandbox','dsh-pwsh-sandbox','dsh-shell-env','dsh-tool-bash','dsh-tool-pwsh','dsh-tool-jobs',
  'dsh-user-questions','dsh-tool-ask-user','dsh-tool-todo','dsh-skill','dsh-skill-filesystem','dsh-tool-skill',
  'dsh-web','dsh-web-fetch-http','dsh-tool-web','dsh-goal','dsh-tool-goal','dsh-plan-mode',
  'dsh-subagent','dsh-subagent-spawn-in-process','dsh-tool-subagent','dsh-tool-present'].map(x=>'@deepseek-ai/'+x);
