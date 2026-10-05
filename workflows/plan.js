export const meta = {
  name: 'plan',
  description: 'forge stage 3/5: check the index is approved, then up to 3 council rounds (Ozymandias drafts or revises, J. Jonah Jameson critiques, Smithers defends, Ozymandias rules), then write the tests. Produces pipeline/design.md, plan.md, ledger.md and tests/ for your review.',
  phases: [{ title: 'Gate' }, { title: 'Round 1' }, { title: 'Round 2' }, { title: 'Round 3' }, { title: 'Tests' }],
}

const HIPPO = 'forge:hungry-hippo'
const OZ = 'forge:ozymandias'
const JJJ = 'forge:j-jonah-jameson'
const SMITHERS = 'forge:smithers'
const MAX_ROUNDS = 3

const GATE = { type: 'object', required: ['ok', 'output'], properties: { ok: { type: 'boolean' }, output: { type: 'string' } } }
const DONE = {
  type: 'object', required: ['summary'],
  properties: { summary: { type: 'string' }, decisions: { type: 'array', items: { type: 'string' } } },
}
const CRITIQUES = {
  type: 'object', required: ['critiques'],
  properties: { critiques: { type: 'array', items: { type: 'object', required: ['id', 'severity', 'claim', 'evidence'], properties: {
    id: { type: 'string' }, severity: { type: 'string', enum: ['blocker', 'major', 'minor'] },
    claim: { type: 'string' }, evidence: { type: 'string' }, reopens: { type: 'string' },
  } } } },
}
const RESPONSES = {
  type: 'object', required: ['responses', 'load_bearing'],
  properties: {
    responses: { type: 'array', items: { type: 'object', required: ['id', 'response', 'argument'], properties: {
      id: { type: 'string' }, response: { type: 'string', enum: ['rebut', 'concede'] }, argument: { type: 'string' }, evidence: { type: 'string' },
    } } },
    load_bearing: { type: 'array', items: { type: 'object', required: ['id', 'reason'], properties: { id: { type: 'string' }, reason: { type: 'string' } } } },
  },
}
const RULINGS = {
  type: 'object', required: ['rulings'],
  properties: { rulings: { type: 'array', items: { type: 'object', required: ['id', 'ruling', 'reason'], properties: {
    id: { type: 'string' }, ruling: { type: 'string', enum: ['accepted', 'rejected'] }, reason: { type: 'string' }, evidence: { type: 'string' },
  } } } },
}
const TESTS = {
  type: 'object', required: ['files', 'coverage'],
  properties: {
    files: { type: 'array', items: { type: 'string' } },
    coverage: { type: 'array', items: { type: 'object', required: ['test', 'file'], properties: { test: { type: 'string' }, file: { type: 'string' } } } },
    not_written: { type: 'array', items: { type: 'string' } },
  },
}

const cell = s => String(s == null ? '' : s).replace(/\|/g, '/').replace(/\s+/g, ' ').trim()
// Evidence must point somewhere checkable: an index row, a reference key, or a brief/plan/design item.
const EVIDENCE_RE = /SQ-?\d|AC-?\d|D-?\d|T-?\d|[a-z]+\d{4}[a-z]+|brief|plan\.md|design\.md|index|line/i
const hasEvidence = c => typeof c.evidence === 'string' && c.evidence.trim().length > 4 && EVIDENCE_RE.test(c.evidence)

log('forge · stage 3/5 · Plan: gate → council rounds (draft → critique → defend → rule) → tests')

// ---------------------------------------------------------------- Gate
phase('Gate')
const gate = await agent(
  'Run exactly this command and nothing else: `forge-gate index`. Return ok=true only if its output starts with "OK", and put its output line in `output`.',
  { agentType: HIPPO, schema: GATE, label: 'is the index approved?' },
)
if (!gate || !gate.ok) {
  log(`Stopped: ${gate ? gate.output : 'the gate check did not run'}`)
  return { stopped: true, reason: gate ? gate.output : 'gate check failed', next: 'Approve the index with /forge:approve index, then run /forge:plan again.' }
}
log(gate.output)

// ---------------------------------------------------------------- Council
const ledger = [
  '# Ledger',
  '',
  'Written by `/forge:plan`, one section per council round. Every critique gets a ruling. Critics in later rounds read this file and may reopen a ruled item only with new evidence.',
  '',
  'Stop rule: stop when no accepted blocker or major critique is left to address, or after round 3.',
]
const history = []          // per round: { round, critiques, setAside, responses, rulings, open }
let loadBearing = []
let pending = []            // accepted critiques the next revision must address
let stopReason = ''

for (let round = 1; round <= MAX_ROUNDS; round++) {
  phase(`Round ${round}`)

  // Draft or revise
  if (round === 1) {
    const d = await agent(
      'Round 1. Draft pipeline/design.md and pipeline/plan.md from the approved pipeline/brief.md and pipeline/index.md, following your instructions and the templates. Set `round: 1` and `status: draft` in both frontmatters. Return a short summary and the list of key decisions (D-n: one line each).',
      { agentType: OZ, schema: DONE, label: `round ${round}: draft` },
    )
    if (!d) return { stopped: true, reason: 'Ozymandias could not draft the plan.' }
    log(`Round 1 draft: ${d.summary}`)
  } else {
    const d = await agent(
      `Round ${round}. Revise pipeline/design.md and pipeline/plan.md. Address every accepted critique below, keep the load-bearing decisions unless an accepted critique requires changing one, and set \`round: ${round}\` in both frontmatters. pipeline/ledger.md has the full record.\n\nAccepted critiques to address:\n${pending.map(c => `- ${c.id} [${c.severity}] ${c.claim} (ruling: ${c.reason})`).join('\n')}\n\nLoad-bearing decisions (from Smithers):\n${loadBearing.map(l => `- ${l.id}: ${l.reason}`).join('\n') || '- none listed'}\n\nReturn a summary of what changed, critique by critique.`,
      { agentType: OZ, schema: DONE, label: `round ${round}: revise` },
    )
    if (!d) return { stopped: true, reason: `Ozymandias could not revise the plan in round ${round}.` }
    log(`Round ${round} revision: ${d.summary}`)
  }

  // Critique (fresh critic every round)
  const crit = await agent(
    `Round ${round}. Critique the current pipeline/design.md and pipeline/plan.md as your instructions describe. pipeline/ledger.md holds earlier rounds and rulings.`,
    { agentType: JJJ, schema: CRITIQUES, label: `round ${round}: critique` },
  )
  const all = (crit ? crit.critiques : []).map((c, i) => ({ ...c, id: `R${round}-C${i + 1}` }))
  const critiques = all.filter(hasEvidence)
  const setAside = all.filter(c => !hasEvidence(c))
  log(`Round ${round}: ${critiques.length} critiques with evidence (${critiques.filter(c => c.severity === 'blocker').length} blocker, ${critiques.filter(c => c.severity === 'major').length} major), ${setAside.length} set aside for lack of evidence`)

  let responses = [], rulings = []
  if (critiques.length) {
    // Defend
    const def = await agent(
      `Round ${round}. Answer each of these critiques of pipeline/design.md and pipeline/plan.md (rebut with evidence, or concede), then list the load-bearing decisions.\n\n${critiques.map(c => `- ${c.id} [${c.severity}] ${c.claim}\n  evidence: ${c.evidence}`).join('\n')}`,
      { agentType: SMITHERS, schema: RESPONSES, label: `round ${round}: defend` },
    )
    responses = def ? def.responses : []
    if (def && def.load_bearing.length) loadBearing = def.load_bearing

    // Rule: every critique must get a ruling; ask once more for any that are missing.
    const ask = list => agent(
      `Round ${round}. Rule on each critique below: accepted (the next revision must address it) or rejected, with reason and evidence. Weigh Smithers' response on its evidence.\n\n${list.map(c => {
        const r = responses.find(x => x.id === c.id)
        return `- ${c.id} [${c.severity}] ${c.claim}\n  critic's evidence: ${c.evidence}\n  Smithers: ${r ? `${r.response}: ${r.argument}${r.evidence ? ` (evidence: ${r.evidence})` : ''}` : 'no response'}`
      }).join('\n')}`,
      { agentType: OZ, schema: RULINGS, label: `round ${round}: rule${list.length < critiques.length ? ' (missing ids)' : ''}` },
    )
    const first = await ask(critiques)
    rulings = first ? first.rulings : []
    const missing = critiques.filter(c => !rulings.some(r => r.id === c.id))
    if (missing.length) {
      const second = await ask(missing)
      rulings = rulings.concat(second ? second.rulings : [])
    }
  }

  // Bookkeeping, decided by the script
  const ruled = critiques.map(c => {
    const r = rulings.find(x => x.id === c.id)
    return { ...c, ruling: r ? r.ruling : 'no ruling', reason: r ? r.reason : 'Ozymandias gave no ruling (treated as accepted)', rulingEvidence: r ? r.evidence || '' : '' }
  })
  const accepted = ruled.filter(c => c.ruling === 'accepted' || c.ruling === 'no ruling')
  const open = accepted.filter(c => c.severity === 'blocker' || c.severity === 'major')
  history.push({ round, critiques: ruled, setAside, responses, open })
  pending = accepted

  ledger.push('', `## Round ${round}`, '', '### Critiques (J. Jonah Jameson)', '')
  if (ruled.length) {
    ledger.push('| id | severity | claim | evidence |', '|---|---|---|---|')
    for (const c of ruled) ledger.push(`| ${c.id} | ${c.severity} | ${cell(c.claim)} | ${cell(c.evidence)} |`)
  } else ledger.push('_No critiques with evidence._')
  if (setAside.length) {
    ledger.push('', 'Set aside (no checkable evidence):', '')
    for (const c of setAside) ledger.push(`- ${c.id} [${c.severity}] ${cell(c.claim)}`)
  }
  if (ruled.length) {
    ledger.push('', '### Responses (Smithers)', '', '| id | response | argument | evidence |', '|---|---|---|---|')
    for (const c of ruled) {
      const r = responses.find(x => x.id === c.id)
      ledger.push(`| ${c.id} | ${r ? r.response : 'none'} | ${cell(r && r.argument)} | ${cell(r && r.evidence)} |`)
    }
    ledger.push('', `Load-bearing decisions: ${loadBearing.map(l => `${l.id} (${cell(l.reason)})`).join('; ') || 'none listed'}`)
    ledger.push('', '### Rulings (Ozymandias)', '', '| id | ruling | reason | evidence |', '|---|---|---|---|')
    for (const c of ruled) ledger.push(`| ${c.id} | ${c.ruling} | ${cell(c.reason)} | ${cell(c.rulingEvidence)} |`)
  }
  const decision = open.length === 0 ? 'stop' : round === MAX_ROUNDS ? 'stop (round limit)' : 'revise and continue'
  ledger.push('', `Accepted after this round: ${accepted.length} (blockers and majors: ${open.length}). Decision: ${decision}.`)

  const wrote = await agent(
    `Write the following text to pipeline/ledger.md exactly, character for character, replacing the file. Then return a one-line summary.\n\n<<<CONTENT\n${ledger.join('\n')}\n` + 'CONTENT>>>',
    { agentType: OZ, schema: DONE, label: `round ${round}: write ledger` },
  )
  if (!wrote) log('Warning: writing pipeline/ledger.md failed')
  log(`Round ${round}: ${accepted.length} accepted, ${ruled.length - accepted.length} rejected; ${open.length} blocker/major to address → ${decision}`)

  if (open.length === 0) { stopReason = `no accepted blocker or major critique after round ${round}`; break }
  if (round === MAX_ROUNDS) { stopReason = `round limit (${MAX_ROUNDS}) reached with ${open.length} accepted blocker/major critiques`; break }
}

// Final revision for what the last round accepted (minors, or majors at the round limit), then mark final.
const lastOpen = history.length ? history[history.length - 1].open : []
const fin = await agent(
  `Final revision. ${pending.length ? `Address these accepted critiques from the last round:\n${pending.map(c => `- ${c.id} [${c.severity}] ${c.claim} (ruling: ${c.reason})`).join('\n')}\n` : 'No accepted critiques are left. '}` +
  `${lastOpen.length ? `The council stopped at the round limit, so these blocker/major items were not re-reviewed: list each of them in design.md's Risks as "not re-reviewed by the council: <id>". ` : ''}` +
  'Set `status: final` in the frontmatter of pipeline/design.md and pipeline/plan.md. Return a summary of the final changes.',
  { agentType: OZ, schema: DONE, label: 'final revision' },
)
log(fin ? `Final: ${fin.summary}` : 'Warning: the final revision did not complete')

// ---------------------------------------------------------------- Tests
phase('Tests')
const tests = await agent(
  'Write the test suite under tests/ from the "Test specs" of pipeline/plan.md: one test function per spec where possible (name it after the T-id, e.g. test_T3_...), using pytest. Include the conceptual tests the plan specifies (known-answer synthetic data, shuffled-label control at chance, invariants, tiny-dataset overfit). Tests import the modules and signatures plan.md defines; they will fail until the build stage implements them, which is expected. Do not write any code outside tests/. Return the files written, the T-id → file coverage, and any spec you could not turn into a test (with the reason).',
  { agentType: OZ, schema: TESTS, label: 'write tests' },
)

const crit = history.flatMap(h => h.critiques)
return {
  stage: 'forge · stage 3/5 · Plan finished',
  rounds: history.length,
  stop_rule: stopReason,
  critiques: crit.length,
  accepted: crit.filter(c => c.ruling === 'accepted').length,
  rejected: crit.filter(c => c.ruling === 'rejected').length,
  set_aside_without_evidence: history.reduce((n, h) => n + h.setAside.length, 0),
  not_re_reviewed: lastOpen.map(c => c.id),
  tests: tests ? `${tests.files.length} files, ${tests.coverage.length} specs covered${tests.not_written && tests.not_written.length ? `, not written: ${tests.not_written.join('; ')}` : ''}` : 'writing tests failed',
  files: ['pipeline/design.md', 'pipeline/plan.md', 'pipeline/ledger.md', 'tests/'],
  next: 'Read pipeline/design.md (and pipeline/ledger.md for the debate). If you agree, run /forge:approve design: that locks tests/ and opens the build stage. If not, do not approve; say what is wrong so the plan can be revised.',
}
