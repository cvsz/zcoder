#!/usr/bin/env node
// post-release-smoke.mjs — post-release smoke for wheel + container
// Usage:
//   node scripts/post-release-smoke.mjs --target ghcr.io/cvsz/zcoder:1.41.0
//   node scripts/post-release-smoke.mjs --target dist/zcoder-1.41.0-py3-none-any.whl
//   node scripts/post-release-smoke.mjs --target http://localhost:8000 --live
//
// Checks:
// - wheel: pip install --force-reinstall + zcoder --version + --health-check
// - container: docker run --rm <image> --version + --health-check
// - live: curl /health/live + /health/ready + /metrics
// Exit 0 = smoke pass, 1 = fail

import { spawnSync, execSync } from 'node:child_process';

const args = process.argv.slice(2);
const target = args[args.indexOf('--target') + 1] || 'ghcr.io/cvsz/zcoder:1.41.0';
const live = args.includes('--live');
const isWheel = target.endsWith('.whl');
const isHttp = target.startsWith('http');

function run(cmd, opts = {}) {
  const r = spawnSync(cmd[0], cmd.slice(1), { encoding: 'utf8', ...opts });
  return { ok: r.status === 0, out: (r.stdout + r.stderr).slice(0, 2000), status: r.status };
}

function curl(path) {
  try {
    const out = execSync(`curl -sf ${target}${path}`, { encoding: 'utf8', timeout: 8000 });
    return { ok: true, out: out.slice(0, 1000) };
  } catch (e) {
    return { ok: false, out: e.message.slice(0, 1000) };
  }
}

const results = [];

if (isWheel) {
  const pip = run(['uv', 'pip', 'install', '--force-reinstall', target]);
  results.push({ name: 'pip install wheel', ...pip });
  const ver = run(['zcoder', '--version']);
  results.push({ name: 'zcoder --version', ...ver });
  const health = run(['python', '-c', 'from zcoder.core.health import run_health_checks; print(run_health_checks())']);
  results.push({ name: 'health-check', ...health });
} else if (isHttp && live) {
  for (const p of ['/health/live', '/health/ready', '/metrics']) {
    const c = curl(p);
    results.push({ name: `GET ${p}`, ok: c.ok, out: c.out, status: c.ok ? 0 : 1 });
  }
} else {
  // container image
  const ver = run(['docker', 'run', '--rm', target, '--version']);
  results.push({ name: `docker run ${target} --version`, ...ver });
  const health = run(['docker', 'run', '--rm', target, '--health-check']);
  // --health-check may not be a CLI flag; fallback to python health
  if (!health.ok) {
    const health2 = run(['docker', 'run', '--rm', target, 'python', '-c', 'from zcoder.core.health import run_health_checks; print(run_health_checks())']);
    results.push({ name: 'container health', ...health2 });
  } else results.push({ name: 'container health', ...health });
}

console.log(`\nPost-release smoke: ${target}\n${'='.repeat(50)}`);
for (const r of results) console.log(`${r.ok ? '✓' : '✗'} ${r.name}: ${r.out.split('\n')[0].slice(0, 180)}`);
const ok = results.every(r => r.ok);
console.log(`\n${ok ? 'SMOKE PASS' : 'SMOKE FAIL'}\n`);
process.exit(ok ? 0 : 1);
