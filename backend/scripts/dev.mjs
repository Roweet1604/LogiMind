// `npm run dev` for the Python backend (decision 0026). Finds the Python environment, then runs
//   api     python -m uvicorn app.main:app --reload --port 8000   (LOGIMIND_WORKER=inline unless set)
//   worker  python -m app.jobs.worker
//   test    python -m pytest -q
//   tenant  python manage.py create-tenant "<name>"   (prints the first API key once; only its hash is stored)
// Python is taken from LOGIMIND_PYTHON, else the venv in %TEMP%\lmv (CLAUDE.md), else backend/.venv or ../.venv,
// else python / python3 on the PATH. Settings are environment variables (see app/main.py); for local runs they
// can also live in backend/.env (git-ignored, see .env.example). Variables already set in the shell win.
// api also opens a Cloudflare quick tunnel for the deployed console when backend/.env asks for the public demo
// (LOGIMIND_PUBLIC_DEMO=1 and FRONTEND_URL; decision 0040) and prints the console link to open, retrying a failed
// tunnel up to 3 times and printing no link if it never works (decision 0043).
import { spawn, spawnSync } from 'node:child_process'
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { MAX_ATTEMPTS, classifyLine, findTunnelAddress, tunnelArgs } from './tunnel.mjs'

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

const apiPort = env.PORT || '8000'
if (mode === 'api') freePort(apiPort)
const child = spawn(python, args, { cwd: backend, env, stdio: 'inherit' })
const tunnel = mode === 'api' ? startTunnel(apiPort) : null
for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => { tunnel?.kill(); child.kill(sig) })
child.on('exit', (code, signal) => {
  tunnel?.kill()
  if (mode === 'api') console.log(`[api] The API stopped (exit ${code ?? signal}); the tunnel was stopped with it. The reason is in the lines above.`)
  process.exit(code ?? (signal ? 1 : 0))
})

// Port check before the API starts (decision 0040). A LogiMind API left running from an earlier `npm run dev`
// (uvicorn app.main:app) is stopped with its reloader and workers; anything else is reported and nothing starts.
function listeners(port) {
  if (!win) return []
  const out = spawnSync('netstat', ['-ano', '-p', 'TCP'], { encoding: 'utf8' }).stdout || ''
  const pids = new Set()
  for (const line of out.split(/\r?\n/)) {
    const m = line.trim().match(/^TCP\s+\S+:(\d+)\s+\S+\s+LISTENING\s+(\d+)$/)
    if (m && m[1] === String(port) && m[2] !== '0') pids.add(Number(m[2]))
  }
  return [...pids]
}

function processInfo(pid) {
  const ps = `$p = Get-CimInstance Win32_Process -Filter "ProcessId=${Number(pid)}"; if ($p) { [string]$p.ParentProcessId; $p.Name; [string]$p.CommandLine }`
  const r = spawnSync('powershell', ['-NoProfile', '-Command', ps], { encoding: 'utf8' })
  const [parent, name, cmd] = (r.stdout || '').split(/\r?\n/)
  return name ? { pid, parent: Number(parent), name, cmd: cmd || '' } : null
}

function isLogiMindApi(p) { return /uvicorn/.test(p.cmd) && /app\.main:app/.test(p.cmd) }

function freePort(port) {
  const pids = listeners(port)
  if (!pids.length) return
  for (const pid of pids) {
    const p = processInfo(pid)
    if (!p || !isLogiMindApi(p)) {
      console.error(`[api] Port ${port} is already used by ${p ? `${p.name} (PID ${pid}): ${p.cmd}` : `PID ${pid}`}.\n` +
        `      It is not a LogiMind API, so it was left alone. Close it, or start on another port: set PORT=8001 in backend/.env.`)
      process.exit(1)
    }
    let top = p  // with --reload the listener is a worker; stop from the reloader down
    for (let up = processInfo(p.parent); up && isLogiMindApi(up); up = processInfo(up.parent)) top = up
    console.log(`[api] Port ${port} was held by an earlier LogiMind API (PID ${top.pid}); stopping it.`)
    spawnSync('taskkill', ['/PID', String(top.pid), '/T', '/F'], { stdio: 'ignore' })
  }
  for (let i = 0; i < 20 && listeners(port).length; i++) spawnSync(process.execPath, ['-e', 'setTimeout(()=>{},250)'])
  if (listeners(port).length) {
    console.error(`[api] Port ${port} is still in use after stopping PID(s) ${pids.join(', ')}. Close that window by hand and run npm run dev again.`)
    process.exit(1)
  }
}

// Public demo from this PC (decision 0040): with LOGIMIND_PUBLIC_DEMO=1 and FRONTEND_URL in backend/.env, a free
// Cloudflare quick tunnel (no account) makes the API reachable from the deployed console. Its address changes on
// every start, so the console link carries it: <FRONTEND_URL>/?api=<tunnel>. LOGIMIND_TUNNEL=0 turns this off.
// cloudflared is looked for in LOGIMIND_CLOUDFLARED, on the PATH, then in the usual install folders (VS Code's
// terminal may have an older PATH than a new Windows terminal).
function findCloudflared() {
  if (env.LOGIMIND_CLOUDFLARED && existsSync(env.LOGIMIND_CLOUDFLARED)) return env.LOGIMIND_CLOUDFLARED
  const onPath = spawnSync(win ? 'where' : 'which', ['cloudflared'], { encoding: 'utf8' })
  if (onPath.status === 0 && onPath.stdout.trim()) return onPath.stdout.trim().split(/\r?\n/)[0]
  if (!win) return ['/usr/local/bin/cloudflared', '/opt/homebrew/bin/cloudflared', '/usr/bin/cloudflared'].find(existsSync)
  const local = process.env.LOCALAPPDATA || ''
  const candidates = [
    join(process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)', 'cloudflared', 'cloudflared.exe'),
    join(process.env.ProgramFiles || 'C:\\Program Files', 'cloudflared', 'cloudflared.exe'),
    'C:\\Program Files (x86)\\cloudflared\\cloudflared.exe',
    'C:\\Program Files\\cloudflared\\cloudflared.exe',
    join(local, 'Microsoft', 'WinGet', 'Links', 'cloudflared.exe'),
    join(local, 'cloudflared', 'cloudflared.exe'),
    join(process.env.USERPROFILE || '', 'scoop', 'shims', 'cloudflared.exe'),
    'C:\\ProgramData\\chocolatey\\bin\\cloudflared.exe',
  ]
  const pkgs = join(local, 'Microsoft', 'WinGet', 'Packages')
  if (local && existsSync(pkgs)) {
    for (const d of readdirSync(pkgs)) if (/^Cloudflare\.cloudflared/i.test(d)) candidates.push(join(pkgs, d, 'cloudflared.exe'))
  }
  return candidates.find((c) => c && existsSync(c))
}

function pause(ms) { return new Promise((r) => setTimeout(r, ms)) }

// The tunnel's DNS name can take a few seconds to resolve, and the API needs a moment to start; check it from here.
async function checkTunnel(url, cancelled) {
  let last = ''
  for (let i = 0; i < 45; i++) {
    if (cancelled()) return 'cancelled'
    if (child.exitCode !== null) return 'the API stopped'
    try {
      const r = await fetch(`${url}/health`, { signal: AbortSignal.timeout(5000) })
      if (r.ok) return null
      last = `HTTP ${r.status}`
    } catch (e) { last = e.cause?.code || e.message }
    await pause(2000)
  }
  return last
}

function startTunnel(port) {
  if (env.LOGIMIND_TUNNEL === '0') return null
  if (env.LOGIMIND_PUBLIC_DEMO !== '1' || !env.FRONTEND_URL) {
    console.log('[tunnel] Not started: backend/.env needs LOGIMIND_PUBLIC_DEMO=1 and FRONTEND_URL=https://... for the deployed console.')
    return null
  }
  if (env.LOGIMIND_DEMO_MODE !== '1') console.log('[tunnel] note: LOGIMIND_DEMO_MODE=1 is missing, so the console will ask for an API key.')
  const exe = findCloudflared()
  if (!exe) {
    console.log('[tunnel] cloudflared not found (PATH, Program Files, WinGet folders), so the deployed console cannot reach this PC.\n' +
      '         Install it with: winget install Cloudflare.cloudflared   or set LOGIMIND_CLOUDFLARED=<full path to cloudflared.exe> in backend/.env')
    return null
  }
  // Up to MAX_ATTEMPTS tries (decision 0043). The link is printed only when the address came from cloudflared's
  // success banner AND <address>/health answers; a QUIC timeout switches the next tries to --protocol http2.
  const state = { proc: null, stopped: false }
  ;(async () => {
    let protocol = null
    let last = []
    for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
      if (state.stopped || child.exitCode !== null) return
      const how = protocol ? ` with --protocol ${protocol}` : ''
      console.log(`[tunnel] Starting a Cloudflare quick tunnel to this API${how} (try ${attempt} of ${MAX_ATTEMPTS}; ${exe})...`)
      const r = await tunnelAttempt(exe, port, protocol, state)
      last = r.recent
      if (r.ok || state.stopped || child.exitCode !== null) return
      if (r.quicTimeout && !protocol) protocol = 'http2'
      console.log(`[tunnel] Try ${attempt} failed: ${r.reason}.${protocol && r.quicTimeout ? ' Next try uses --protocol http2.' : ''}`)
      if (attempt < MAX_ATTEMPTS) await pause(3000 * attempt)
    }
    if (state.stopped || child.exitCode !== null) return
    console.log(`\n[tunnel] Gave up after ${MAX_ATTEMPTS} tries: no working Cloudflare quick tunnel, so there is NO console link this time.\n` +
      `         The API still runs on this PC (http://localhost:${port}). cloudflared's last lines:\n  ${last.join('\n  ') || '(none)'}\n` +
      '         Check the internet connection (a firewall may block cloudflared), then stop with Ctrl+C and run npm run dev again.\n')
  })()
  return { kill: () => { state.stopped = true; state.proc?.kill() } }
}

// One cloudflared run. Resolves { ok: true } once the link was printed, else { ok: false, reason } after stopping
// cloudflared; quicTimeout says whether a QUIC timeout was seen. If a working tunnel's cloudflared stops later, that is
// reported (the link no longer works).
function tunnelAttempt(exe, port, protocol, state) {
  return new Promise((resolve) => {
    const proc = spawn(exe, tunnelArgs(port, protocol), { stdio: ['ignore', 'pipe', 'pipe'] })
    state.proc = proc
    let output = ''  // what cloudflared printed so far, so a banner split across chunks is still found
    const recent = []  // cloudflared's last lines, shown if it fails
    let address = null
    let quicTimeout = false
    let done = false
    let succeeded = false  // the link was printed for this run
    let noAddress = null
    const finish = (r) => {
      if (done) return
      done = true
      succeeded = r.ok
      clearTimeout(noAddress)
      if (!r.ok) proc.kill()
      resolve({ ...r, quicTimeout, recent: [...recent] })
    }
    const fail = (reason) => finish({ ok: false, reason })
    const watch = (chunk) => {
      const text = String(chunk)
      output = (output + text).slice(-20000)
      let failure = null
      for (const line of text.split(/\r?\n/)) {
        if (!line.trim()) continue
        recent.push(line.trim())
        const kind = classifyLine(line)
        if (kind === 'quic-timeout') quicTimeout = true
        failure ??= kind
      }
      recent.splice(0, Math.max(0, recent.length - 8))
      if (done) return
      if (failure) {
        fail(failure === 'quic-timeout' ? 'the QUIC connection to Cloudflare timed out' : 'cloudflared could not get a quick tunnel')
        return
      }
      if (address) return
      address = findTunnelAddress(output)
      if (!address) return
      clearTimeout(noAddress)
      console.log(`[tunnel] Tunnel address ${address}; checking that it reaches the API...`)
      checkTunnel(address, () => done).then((problem) => {
        if (done) return
        if (problem) { fail(`${address}/health did not answer (${problem})`); return }
        const link = `${env.FRONTEND_URL.replace(/\/+$/, '')}/?api=${address}`
        console.log(`\n[tunnel] Checked: ${address}/health answers. Open (and share) this link; it changes every time npm run dev starts:\n\n  ${link}\n\n` +
          '[tunnel] Keep this terminal open; Ctrl+C stops the API and the tunnel.\n')
        finish({ ok: true })
      })
    }
    proc.stdout.on('data', watch)
    proc.stderr.on('data', watch)
    noAddress = setTimeout(() => fail('no tunnel address after 60 s'), 60000)
    noAddress.unref()
    proc.on('error', (e) => fail(`could not start ${exe}: ${e.message}`))
    proc.on('exit', (code) => {
      if (!done) { fail(`cloudflared stopped (exit ${code})`); return }
      if (!succeeded || state.stopped || child.exitCode !== null) return
      console.log(`[tunnel] cloudflared stopped (exit ${code}); the link above no longer works. Its last lines:\n  ${recent.join('\n  ') || '(none)'}\n` +
        '         Stop with Ctrl+C and run npm run dev again for a new link.')
    })
  })
}
