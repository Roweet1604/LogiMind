// `npm run dev` for the Python backend (decision 0026). Finds the Python environment, then runs
//   api     python -m uvicorn app.main:app --reload --port 8000   (LOGIMIND_WORKER=inline unless set)
//   worker  python -m app.jobs.worker
//   test    python -m pytest -q
// Python is taken from LOGIMIND_PYTHON, else the venv in %TEMP%\lmv (CLAUDE.md), else backend/.venv or ../.venv,
// else python / python3 on the PATH. Every other setting stays an environment variable (see app/main.py).
import { spawn, spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
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

const env = { ...process.env }
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
} else {
  console.error(`unknown mode ${mode}; expected api, worker or test`)
  process.exit(1)
}

const child = spawn(python, args, { cwd: backend, env, stdio: 'inherit' })
for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => child.kill(sig))
child.on('exit', (code, signal) => process.exit(code ?? (signal ? 1 : 0)))
