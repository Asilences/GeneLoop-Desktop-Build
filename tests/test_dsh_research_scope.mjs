/** Real native skill service and tool diagnostics, no model/provider calls. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, mkdirSync, writeFileSync, readFileSync, realpathSync, rmSync, existsSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createHash, randomUUID} from 'node:crypto';
import {Context} from '@deepseek-ai/cordis';
import {AgentRegistry} from '@deepseek-ai/dsh-agent';
import {AgentLoop} from '@deepseek-ai/dsh-agent-loop';
import {SessionStore} from '@deepseek-ai/dsh-session';
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection';
import {SystemPrompt} from '@deepseek-ai/dsh-system-prompt';
import {ToolRuntime} from '@deepseek-ai/dsh-tools';
import {LlmRuntime} from '@deepseek-ai/dsh-llm';
import {SkillRegistry} from '@deepseek-ai/dsh-skill';
import {LocalFileSystem} from '@deepseek-ai/dsh-fs-local';
import {apply as skillTool} from '@deepseek-ai/dsh-tool-skill';
import {apply as researchScope} from '../src/adapters/dsh_research_scope.mjs';

const sha = value => createHash('sha256').update(value).digest('hex');

async function fixture({install = true} = {}) {
  const root = realpathSync(mkdtempSync(join(tmpdir(), 'geneloop-research-scope-')));
  const ctx = new Context();
  new SessionStore(ctx);
  new AgentRegistry(ctx);
  new SessionProjectionRegistry(ctx);
  new SystemPrompt(ctx, {});
  new ToolRuntime(ctx, {});
  new LlmRuntime(ctx);
  new SkillRegistry(ctx);
  new LocalFileSystem(ctx, {cwd: root, diffBasisMaxBytes: 1024 * 1024});
  const loop = new AgentLoop(ctx, {agents: []});
  skillTool(ctx);
  ctx.tools.register({name: 'mcp__research__inspect_archive', description: 'Synthetic archive tool',
    parameters: {}, output: {schema: {type: 'object'},
      render: (_args, value) => [{type: 'text', text: JSON.stringify(value)}]},
    async execute() { return {}; }});
  const path = join(root, 'skill');
  mkdirSync(path);
  const content = '---\nname: research-procedure\ndescription: Investigate recorded task execution\n---\n# Procedure\nRead the relevant evidence before proposing a change.\n';
  writeFileSync(join(path, 'SKILL.md'), content);
  const activationRecord = join(root, 'skill-activations.jsonl');
  const config = {allowedTools: ['mcp__research__inspect_archive'],
    skills: install ? [{name: 'research-procedure', description: 'Investigate recorded task execution', path}] : [],
    activationRecord};
  researchScope(ctx, config);
  const agent = await loop.create('research-' + randomUUID(), {provider: 'unused', model: 'unused'}, {cwd: root});
  agent.session.append('turn/start', {turn: 1});
  return {root, ctx, agent, path, config, content, activationRecord,
    execute: (name, arguments_) => ctx.tools.execute({name, arguments: arguments_, agent,
      callId: randomUUID(), signal: new AbortController().signal}),
    async close() {
      await ctx.fiber.dispose();
      rmSync(root, {recursive: true, force: true});
    }};
}

test('native catalog exposes descriptions and skill tool actually loads package with evidence', async () => {
  const f = await fixture();
  try {
    const catalog = await f.ctx.skills.list({cwd: f.root});
    assert.deepEqual(catalog.map(row => row.name), ['research-procedure']);
    assert.equal(catalog[0].description, 'Investigate recorded task execution');
    assert.equal('content' in catalog[0], false);
    assert.equal(existsSync(f.activationRecord), false);
    const loaded = await f.execute('skill', {name: 'research-procedure'});
    assert.equal(loaded.isError, false);
    assert.match(loaded.value.content, /Read the relevant evidence/);
    assert.equal(loaded.value.resourceBase.path, f.path);
    const rows = readFileSync(f.activationRecord, 'utf8').trim().split('\n').map(JSON.parse);
    assert.equal(rows.length, 1);
    assert.equal(rows[0].session_id, f.agent.session.id);
    assert.equal(rows[0].name, 'research-procedure');
    assert.equal(rows[0].status, 'loaded');
    assert.equal(rows[0].source_sha256, sha(f.content));
  } finally {
    await f.close();
  }
});

test('failed skill invocation is not recorded as activation', async () => {
  const f = await fixture();
  try {
    assert.equal((await f.execute('skill', {name: 'missing-skill'})).isError, true);
    assert.equal(existsSync(f.activationRecord), false);
  } finally {
    await f.close();
  }
});

test('empty skill catalog leaves no native skill invocation authority', async () => {
  const f = await fixture({install: false});
  try {
    assert.deepEqual(await f.ctx.skills.list({cwd: f.root}), []);
    assert.equal((await f.execute('skill', {name: 'research-procedure'})).isError, true);
    assert.equal(existsSync(f.activationRecord), false);
  } finally {
    await f.close();
  }
});

test('activation hashes the content actually registered rather than later disk bytes', async () => {
  const f = await fixture();
  try {
    writeFileSync(join(f.path, 'SKILL.md'), f.content + '\nLater unrelated edit.\n');
    const loaded = await f.execute('skill', {name: 'research-procedure'});
    assert.equal(loaded.isError, false);
    assert.doesNotMatch(loaded.value.content, /Later unrelated edit/);
    const receipt = JSON.parse(readFileSync(f.activationRecord, 'utf8').trim());
    assert.equal(receipt.source_sha256, sha(f.content));
  } finally {
    await f.close();
  }
});
