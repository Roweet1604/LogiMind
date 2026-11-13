// Vercel build (decision 0041): the console at / and the driver PWA at /driver/ on the same site, so driver links
// made in the deployed console open on a phone. Runs from frontend/ (Vercel's root directory for this project):
//   1. console:  VITE_DRIVER_PATH=/driver/ vite build            -> dist/
//   2. driver:   npm ci in ../driver, DRIVER_BASE=/driver/ vite build -> dist/driver/
// VITE_API_URL (the default API, decision 0039) reaches both builds from the environment.
import { spawnSync } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontend = join(dirname(fileURLToPath(import.meta.url)), '..')
const driver = join(frontend, '..', 'driver')
const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm'

function run(cmd, args, cwd, extraEnv) {
  console.log(`> (${cwd}) ${cmd} ${args.join(' ')}`)
  const shell = process.platform === 'win32' && cmd === npm
  const r = spawnSync(cmd, args, { cwd, stdio: 'inherit', env: { ...process.env, ...extraEnv }, shell })
  if (r.status !== 0) process.exit(r.status ?? 1)
}

// Vite is started with node itself (no shell), so folder names with spaces are passed safely.
const vite = (dir) => join(dir, 'node_modules', 'vite', 'bin', 'vite.js')
run(process.execPath, [vite(frontend), 'build'], frontend, { VITE_DRIVER_PATH: '/driver/' })
run(npm, ['ci', '--no-audit', '--no-fund'], driver)  // fixed arguments; the shell is needed for npm.cmd on Windows
run(process.execPath, [vite(driver), 'build', '--outDir', join(frontend, 'dist', 'driver'), '--emptyOutDir'], driver, { DRIVER_BASE: '/driver/' })
