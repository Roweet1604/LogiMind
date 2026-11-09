// `npm run dev` for the Python backend (decision 0026). Finds the Python environment, then runs
//   api     python -m uvicorn app.main:app --reload --port 8000   (LOGIMIND_WORKER=inline unless set)
//   worker  python -m app.jobs.worker
//   test    python -m pytest -q
//   tenant  python manage.py create-tenant "<name>"   (prints the first API key once; only its hash is stored)
// Python is taken from LOGIMIND_PYTHON, else the venv in %TEMP%\lmv (CLAUDE.md), else backend/.venv or ../.venv,
// else python / python3 on the PATH. Settings are environment variables (see app/main.py); for local runs they
// can also live in backend/.env (git-ignored, see .env.example). Variables already set in the shell win.
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
for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => child.kill(sig))
child.on('exit', (code, signal) => process.exit(code ?? (signal ? 1 : 0)))
