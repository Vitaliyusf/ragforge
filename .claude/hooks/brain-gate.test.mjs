import test from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const hook = path.resolve(path.dirname(fileURLToPath(import.meta.url)), 'brain-gate.mjs')

function run(root, mode, input) {
  const result = spawnSync(process.execPath, [hook, mode], {
    cwd: root,
    input: JSON.stringify(input),
    encoding: 'utf8',
  })
  if (result.error) throw result.error
  return result
}

function expectStatus(result, expected) {
  assert.equal(
    result.status,
    expected,
    `hook exit mismatch (expected ${expected}, got ${result.status})\nstdout: ${result.stdout || '<empty>'}\nstderr: ${result.stderr || '<empty>'}\nhook: ${hook}`,
  )
}

function fixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'brain-gate-'))
  fs.mkdirSync(path.join(root, 'scripts', 'ai'), { recursive: true })
  fs.writeFileSync(path.join(root, 'AGENTS.md'), '# test\n')
  fs.writeFileSync(path.join(root, 'scripts', 'ai', 'brain.py'), '# test\n')
  fs.mkdirSync(path.join(root, 'docs', 'ai', 'tasks'), { recursive: true })
  fs.writeFileSync(path.join(root, 'docs', 'ai', 'tasks', 'CHAT-01.md'), '# task\n')
  fs.mkdirSync(path.join(root, 'frontend', 'src'), { recursive: true })
  fs.writeFileSync(path.join(root, 'frontend', 'src', 'App.jsx'), 'export default 1\n')
  return root
}

const session = 'session-test'

test('blocks exploration before Brain', () => {
  const root = fixture()
  run(root, 'session-start', { cwd: root, session_id: session })
  const r = run(root, 'pre', { cwd: root, session_id: session, tool_name: 'Bash', tool_input: { command: 'find frontend -type f' } })
  expectStatus(r, 2)
  assert.match(r.stderr, /Brain gate/)
})

test('allows task spec and bounded git before Brain', () => {
  const root = fixture()
  run(root, 'session-start', { cwd: root, session_id: session })
  let r = run(root, 'pre', { cwd: root, session_id: session, tool_name: 'Read', tool_input: { file_path: path.join(root, 'docs', 'ai', 'tasks', 'CHAT-01.md') } })
  expectStatus(r, 0)
  r = run(root, 'pre', { cwd: root, session_id: session, tool_name: 'Bash', tool_input: { command: 'git status --short && git branch --show-current && git rev-parse HEAD' } })
  expectStatus(r, 0)
})

test('successful Brain query opens gate', () => {
  const root = fixture()
  run(root, 'session-start', { cwd: root, session_id: session })
  const command = 'py -3.12 scripts/ai/brain.py query "CHAT-01 goal" --top 12'
  let r = run(root, 'pre', { cwd: root, session_id: session, tool_name: 'Bash', tool_input: { command } })
  expectStatus(r, 0)
  r = run(root, 'post', { cwd: root, session_id: session, tool_name: 'Bash', tool_input: { command } })
  expectStatus(r, 0)
  r = run(root, 'pre', { cwd: root, session_id: session, tool_name: 'Bash', tool_input: { command: 'find frontend -type f' } })
  expectStatus(r, 0)
})

test('failed Brain query does not open gate', () => {
  const root = fixture()
  run(root, 'session-start', { cwd: root, session_id: session })
  const command = 'py -3.12 scripts/ai/brain.py query "CHAT-01 goal" --top 12'
  run(root, 'failure', { cwd: root, session_id: session, tool_name: 'Bash', tool_input: { command }, error: 'Exit code 1' })
  const r = run(root, 'pre', { cwd: root, session_id: session, tool_name: 'Read', tool_input: { file_path: path.join(root, 'frontend', 'src', 'App.jsx') } })
  expectStatus(r, 2)
})

test('new task id resets an open gate', () => {
  const root = fixture()
  run(root, 'session-start', { cwd: root, session_id: session })
  const command = 'py -3.12 scripts/ai/brain.py query "CHAT-01 goal" --top 12'
  run(root, 'post', { cwd: root, session_id: session, tool_name: 'Bash', tool_input: { command } })
  run(root, 'prompt', { cwd: root, session_id: session, prompt: 'Implement FILES-LIST-01 now.' })
  const r = run(root, 'pre', { cwd: root, session_id: session, tool_name: 'Grep', tool_input: { pattern: 'foo' } })
  expectStatus(r, 2)
})
