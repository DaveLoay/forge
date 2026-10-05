export const meta = {
  name: 'build',
  description: 'forge stage 5/5: build the next slice of the approved plan (up to 3 attempts), verify it with forge-test, write the slice report, and stop for your approval. When every slice is approved, run the final review.',
  phases: [{ title: 'Status' }, { title: 'Build' }, { title: 'Report' }, { title: 'Review' }],
}

const HIPPO = 'forge:hungry-hippo'
const MF = 'forge:mf-code'
const REVIEWER = 'forge:reviewer'
const MAX_ATTEMPTS = 3

const STATUS = {
  type: 'object', required: ['design_ok', 'tests_intact', 'next', 'all_approved', 'slices'],
  properties: {
    design_ok: { type: 'boolean' }, design: { type: 'string' },
    tests_locked: { type: 'boolean' }, tests_intact: { type: 'boolean' }, tests_lock: { type: 'string' },
    next: { type: ['integer', 'null'] }, all_approved: { type: 'boolean' }, review_exists: { type: 'boolean' },
    slices: { type: 'array', items: { type: 'object', required: ['n', 'name', 'approved'], properties: {
      n: { type: 'integer' }, name: { type: 'string' }, approved: { type: 'boolean' }, report: { type: 'boolean' },
      commands: { type: 'array', items: { type: 'string' } },
      tests: { type: ['object', 'null'], properties: {
        passed: { type: 'boolean' }, ran_at: { type: 'string' }, reason: { type: 'string' }, tail: { type: 'string' },
        commands: { type: 'array', items: { type: 'object', properties: { command: { type: 'string' }, exit: { type: 'integer' } } } },
      } },
      changes: { type: ['object', 'null'], properties: {
        added: { type: 'array', items: { type: 'string' } }, changed: { type: 'array', items: { type: 'string' } }, removed: { type: 'array', items: { type: 'string' } },
      } },
    } } },
  },
}
const ATTEMPT = {
  type: 'object', required: ['summary'],
  properties: {
    summary: { type: 'string' },
    plan_says_stop: { type: ['string', 'null'] },
    test_concerns: { type: 'array', items: { type: 'string' } },
  },
}
const DONE = { type: 'object', required: ['summary'], properties: { summary: { type: 'string' } } }

const cell = s => String(s == null ? '' : s).replace(/\|/g, '/').replace(/\s+/g, ' ').trim()
const readStatus = label => agent(
  'Run exactly this command and nothing else: `forge-build-status --json`. Return the JSON it printed as your structured output, copying every field and value exactly.',
  { agentType: HIPPO, schema: STATUS, label },
)

log('forge · stage 5/5 · Build: one slice per run → forge-test checkpoint → slice report → your approval')

// ---------------------------------------------------------------- Status
phase('Status')
const st = await readStatus('read build status')
if (!st) return { stopped: true, reason: 'Could not read the build status.' }
if (!st.design_ok) return { stopped: true, reason: st.design, next: 'Run /forge:approve design (it also locks tests/), then /forge:build.' }
if (!st.tests_intact) return { stopped: true, reason: st.tests_lock, next: 'tests/ must match what was locked at design approval. Restore it, or re-plan and re-approve the design.' }

// ---------------------------------------------------------------- Review (all slices approved)
if (st.all_approved) {
  phase('Review')
  const rv = await agent(
    'Every slice is built and approved. Review the build against pipeline/plan.md and pipeline/design.md as your instructions describe, write pipeline/review.md, and return a summary with the count of findings by severity.',
    { agentType: REVIEWER, schema: DONE, label: 'final review' },
  )
  return {
    stage: 'forge · stage 5/5 · Build finished',
    review: rv ? rv.summary : 'the review did not complete',
    next: 'Read pipeline/review.md. Blocker or major findings go back to planning; otherwise the project is done.',
  }
}

const n = st.next
const slice = st.slices.find(s => s.n === n)
if (slice.tests && slice.tests.passed && slice.report) {
  return {
    stopped: true,
    reason: `Slice ${n} (${slice.name}) is built and its checkpoint passed, but you have not approved it yet.`,
    next: `Review pipeline/slices/slice-${n}.md, then run /forge:approve slice-${n}, then /forge:build for the next slice.`,
  }
}
log(`Next: slice ${n} of ${st.slices.length}: ${slice.name}. Checkpoint: ${slice.commands.join(' ; ')}`)

// ---------------------------------------------------------------- Build (up to 3 attempts)
phase('Build')
const attempts = []
let after = null
let stopNote = null
for (let a = 1; a <= MAX_ATTEMPTS; a++) {
  const prev = attempts.length ? attempts[attempts.length - 1] : null
  const r = await agent(
    `Build Slice ${n} ("${slice.name}") of pipeline/plan.md. Attempt ${a} of ${MAX_ATTEMPTS}.\n` +
    (prev ? `\nThe previous attempt did not pass its checkpoint. forge-test reported: ${prev.reason}\nLast output:\n${prev.tail}\nFix the cause; do not touch tests/.\n` : '') +
    `\nWhen the code is in place, run \`forge-test ${n}\` (Bash timeout 600000). Return a summary of what you built or changed, \`plan_says_stop\` if the plan's own stop condition applies, and any \`test_concerns\`.`,
    { agentType: MF, schema: ATTEMPT, label: `slice ${n}: attempt ${a}` },
  )
  // The verdict comes from forge-test's record, not from the agent's summary.
  after = await readStatus(`slice ${n}: check attempt ${a}`)
  const rec = after ? after.slices.find(s => s.n === n).tests : null
  const passed = !!(rec && rec.passed && after.tests_intact)
  attempts.push({
    attempt: a, summary: r ? r.summary : 'the attempt did not complete', passed,
    reason: rec ? (rec.reason || (rec.passed ? 'passed' : 'failed')) : 'forge-test was not run',
    tail: rec ? rec.tail || '' : '', concerns: r && r.test_concerns ? r.test_concerns : [],
  })
  log(`Slice ${n}, attempt ${a}: ${passed ? 'checkpoint PASSED' : `checkpoint not passed (${attempts[attempts.length - 1].reason})`}`)
  if (r && r.plan_says_stop) { stopNote = r.plan_says_stop; break }
  if (passed) break
}
const final = attempts[attempts.length - 1]
const sliceSt = after ? after.slices.find(s => s.n === n) : slice
const ch = sliceSt.changes || { added: [], changed: [], removed: [] }

// ---------------------------------------------------------------- Report
phase('Report')
const outcome = final.passed ? 'PASSED' : stopNote ? 'STOPPED BY THE PLAN' : 'BLOCKED'
const lines = [
  `# Slice ${n}: ${slice.name}`,
  '',
  `Outcome: **${outcome}** after ${attempts.length} attempt(s). Written by \`/forge:build\`; the test results come from \`forge-test ${n}\` (pipeline/slices/slice-${n}.tests.json), not from the builder.`,
  '',
  '## Checkpoint (from plan.md)',
  '',
  ...((sliceSt.tests && sliceSt.tests.commands) || []).map(c => `- \`${c.command}\` → exit ${c.exit}`),
  ...(!sliceSt.tests ? ['- not run'] : []),
  '',
  `tests/ unchanged since the lock: ${after && after.tests_intact ? 'yes' : 'NO'}`,
  '',
  '## Files',
  '',
  `- added: ${ch.added.join(', ') || 'none'}`,
  `- changed: ${ch.changed.join(', ') || 'none'}`,
  `- removed: ${ch.removed.join(', ') || 'none'}`,
  '',
  '## Attempts',
  '',
  ...attempts.map(t => `### Attempt ${t.attempt}: ${t.passed ? 'passed' : 'not passed'}\n\n${t.summary}\n${t.passed ? '' : `\nforge-test: ${t.reason}\n\n\`\`\`\n${t.tail}\n\`\`\`\n`}`),
]
const concerns = attempts.flatMap(t => t.concerns)
if (concerns.length) lines.push('## Concerns about the tests (for planning)', '', ...concerns.map(c => `- ${c}`), '')
if (stopNote) lines.push('## Stop condition from the plan', '', stopNote, '')
if (!final.passed && !stopNote) {
  lines.push('## Blocker report', '',
    `The checkpoint still fails after ${MAX_ATTEMPTS} attempts. The build stops here instead of looping. ` +
    'This goes back to planning: check the failing output above against the plan and the tests, then revise the plan (/forge:plan) and re-approve the design, or fix the environment if the failure is not about the code.', '')
}
if (final.passed) lines.push('## Your review', '', `Read the files above. If you are satisfied, run \`/forge:approve slice-${n}\`, then \`/forge:build\` for the next slice.`, '')
const md = lines.join('\n') + '\n'

await agent(
  `Write the following text to pipeline/slices/slice-${n}.md exactly, character for character, replacing the file. Then append this one line to pipeline/build-log.md (create it with the heading "# Build log" if missing): "- slice ${n} (${cell(slice.name)}): ${outcome}, ${attempts.length} attempt(s), see pipeline/slices/slice-${n}.md". Return a one-line summary.\n\n<<<CONTENT\n${md}` + 'CONTENT>>>',
  { agentType: MF, schema: DONE, label: `slice ${n}: write report` },
)

return {
  stage: `forge · stage 5/5 · Build: slice ${n} of ${st.slices.length}`,
  slice: `${n}: ${slice.name}`,
  outcome,
  attempts: attempts.length,
  files: ch,
  report: `pipeline/slices/slice-${n}.md`,
  next: final.passed
    ? `Review pipeline/slices/slice-${n}.md, then /forge:approve slice-${n}, then /forge:build.`
    : stopNote
      ? `The plan says to stop here: ${stopNote}. Read the report and decide with the planner what to do.`
      : `Blocked after ${MAX_ATTEMPTS} attempts: read the blocker report in pipeline/slices/slice-${n}.md; this goes back to planning.`,
}
