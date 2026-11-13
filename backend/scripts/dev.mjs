// `npm run dev` for the Python backend (decision 0026). Finds the Python environment, then runs
//   api     python -m uvicorn app.main:app --reload --port 8000   (LOGIMIND_WORKER=inline unless set)
//   worker  python -m app.jobs.worker
//   test    python -m pytest -q
//   tenant  python manage.py create-tenant "<name>"   (prints the first API key once; only its hash is stored)
// Python is taken from LOGIMIND_PYTHON, else the venv in %TEMP%\lmv (CLAUDE.md), else backend/.venv or ../.venv,
// else python / python3 on the PATH. Settings are environment variables (see app/main.py); for local runs they
// can also live in backend/.env (git-ignored, see .env.example). Variables already set in the shell win.
// api also opens a Cloudflare quick tunnel for the deployed console when backend/.env asks for the public demo
// (LOGIMIND_PUBLIC_DEMO=1 and FRONTEND_URL; decision 0040) and prints the console link to open.
import { spawn, spawnSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const backend = join(dirname(fileURLToPath(import.meta.url)), '..')
const win = process.platform === 'win32'
const inVenv = (dir) => join(dir, win ? 'Scripts' : 'bin', win ? 'python.exe' : 'python')

function findPython() {
  if (process.env.LOGIMIND_PYTHON) return process.env.LOGIMIND_PYTHON
  const venvs = [join(process.env.TEMP || tmpdir(), 'lmv'), join(backend, '.venv'), join(backend, '..', '.venv')]
  const found = venvs.map(inVenv).find(existsSync)
  if (found) return found
  return ['python', 'python3'].find((p) => spawnSync(p, ['--version'], { stdio: 'ignore' }).status === 0)
}

const mode = process.argv[2] || 'api'
const python = findPython()
if (!python) {
  console.error('No Python found. Create the venv first (see CLAUDE.md "Commands"), or set LOGIMIND_PYTHON.')
  process.exit(1)
}
const needs = mode === 'test' ? 'fastapi, pytest' : 'fastapi, uvicorn'
if (spawnSync(python, ['-c', `import ${needs}`], { cwd: backend, stdio: 'ignore' }).status !== 0) {
  console.error(`${python} cannot import ${needs}. Install the requirements:\n  "${python}" -m pip install -r backend/requirements.txt`)
  process.exit(1)
}

// KEY=value lines; # comments and blank lines ignored; optional surrounding quotes removed.
function readDotEnv(file) {
  if (!existsSync(file)) return {}
  const out = {}
  for (const line of readFileSync(file, 'utf8').split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/)
    if (!m || line.trim().startsWith('#')) continue
    out[m[1]] = m[2].replace(/^(['"])(.*)\1$/, '$2')
  }
  return out
}

const dotenv = readDotEnv(join(backend, '.env'))
const fromFile = Object.keys(dotenv).filter((k) => dotenv[k] !== '' && process.env[k] === undefined)
const env = { ...Object.fromEntries(fromFile.map((k) => [k, dotenv[k]])), ...process.env }
if (fromFile.length) console.log(`backend/.env: ${fromFile.join(', ')}`)  // names only, never values
let args
if (mode === 'api') {
  // One process for development: the API also runs the job worker, so plans do not stay "queued".
  // Set LOGIMIND_WORKER=external and run `npm run worker` in a second terminal to use a separate worker.
  env.LOGIMIND_WORKER ??= 'inline'
  const port = env.PORT || '8000'
  args = ['-m', 'uvicorn', 'app.main:app', '--reload', '--port', port]
  console.log(`LogiMind API on http://localhost:${port}  (python: ${python}; worker: ${env.LOGIMIND_WORKER})`)
} else if (mode === 'worker') {
  args = ['-m', 'app.jobs.worker']
} else if (mode === 'test') {
  args = ['-m', 'pytest', '-q']
} else if (mode === 'tenant') {
  const name = process.argv.slice(3).join(' ').trim()
  if (!name) {
    console.error('usage: npm run tenant -- "Tenant name"')
    process.exit(2)
  }
  args = ['manage.py', 'create-tenant', name]
} else {
  console.error(`unknown mode ${mode}; expected api, worker, test or tenant`)
  process.exit(1)
}

const child = spawn(python, args, { cwd: backend, env, stdio: 'inherit' })
const tunnel = mode === 'api' ? startTunnel(env.PORT || '8000') : null
for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => { tunnel?.kill(); child.kill(sig) })
child.on('exit', (code, signal) => { tunnel?.kill(); process.exit(code ?? (signal ? 1 : 0)) })

// Public demo from this PC (decision 0040): with LOGIMIND_PUBLIC_DEMO=1 and FRONTEND_URL in backend/.env, a free
// Cloudflare quick tunnel (no account) makes the API reachable from the deployed console. Its address changes on
// every start, so the console link carries it: <FRONTEND_URL>/?api=<tunnel>. LOGIMIND_TUNNEL=0 turns this off.
function findCloudflared() {
  const onPath = spawnSync(win ? 'where' : 'which', ['cloudflared'], { encoding: 'utf8' })
  if (onPath.status === 0 && onPath.stdout.trim()) return onPath.stdout.trim().split(/\r?\n/)[0]
  const dirs = win ? [process.env['ProgramFiles(x86)'], process.env.ProgramFiles].filter(Boolean) : []
  return dirs.map((d) => join(d, 'cloudflared', 'cloudflared.exe')).find(existsSync)
}

function startTunnel(port) {
  if (env.LOGIMIND_PUBLIC_DEMO !== '1' || !env.FRONTEND_URL || env.LOGIMIND_TUNNEL === '0') return null
  if (env.LOGIMIND_DEMO_MODE !== '1') console.log('[tunnel] note: LOGIMIND_DEMO_MODE=1 is missing, so the console will ask for an API key.')
  const exe = findCloudflared()
  if (!exe) {
    console.log('[tunnel] cloudflared not found, so the deployed console cannot reach this PC. Install it with:\n  winget install Cloudflare.cloudflared')
    return null
  }
  const proc = spawn(exe, ['tunnel', '--no-autoupdate', '--url', `http://localhost:${port}`], { stdio: ['ignore', 'pipe', 'pipe'] })
  let shown = false
  const watch = (chunk) => {
    const m = !shown && String(chunk).match(/https:\/\/[a-z0-9-]+\.trycloudflare\.com/)
    if (!m) return
    shown = true
    const consoleUrl = env.FRONTEND_URL.replace(/\/+$/, '')
    console.log(`\n[tunnel] Public demo on this PC. Open (and share) this link; it changes every time npm run dev starts:\n\n  ${consoleUrl}/?api=${m[0]}\n\n[tunnel] API address: ${m[0]}  (keep this window open; Ctrl+C stops the API and the tunnel)\n`)
  }
  proc.stdout.on('data', watch)
  proc.stderr.on('data', watch)
  proc.on('error', (e) => console.log(`[tunnel] could not start cloudflared: ${e.message}`))
  proc.on('exit', (code) => { if (!child.killed && child.exitCode === null) console.log(`[tunnel] cloudflared stopped (exit ${code}); the deployed console can no longer reach this PC.`) })
  console.log('[tunnel] Starting a Cloudflare quick tunnel to this API...')
  return proc
}
