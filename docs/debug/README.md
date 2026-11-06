# 调试与工程联调记录

此目录集中保存调试、排错、配置/提示审计、部署与工程联调记录。正式科研实验位于 `../experiments/`，私有输入、完整提示和原始日志位于 `.local/debug/<issue-id>/`。

## 历史路径索引

历史证书和 Git 快照可能保存原记录路径，可按下表定位当前文件。迁移保留原记录正文与失败证据，链接按当前位置更新。

| 原路径 | 当前记录 |
|---|---|
| `docs/efficiency-rsi-audit.md` | [efficiency-rsi-audit.md](efficiency-rsi-audit.md) |
| `docs/experiments/all-scene-motif-execute-20261017-v1.md` | [all-scene-motif-execute-20261017-v1.md](all-scene-motif-execute-20261017-v1.md) |
| `docs/experiments/attachment-context-streaming-20261019.md` | [attachment-context-streaming-20261019.md](attachment-context-streaming-20261019.md) |
| `docs/experiments/chat-session-recovery-20261014-v1.md` | [chat-session-recovery-20261014-v1.md](chat-session-recovery-20261014-v1.md) |
| `docs/experiments/clickable-generated-files-20261019.md` | [clickable-generated-files-20261019.md](clickable-generated-files-20261019.md) |
| `docs/experiments/concurrent-chat-20261020.md` | [concurrent-chat-20261020.md](concurrent-chat-20261020.md) |
| `docs/experiments/deepseek-real-api-smoke-20261009-v1.md` | [deepseek-real-api-smoke-20261009-v1.md](deepseek-real-api-smoke-20261009-v1.md) |
| `docs/experiments/distributed-motif-example-v1.md` | [distributed-motif-example-v1.md](distributed-motif-example-v1.md) |
| `docs/experiments/domain-release-20261031.md` | [domain-release-20261031.md](domain-release-20261031.md) |
| `docs/experiments/dsh-native-capabilities-20261021.md` | [dsh-native-capabilities-20261021.md](dsh-native-capabilities-20261021.md) |
| `docs/experiments/dynamic-web-tasks-20261009-v1.md` | [dynamic-web-tasks-20261009-v1.md](dynamic-web-tasks-20261009-v1.md) |
| `docs/experiments/efficiency-rsi-authoring-replay-20261102.md` | [efficiency-rsi-authoring-replay-20261102.md](efficiency-rsi-authoring-replay-20261102.md) |
| `docs/experiments/efficiency-rsi-feedback-20261102.md` | [efficiency-rsi-feedback-20261102.md](efficiency-rsi-feedback-20261102.md) |
| `docs/experiments/efficiency-rsi-measurement-20261102.md` | [efficiency-rsi-measurement-20261102.md](efficiency-rsi-measurement-20261102.md) |
| `docs/experiments/f02-protocol-local-20261024-v1.md` | [f02-protocol-local-20261024-v1.md](f02-protocol-local-20261024-v1.md) |
| `docs/experiments/file-management-workflow-free-20261013.md` | [file-management-workflow-free-20261013.md](file-management-workflow-free-20261013.md) |
| `docs/experiments/file-ppt-integration-20261019.md` | [file-ppt-integration-20261019.md](file-ppt-integration-20261019.md) |
| `docs/experiments/five-user-stress-20261020.md` | [five-user-stress-20261020.md](five-user-stress-20261020.md) |
| `docs/experiments/four-scenario-main-integration-20261014-v1.md` | [four-scenario-main-integration-20261014-v1.md](four-scenario-main-integration-20261014-v1.md) |
| `docs/experiments/gateway-oversize-drain-20261102.md` | [gateway-oversize-drain-20261102.md](gateway-oversize-drain-20261102.md) |
| `docs/experiments/geneloop-attachment-inheritance-20261018.md` | [geneloop-attachment-inheritance-20261018.md](geneloop-attachment-inheritance-20261018.md) |
| `docs/experiments/geneloop-chat-lifecycle-20261018.md` | [geneloop-chat-lifecycle-20261018.md](geneloop-chat-lifecycle-20261018.md) |
| `docs/experiments/geneloop-common-capabilities-20261017.md` | [geneloop-common-capabilities-20261017.md](geneloop-common-capabilities-20261017.md) |
| `docs/experiments/geneloop-comparison-responsive-20261015-v1.md` | [geneloop-comparison-responsive-20261015-v1.md](geneloop-comparison-responsive-20261015-v1.md) |
| `docs/experiments/geneloop-composer-activity-20261016-v1.md` | [geneloop-composer-activity-20261016-v1.md](geneloop-composer-activity-20261016-v1.md) |
| `docs/experiments/geneloop-composer-switching-20261017.md` | [geneloop-composer-switching-20261017.md](geneloop-composer-switching-20261017.md) |
| `docs/experiments/geneloop-conversation-workflow-20261015-v1.md` | [geneloop-conversation-workflow-20261015-v1.md](geneloop-conversation-workflow-20261015-v1.md) |
| `docs/experiments/geneloop-delivery-20261015-v1.md` | [geneloop-delivery-20261015-v1.md](geneloop-delivery-20261015-v1.md) |
| `docs/experiments/geneloop-delivery-file-cards-20261016-v1.md` | [geneloop-delivery-file-cards-20261016-v1.md](geneloop-delivery-file-cards-20261016-v1.md) |
| `docs/experiments/geneloop-desktop-20261103.md` | [geneloop-desktop-20261103.md](geneloop-desktop-20261103.md) |
| `docs/experiments/geneloop-desktop-independent-20261103.md` | [geneloop-desktop-independent-20261103.md](geneloop-desktop-independent-20261103.md) |
| `docs/experiments/geneloop-file-main-integration-20261019.md` | [geneloop-file-main-integration-20261019.md](geneloop-file-main-integration-20261019.md) |
| `docs/experiments/geneloop-instant-model-picker-20261015-v1.md` | [geneloop-instant-model-picker-20261015-v1.md](geneloop-instant-model-picker-20261015-v1.md) |
| `docs/experiments/geneloop-instant-submit-unlimited-20261016-v1.md` | [geneloop-instant-submit-unlimited-20261016-v1.md](geneloop-instant-submit-unlimited-20261016-v1.md) |
| `docs/experiments/geneloop-live-workflow-20261015-v1.md` | [geneloop-live-workflow-20261015-v1.md](geneloop-live-workflow-20261015-v1.md) |
| `docs/experiments/geneloop-message-privacy-20261015-v1.md` | [geneloop-message-privacy-20261015-v1.md](geneloop-message-privacy-20261015-v1.md) |
| `docs/experiments/geneloop-native-image-scenes-20261016-v1.md` | [geneloop-native-image-scenes-20261016-v1.md](geneloop-native-image-scenes-20261016-v1.md) |
| `docs/experiments/geneloop-paired-progress-20261018.md` | [geneloop-paired-progress-20261018.md](geneloop-paired-progress-20261018.md) |
| `docs/experiments/geneloop-ppt-numeric-source-20261016-v1.md` | [geneloop-ppt-numeric-source-20261016-v1.md](geneloop-ppt-numeric-source-20261016-v1.md) |
| `docs/experiments/geneloop-reasoning-strength-slider-20261017-v1.md` | [geneloop-reasoning-strength-slider-20261017-v1.md](geneloop-reasoning-strength-slider-20261017-v1.md) |
| `docs/experiments/geneloop-reply-actions-20261015-v1.md` | [geneloop-reply-actions-20261015-v1.md](geneloop-reply-actions-20261015-v1.md) |
| `docs/experiments/geneloop-scene-clear-20261015-v1.md` | [geneloop-scene-clear-20261015-v1.md](geneloop-scene-clear-20261015-v1.md) |
| `docs/experiments/geneloop-scene-delivery-repair-20261016-v1.md` | [geneloop-scene-delivery-repair-20261016-v1.md](geneloop-scene-delivery-repair-20261016-v1.md) |
| `docs/experiments/geneloop-scene-stream-attachments-20261015-v1.md` | [geneloop-scene-stream-attachments-20261015-v1.md](geneloop-scene-stream-attachments-20261015-v1.md) |
| `docs/experiments/geneloop-server-source-reconciliation-20261017.md` | [geneloop-server-source-reconciliation-20261017.md](geneloop-server-source-reconciliation-20261017.md) |
| `docs/experiments/geneloop-settings-model-loading-20261015-v1.md` | [geneloop-settings-model-loading-20261015-v1.md](geneloop-settings-model-loading-20261015-v1.md) |
| `docs/experiments/geneloop-three-scene-quality-20261016-v1.md` | [geneloop-three-scene-quality-20261016-v1.md](geneloop-three-scene-quality-20261016-v1.md) |
| `docs/experiments/geneloop-unified-trajectory-20261016-v1.md` | [geneloop-unified-trajectory-20261016-v1.md](geneloop-unified-trajectory-20261016-v1.md) |
| `docs/experiments/geneloop-user-scene-flow-20261015-v1.md` | [geneloop-user-scene-flow-20261015-v1.md](geneloop-user-scene-flow-20261015-v1.md) |
| `docs/experiments/geneloop-workspace-trash-20261015-v1.md` | [geneloop-workspace-trash-20261015-v1.md](geneloop-workspace-trash-20261015-v1.md) |
| `docs/experiments/geneloop-workspaces-scenes-20261015-v1.md` | [geneloop-workspaces-scenes-20261015-v1.md](geneloop-workspaces-scenes-20261015-v1.md) |
| `docs/experiments/general-agent-tools-20261019.md` | [general-agent-tools-20261019.md](general-agent-tools-20261019.md) |
| `docs/experiments/harless-controls-20261013-v1.md` | [harless-controls-20261013-v1.md](harless-controls-20261013-v1.md) |
| `docs/experiments/harless-launch-readiness-20261014-v1.md` | [harless-launch-readiness-20261014-v1.md](harless-launch-readiness-20261014-v1.md) |
| `docs/experiments/harless-scenes-runtime-20261013-v1.md` | [harless-scenes-runtime-20261013-v1.md](harless-scenes-runtime-20261013-v1.md) |
| `docs/experiments/harness-web-v1-20261009.md` | [harness-web-v1-20261009.md](harness-web-v1-20261009.md) |
| `docs/experiments/invites-ratings-20261020.md` | [invites-ratings-20261020.md](invites-ratings-20261020.md) |
| `docs/experiments/literature-web-binding-20261012.md` | [literature-web-binding-20261012.md](literature-web-binding-20261012.md) |
| `docs/experiments/mode-controls-20261021.md` | [mode-controls-20261021.md](mode-controls-20261021.md) |
| `docs/experiments/native-chat-confirm-20261009-v1.md` | [native-chat-confirm-20261009-v1.md](native-chat-confirm-20261009-v1.md) |
| `docs/experiments/owner-access-recovery-20261019.md` | [owner-access-recovery-20261019.md](owner-access-recovery-20261019.md) |
| `docs/experiments/paper-main-integration-20261016-v1.md` | [paper-main-integration-20261016-v1.md](paper-main-integration-20261016-v1.md) |
| `docs/experiments/paper-motif-shadow-execute-20261009-v1.md` | [paper-motif-shadow-execute-20261009-v1.md](paper-motif-shadow-execute-20261009-v1.md) |
| `docs/experiments/paper-rsi-main-compat-20261021-v1.md` | [paper-rsi-main-compat-20261021-v1.md](paper-rsi-main-compat-20261021-v1.md) |
| `docs/experiments/pdf-ocr-vision-20261018.md` | [pdf-ocr-vision-20261018.md](pdf-ocr-vision-20261018.md) |
| `docs/experiments/postdeploy-stress-20261031.md` | [postdeploy-stress-20261031.md](postdeploy-stress-20261031.md) |
| `docs/experiments/ppt-library-transfer-20261014-v1.md` | [ppt-library-transfer-20261014-v1.md](ppt-library-transfer-20261014-v1.md) |
| `docs/experiments/ppt-read-receipt-fix-20261103.md` | [ppt-read-receipt-fix-20261103.md](ppt-read-receipt-fix-20261103.md) |
| `docs/experiments/pr121-windows-ci-20261102.md` | [pr121-windows-ci-20261102.md](pr121-windows-ci-20261102.md) |
| `docs/experiments/provider-output-20261020.md` | [provider-output-20261020.md](provider-output-20261020.md) |
| `docs/experiments/release-readiness-20261031.md` | [release-readiness-20261031.md](release-readiness-20261031.md) |
| `docs/experiments/research-ppt-frontend-rsi-20261014.md` | [research-ppt-frontend-rsi-20261014.md](research-ppt-frontend-rsi-20261014.md) |
| `docs/experiments/research-ppt-native-chat-20261014.md` | [research-ppt-native-chat-20261014.md](research-ppt-native-chat-20261014.md) |
| `docs/experiments/research-ppt-v17-release-preparation-20261013.md` | [research-ppt-v17-release-preparation-20261013.md](research-ppt-v17-release-preparation-20261013.md) |
| `docs/experiments/research-ppt-v17-web-integration-20261013.md` | [research-ppt-v17-web-integration-20261013.md](research-ppt-v17-web-integration-20261013.md) |
| `docs/experiments/research-report-agent-main-integration-20261012.md` | [research-report-agent-main-integration-20261012.md](research-report-agent-main-integration-20261012.md) |
| `docs/experiments/script-receipt-transport-20261023-v1.md` | [script-receipt-transport-20261023-v1.md](script-receipt-transport-20261023-v1.md) |
| `docs/experiments/server-python310-free-loop-20261009-v1.md` | [server-python310-free-loop-20261009-v1.md](server-python310-free-loop-20261009-v1.md) |
| `docs/experiments/shared-invite-20261103.md` | [shared-invite-20261103.md](shared-invite-20261103.md) |
| `docs/experiments/slash-member-recovery-20261014-v1.md` | [slash-member-recovery-20261014-v1.md](slash-member-recovery-20261014-v1.md) |
| `docs/experiments/trained-three-scenes-20261014-v1.md` | [trained-three-scenes-20261014-v1.md](trained-three-scenes-20261014-v1.md) |
| `docs/experiments/unified-service-lifecycle-20261019.md` | [unified-service-lifecycle-20261019.md](unified-service-lifecycle-20261019.md) |
| `docs/experiments/upload-capacity-context-20261103.md` | [upload-capacity-context-20261103.md](upload-capacity-context-20261103.md) |
| `docs/experiments/video-web-integration-20261101.md` | [video-web-integration-20261101.md](video-web-integration-20261101.md) |
| `docs/experiments/windows-ci-compatibility.md` | [windows-ci-compatibility.md](windows-ci-compatibility.md) |
| `docs/experiments/windows-rsi-lock-20261012-v1.md` | [windows-rsi-lock-20261012-v1.md](windows-rsi-lock-20261012-v1.md) |
| `docs/prompt-audits/F00.md` | [F00.md](prompt-audits/F00.md) |
| `docs/prompt-audits/F02.md` | [F02.md](prompt-audits/F02.md) |
