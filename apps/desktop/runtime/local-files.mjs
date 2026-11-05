const implementation = await import(process.platform === 'win32'
  ? './local-files-windows.mjs' : './local-files-posix.mjs');

export const openWorkspaceReader = implementation.openWorkspaceReader;
export const openReportWriter = implementation.openReportWriter;
