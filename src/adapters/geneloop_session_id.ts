/** Session identities admitted by the Harness and the Web task workbench. */
export function isExecutionSessionId(value: unknown): value is string {
  return typeof value === 'string' && /^(?:session-[a-f0-9-]{36}|sss-[a-f0-9]{32})$/.test(value);
}
