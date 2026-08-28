#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = ''
    process.stdin.setEncoding('utf8')
    process.stdin.on('data', (chunk) => { data += chunk })
    process.stdin.on('end', () => resolve(data))
    process.stdin.on('error', reject)
  })
}

function findRepoRoot(start) {
  let current = path.resolve(start || process.cwd())
  for (;;) {
    if (
      fs.existsSync(path.join(current, 'AGENTS.md')) &&
      fs.existsSync(path.join(current, 'scripts', 'ai', 'brain.py'))
    ) return current
    const parent = path.dirname(current)
    if (parent === current) return path.resolve(start || process.cwd())
    current = parent
  }
}

function stateFile(repoRoot, sessionId) {
  const safe = String(sessionId || 'unknown').replace(/[^a-zA-Z0-9._-]/g, '_')
  return path.join(repoRoot, '.agent-private', 'tooling', 'brain-gate', `${safe}.json`)
}

function readState(file) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch {
    return { ready: false, taskId: null, brainFailures: 0 }
  }
}

function writeState(file, state) {
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, `${JSON.stringify(state, null, 2)}\n`, 'utf8')
}

function normalizeSlashes(value) {
  return String(value || '').replace(/\\/g, '/')
}

function extractTaskId(prompt) {
  const match = String(prompt || '').match(/\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+-\d+\b/)
  return match?.[0] || null
}

function isBrainQuery(command) {
  const s = normalizeSlashes(command).toLowerCase()
  return /scripts\/ai\/brain\.py\s+query\b/.test(s)
}

function containsExplorationAlongsideBrain(command) {
  const s = normalizeSlashes(command).toLowerCase()
  const blocked = [
    /\bfind\s+/, /\brg\s+/, /\bgrep\s+/, /\bgit\s+(show|log)\b/,
    /\bcat\s+(src|frontend|backend)\//, /\bsed\s+-n\s+.*(src|frontend|backend)\//,
    /get-content\b.*(src|frontend|backend)[\\/]/,
  ]
  return blocked.some((re) => re.test(s))
}

function isStartupGit(command) {
  const s = normalizeSlashes(command).toLowerCase().trim()
  // Allow only the bounded startup Git facts, including compound forms.
  const cleaned = s
    .replace(/git\s+status\s+--short/g, '')
    .replace(/git\s+branch\s+--show-current/g, '')
    .replace(/git\s+rev-parse\s+(--short\s+)?head/g, '')
    .replace(/git\s+worktree\s+list/g, '')
    .replace(/echo\s+['\"]?---[^;&|]*['\"]?/g, '')
    .replace(/[;&|\s]/g, '')
  return cleaned === ''
}

function isTaskSpecReadCommand(command) {
  const s = normalizeSlashes(command).toLowerCase()
  const hasTaskPath = /docs\/ai\/tasks\/[a-z0-9._-]+\.md/.test(s)
  if (!hasTaskPath) return false
  return /\b(cat|type|sed|get-content)\b/.test(s)
}

function isBrainDiagnostic(command, failures) {
  if (!failures) return false
  const s = normalizeSlashes(command).toLowerCase().trim()
  return (
    /^(py\s+-3\.12|python3?|node)\s+--version\b/.test(s) ||
    /^where(\.exe)?\s+(py|python|node)\b/.test(s) ||
    /^get-command\s+(py|python|node)\b/.test(s)
  )
}

function isAllowedRead(filePath, failures) {
  const p = normalizeSlashes(filePath).toLowerCase()
  if (/\/docs\/ai\/tasks\/[^/]+\.md$/.test(p)) return true
  if (/\/(agents|claude)\.md$/.test(p)) return true
  if (failures > 0) {
    if (p.endsWith('/docs/ai/runtime_contract.md')) return true
    if (p.endsWith('/scripts/ai/brain.py')) return true
    if (p.endsWith('/.python-version')) return true
  }
  return false
}

function deny(reason) {
  process.stderr.write(`${reason}\n`)
  process.exit(2)
}

async function main() {
  const mode = process.argv[2] || ''
  const raw = await readStdin()
  const input = raw.trim() ? JSON.parse(raw) : {}
  const repoRoot = findRepoRoot(input.cwd || process.cwd())
  const file = stateFile(repoRoot, input.session_id)
  const state = readState(file)

  if (mode === 'session-start') {
    writeState(file, { ready: false, taskId: null, brainFailures: 0 })
    return
  }

  if (mode === 'prompt') {
    const taskId = extractTaskId(input.prompt)
    if (taskId && taskId !== state.taskId) {
      writeState(file, { ready: false, taskId, brainFailures: 0 })
    } else if (!fs.existsSync(file)) {
      writeState(file, { ready: false, taskId, brainFailures: 0 })
    }
    return
  }

  if (mode === 'post') {
    const command = input?.tool_input?.command || ''
    if ((input.tool_name === 'Bash' || input.tool_name === 'PowerShell') && isBrainQuery(command)) {
      writeState(file, { ...state, ready: true, brainFailures: 0, brainReadyAt: new Date().toISOString() })
    }
    return
  }

  if (mode === 'failure') {
    const command = input?.tool_input?.command || ''
    if ((input.tool_name === 'Bash' || input.tool_name === 'PowerShell') && isBrainQuery(command)) {
      writeState(file, { ...state, ready: false, brainFailures: (state.brainFailures || 0) + 1 })
    }
    return
  }

  if (mode === 'session-end') {
    try { fs.unlinkSync(file) } catch {}
    return
  }

  if (mode !== 'pre' || state.ready) return

  const tool = input.tool_name
  if (tool === 'Read') {
    if (isAllowedRead(input?.tool_input?.file_path, state.brainFailures || 0)) return
    deny('Repo Brain gate: source reads are blocked until one Repo Brain query succeeds. Read the active task spec, then run: py -3.12 scripts/ai/brain.py query "<task-id> <goal>" --top 12')
  }

  if (tool === 'Bash' || tool === 'PowerShell') {
    const command = input?.tool_input?.command || ''
    if (isBrainQuery(command) && !containsExplorationAlongsideBrain(command)) return
    if (isStartupGit(command)) return
    if (isTaskSpecReadCommand(command)) return
    if (isBrainDiagnostic(command, state.brainFailures || 0)) return
    deny('Repo Brain gate: shell exploration is blocked until one Repo Brain query succeeds. Allowed first: bounded Git state, active task spec, then Brain query. Canonical Windows command: $env:PYTHONIOENCODING="utf-8"; py -3.12 scripts/ai/brain.py query "<task-id> <goal>" --top 12')
  }

  // These tools can directly explore or mutate repository content.
  if (['Glob', 'Grep', 'Agent', 'Edit', 'Write'].includes(tool)) {
    deny(`Repo Brain gate: ${tool} is blocked until one Repo Brain query succeeds.`)
  }
}

main().catch((error) => {
  // A policy hook must fail closed. Exit 2 is the only universally blocking
  // command-hook failure code for PreToolUse.
  process.stderr.write(`Repo Brain gate internal error: ${error?.stack || error}\n`)
  process.exit(2)
})
