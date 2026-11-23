/** Isolated research tools and standard native skill discovery. */
import {readFileSync, appendFileSync} from 'node:fs';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {parse} from 'yaml';

export const name = 'geneloop-research-scope';
export const inject = ['agents', 'tools', 'skills'];

export function apply(ctx, config) {
  const allowed = new Set(config.allowedTools);
  const sourceHashes = new Map();
  if (config.skills.length) allowed.add('skill');
  for (const card of config.skills) {
    const source = readFileSync(join(card.path, 'SKILL.md'), 'utf8');
    const match = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)([\s\S]*)$/.exec(source);
    if (!match) throw Error('research_skill_frontmatter_missing');
    const meta = parse(match[1]);
    if (meta.name !== card.name || typeof meta.description !== 'string')
      throw Error('research_skill_metadata_changed');
    sourceHashes.set(card.name, createHash('sha256').update(source).digest('hex'));
    ctx.effect(() => ctx.skills.register({name: meta.name, description: meta.description,
      source: 'runtime', provider: 'geneloop-research',
      resourceBase: {kind: 'directory', path: card.resource_base ?? card.path}, content: match[2].trim(),
      invocation: {modelInvocable: true, userInvocable: true}}));
  }
  ctx.on('agent/created', ({agent}) => {
    agent.ctx.tools.restrict({allow: [...allowed]});
    agent.ctx.tools.guard(call => allowed.has(call.name) ? undefined : 'Tool is outside this research session');
  });
  ctx.on('tools/execute', async (execution, next) => {
    const result = await next();
    if (execution.name === 'skill' && result.isError !== true) {
      const card = config.skills.find(item => item.name === execution.arguments.name);
      if (card) appendFileSync(config.activationRecord, JSON.stringify({
        name: card.name, session_id: execution.agent?.session.id,
        source_sha256: sourceHashes.get(card.name),
        status: 'loaded', time: Date.now(),
      }) + '\n', {mode: 0o600});
    }
    return result;
  });
}
