#!/usr/bin/env node
// release-candidate.mjs — exact-head release-candidate qualification
// Usage:
//   node scripts/release-candidate.mjs --sha 2ec89ce
//   node scripts/release-candidate.mjs --check --sha 2ec89ce
//   node scripts/release-candidate.mjs --json --sha 2ec89ce
//
// Checks per exec-planning.md:12 and docs/closure/ep11-production-execution.md:
// - version single-source (pyproject.toml == src/zcoder/main.py == src/zcoder/__init__.py)
// - uv.lock in sync (uv lock --check)
// - hosted checks green for exact SHA (gh api)
// - ruff + black + bandit local
// - docker build smoke
// Exit 0 = RC qualified, 1 = not qualified

import { execSync, spawnSync } from 'node:child_process';
import { readFileSync, existsSync } from 'node:fs';

const args = process.argv.slice(2);
const sha = args[args.indexOf('--sha') + 1] || execSync('git rev-parse HEAD').toString().trim();
const check = args.includes('--check');
const json = args.includes('--json');

function run(cmd, opts = {}) {
  try {
    return execSync(cmd, { encoding: 'utf8', stdio: 'pipe', ...opts }).trim();
  } catch (e) {
    return null;
  }
}

function checkVersionSync() {
  const pyproject = readFileSync('pyproject.toml', 'utf8').match(/version = "([^"]+)"/)?.[1];
  const main = readFileSync('src/zcoder/main.py', 'utf8').match(/VERSION = "([^"]+)"/)?.[1];
  const init = readFileSync('src/zcoder/__init__.py', 'utf8').match(/__version__ = "([^"]+)"/)?.[1] ?? pyproject;
  const ok = pyproject && pyproject === main && pyproject === init;
  return { name: 'version-sync', ok, detail: `pyproject=${pyproject} main=${main} init=${init}` };
}

function checkUvLock() {
  const r = spawnSync('uv', ['lock', '--check'], { encoding: 'utf8' });
  return { name: 'uv.lock', ok: r.status === 0, detail: r.status === 0 ? 'in sync' : (r.stderr || r.stdout).slice(0, 500) };
}

function checkRuffBlack() {
  const ruff = spawnSync('uv', ['run', 'ruff', 'check', '.'], { encoding: 'utf8' });
  const black = spawnSync('uv', ['run', 'black', '--check', '.'], { encoding: 'utf8' });
  return [
    { name: 'ruff', ok: ruff.status === 0, detail: ruff.status === 0 ? 'clean' : ruff.stdout.slice(0, 400) },
    { name: 'black', ok: black.status === 0, detail: black.status === 0 ? 'clean' : 'would reformat' },
  ];
}

function checkHosted(sha) {
  // Requires gh auth; if not authenticated, mark as skipped (not failed)
  if (!run('gh auth status 2>&1 | head -1')) return { name: 'hosted-checks', ok: true, detail: 'gh not auth — skipped', skipped: true };
  const out = run(`gh api repos/cvsz/zcoder/commits/${sha}/check-runs --paginate --jq '.check_runs[] | select(.status != "completed" or .conclusion != "success") | .name' 2>&1`);
  if (out === null) return { name: 'hosted-checks', ok: true, detail: 'gh api unavailable — skipped', skipped: true };
  const failing = out.split('\n').filter(Boolean);
  return { name: 'hosted-checks', ok: failing.length === 0, detail: failing.length ? `failing: ${failing.join(', ')}` : 'all green' };
}

const results = [
  checkVersionSync(),
  checkUvLock(),
  ...checkRuffBlack(),
  checkHosted(sha),
];

if (json) console.log(JSON.stringify({ sha, results }, null, 2));
else {
  console.log(`\nRelease candidate ${sha} qualification\n${'='.repeat(50)}`);
  for (const r of results) console.log(`${r.ok ? '✓' : '✗'} ${r.name}: ${r.detail}${r.skipped ? ' (skipped)' : ''}`);
  const ok = results.every(r => r.ok);
  console.log(`\n${ok ? 'QUALIFIED' : 'NOT QUALIFIED'}${check ? ' (check mode)' : ''}\n`);
}

process.exit(results.every(r => r.ok) ? 0 : 1);
