#!/usr/bin/env node
// Run automated preflight against one clean, exact release-candidate commit.
// Production qualification additionally requires exec-planning.md evidence.
// Usage: node scripts/release-candidate.mjs [--check] [--json] [--sha <commit>]

import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

const requiredChecks = [
  'lint', 'security', 'test (3.10)', 'test (3.11)', 'test (3.12)', 'docker-build',
  'Analyze Python Code Security', 'Bandit and pip-audit', 'Gitleaks secret scan',
  'actionlint workflows', 'Helm v3.21.3 Lint & Template Check',
  'Helm v4.2.3 Lint & Template Check', 'Package Helm Chart & Checksums',
  'Production Release Gate Audit', 'Validate TypeScript SDK & Types',
  'lock-check', 'sync-locked',
];

function run(command, args) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 120_000 });
  return {
    ok: result.status === 0,
    out: (result.stdout || '').trim(),
    error: result.error ? result.error.message : `command exited ${result.status}`,
  };
}

const args = process.argv.slice(2);
let requestedSha;
let json = false;
for (let index = 0; index < args.length; index++) {
  const arg = args[index];
  if (arg === '--json') json = true;
  else if (arg === '--check') continue;
  else if (arg === '--sha' && !requestedSha && /^[a-f0-9]{7,40}$/i.test(args[index + 1] || '')) {
    requestedSha = args[++index];
  } else {
    console.error('Usage: release-candidate.mjs [--check] [--json] [--sha <7-40 hex commit>]');
    process.exit(1);
  }
}

const head = run('git', ['rev-parse', '--verify', 'HEAD']);
const candidate = run('git', ['rev-parse', '--verify', `${requestedSha || 'HEAD'}^{commit}`]);
const sha = candidate.out;

function checkCheckout() {
  const worktree = run('git', ['diff', '--quiet']);
  const index = run('git', ['diff', '--cached', '--quiet']);
  const ok = head.ok && candidate.ok && sha === head.out && worktree.ok && index.ok;
  return { name: 'exact-checkout', ok, detail: ok ? 'clean checkout matches candidate' : 'candidate must match a clean HEAD' };
}

function checkVersionSync() {
  try {
    const pyproject = readFileSync('pyproject.toml', 'utf8').match(/^version = "([^"]+)"/m)?.[1];
    const main = readFileSync('src/zcoder/main.py', 'utf8').match(/^VERSION = "([^"]+)"/m)?.[1];
    // __init__ reads package metadata dynamically; no independent version constant is required.
    const init = readFileSync('src/zcoder/__init__.py', 'utf8').match(/^__version__ = "([^"]+)"/m)?.[1] ?? pyproject;
    return { name: 'version-sync', ok: Boolean(pyproject && pyproject === main && pyproject === init), detail: `pyproject=${pyproject} main=${main} init=${init}` };
  } catch {
    return { name: 'version-sync', ok: false, detail: 'version sources unavailable' };
  }
}

function checkCommand(name, command, args) {
  const result = run(command, args);
  return { name, ok: result.ok, detail: result.ok ? 'passed' : result.error };
}

function checkHosted() {
  if (!candidate.ok) return { name: 'hosted-checks', ok: false, detail: 'candidate SHA unavailable' };
  const auth = run('gh', ['auth', 'status']);
  if (!auth.ok) return { name: 'hosted-checks', ok: false, detail: 'GitHub authentication unavailable' };
  const response = run('gh', [
    'api', `repos/cvsz/zcoder/commits/${sha}/check-runs?filter=latest&per_page=100`,
    '--paginate', '--slurp',
  ]);
  if (!response.ok) return { name: 'hosted-checks', ok: false, detail: 'GitHub check-run evidence unavailable' };
  try {
    const pages = JSON.parse(response.out);
    if (!Array.isArray(pages) || pages.some(page => !Array.isArray(page.check_runs))) throw new Error('invalid evidence');
    const latest = new Map();
    for (const check of pages.flatMap(page => page.check_runs)) {
      if (!check.name || check.head_sha !== sha) throw new Error('check SHA mismatch');
      if (!latest.has(check.name) || Number(check.id) > Number(latest.get(check.name).id)) latest.set(check.name, check);
    }
    const missing = requiredChecks.filter(name => !latest.has(name));
    const failing = [...latest.values()].filter(check =>
      check.status !== 'completed' || (check.conclusion !== 'success' && !(check.conclusion === 'skipped' && !requiredChecks.includes(check.name)))
    ).map(check => check.name);
    const ok = missing.length === 0 && failing.length === 0;
    return { name: 'hosted-checks', ok, detail: ok ? `${requiredChecks.length} required checks passed` : `missing: ${missing.join(', ') || 'none'}; failing: ${failing.join(', ') || 'none'}` };
  } catch {
    return { name: 'hosted-checks', ok: false, detail: 'invalid or mismatched GitHub check-run evidence' };
  }
}

const results = [
  checkCheckout(),
  checkVersionSync(),
  checkCommand('uv.lock', 'uv', ['lock', '--check']),
  checkCommand('ruff', 'uv', ['run', '--locked', 'ruff', 'check', '.']),
  checkCommand('black', 'uv', ['run', '--locked', 'black', '--check', '.']),
  checkCommand('bandit', 'uv', ['run', '--locked', 'bandit', '-r', 'src/zcoder', 'webapp', 'scripts', '-ll']),
  checkHosted(),
];
const ok = results.every(result => result.ok);
if (json) console.log(JSON.stringify({ sha, results }, null, 2));
else {
  console.log(`Release candidate ${sha || '<unavailable>'} automated preflight`);
  for (const result of results) console.log(`${result.ok ? 'PASS' : 'FAIL'} ${result.name}: ${result.detail}`);
  console.log(ok ? 'AUTOMATED PREFLIGHT PASSED; production qualification evidence is still required.' : 'AUTOMATED PREFLIGHT FAILED');
}
process.exit(ok ? 0 : 1);
