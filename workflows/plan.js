export const meta = {
  name: 'plan',
  description: 'forge stage 3/5: check the index is approved, then up to 3 council rounds (Ozymandias builds the environment, drafts or revises with small probes and Bubastis code lookups, J. Jonah Jameson critiques, Smithers defends, Ozymandias rules), then write the tests. Produces pipeline/design.md, plan.md, ledger.md, env/, probes/, code/ and tests/ for your review.',
  phases: [{ title: 'Gate' }, { title: 'Round 1' }, { title: 'Round 2' }, { title: 'Round 3' }, { title: 'Tests' }],
}

const HIPPO = 'forge:hungry-hippo'
const OZ = 'forge:ozymandias'
const JJJ = 'forge:j-jonah-jameson'
const SMITHERS = 'forge:smithers'
const SCOUT = 'forge:bubastis'
const MAX_ROUNDS = 3
const MAX_LOOKUPS = 12      // code lookups per run
const MAX_PER_TASK = 4      // code lookups one Ozymandias task may ask for

const GATE = { type: 'object', required: ['ok', 'output'], properties: { ok: { type: 'boolean' }, output: { type: 'string' } } }
// Questions about a paper's code that Ozymandias wants a Bubastis scout to answer before its next task.
const CODE_REQUESTS = { type: 'array', items: { type: 'object', required: ['repo', 'question', 'why'], properties: {
  repo: { type: 'string' }, question: { type: 'string' }, why: { type: 'string' },
} } }
const DONE = {
  type: 'object', required: ['summary'],
  properties: {
    summary: { type: 'string' }, decisions: { type: 'array', items: { type: 'string' } },
    probes: { type: 'array', items: { type: 'string' } },   // P-n ids run in this task, with their verdicts
    code_requests: CODE_REQUESTS,
  },
}
const ASK = { type: 'object', required: ['code_requests'], properties: { code_requests: CODE_REQUESTS } }
const REPOS = { type: 'object', required: ['linked', 'output'], properties: { linked: { type: 'integer' }, fetched: { type: 'integer' }, output: { type: 'string' } } }
const FOUND = {
  type: 'object', required: ['summary', 'rows'],
  properties: {
    summary: { type: 'string' }, folder: { type: 'string' }, commit: { type: 'string' },
    rows: { type: 'array', items: { type: 'object', required: ['path', 'lines', 'reason'], properties: {
      path: { type: 'string' }, lines: { type: 'string' }, symbol: { type: 'string' }, reason: { type: 'string' },
    } } },
    not_found: { type: 'string' }, problem: { type: 'string' },
  },
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
  } } }, code_requests: CODE_REQUESTS },
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
// Evidence must point somewhere checkable: an index row, a reference key, a probe record, a code finding, or a brief/plan/design item.
const EVIDENCE_RE = /SQ-?\d|AC-?\d|D-?\d|T-?\d|P-?\d|(?<![\w-])C-\d|[a-z]+\d{4}[a-z]+|brief|plan\.md|design\.md|index|line/i
const hasEvidence = c => typeof c.evidence === 'string' && c.evidence.trim().length > 4 && EVIDENCE_RE.test(c.evidence)

log('forge · stage 3/5 · Plan: gate → council rounds (environment + draft with probes and code lookups → critique → defend → rule) → tests')
const probeNote = d => (d.probes && d.probes.length ? ` Probes: ${d.probes.join('; ')}.` : '')
const one = s => String(s == null ? '' : s).replace(/\s+/g, ' ').trim()

// ---------------------------------------------------------------- Code lookups
// Ozymandias (Opus) never searches a repository itself. It names the repository and the question;
// a Bubastis scout (Haiku) fetches the repository and returns file:line pointers, and Ozymandias
// reads only those lines in its next task. agent() calls can't be resumed, so the answers reach
// the next Ozymandias task (rule, revise or final), which always follows the task that asked.
let codeOn = false          // set once we know a converted paper links a repository
const findings = []         // every lookup in this run: { id, repo, question, why, from, result }
let unseen = []             // findings not yet passed to Ozymandias
const asked = new Set()
const FINDINGS_HEAD = [
  '# Code findings',
  '',
  'Written by `/forge:plan` (this run). Each `C-n` is one question Ozymandias asked about a paper\'s code, answered by Bubastis with pointers into `references/code/<folder>/`, pinned to the commit shown. Read the pointed-to lines before relying on a finding.',
  '',
]

async function writeFindings() {
  const md = [...FINDINGS_HEAD]
  for (const f of findings) {
    const r = f.result
    md.push(`## ${f.id}: ${f.question}`, '', `- asked in: ${f.from}${f.why ? ` · settles ${f.why}` : ''}`,
      `- repository: ${f.repo}${r && r.folder ? ` → references/code/${one(r.folder)}/ @ ${one(r.commit)}` : ''}`)
    if (!r) md.push('- result: the lookup failed')
    else if (r.problem) md.push(`- problem: ${one(r.problem)}`)
    else {
      md.push(`- answer: ${one(r.summary)}`)
      if (r.not_found) md.push(`- not found: ${one(r.not_found)}`)
      if (r.rows.length) {
        md.push('', '| path | lines | symbol | what is there |', '|---|---|---|---|')
        for (const x of r.rows) md.push(`| ${cell(x.path)} | ${cell(x.lines)} | ${cell(x.symbol)} | ${cell(x.reason)} |`)
      }
    }
    md.push('')
  }
  const wrote = await agent(
    `Write the following text to pipeline/code/findings.md exactly, character for character, replacing the file. Then return {"summary": "written", "rows": []}.\n\n<<<CONTENT\n${md.join('\n')}\n` + 'CONTENT>>>',
    { agentType: SCOUT, schema: FOUND, label: 'write pipeline/code/findings.md' },
  )
  if (!wrote) log('Warning: writing pipeline/code/findings.md failed')
}

async function lookUp(requests, from) {
  const asks = []
  for (const r of requests || []) {
    const k = `${one(r && r.repo).toLowerCase()}|${one(r && r.question).toLowerCase()}`
    if (!one(r && r.repo) || !one(r && r.question) || asked.has(k)) continue
    asked.add(k)
    asks.push(r)
  }
  if (!asks.length) return
  if (!codeOn) { log(`Code lookups not run: no converted paper links a repository (${from} asked ${asks.length})`); return }
  const room = Math.max(0, Math.min(MAX_PER_TASK, MAX_LOOKUPS - findings.length))
  const dropped = asks.slice(room)
  if (dropped.length) log(`Code lookups not run (limit: ${MAX_PER_TASK} per task, ${MAX_LOOKUPS} per run): ${dropped.map(r => `${one(r.repo)}: ${one(r.question)}`).join(' | ')}`)
  const items = asks.slice(0, room).map((r, i) => ({ id: `C-${findings.length + i + 1}`, repo: one(r.repo), question: one(r.question), why: one(r.why), from }))
  if (!items.length) return
  const results = await parallel(items.map(it => () => agent(
    `Question ${it.id} from Ozymandias about the code of ${it.repo}:\n\n${it.question}\n\nIt settles: ${it.why || 'not stated'}. Fetch the repository with \`refs code fetch ${it.repo}\`, find where its code answers the question, and return the answer and the pointers as your instructions describe.`,
    { agentType: SCOUT, schema: FOUND, label: `${from}: ${it.id} code lookup` },
  )))
  items.forEach((it, i) => { it.result = results[i]; findings.push(it); unseen.push(it) })
  const answered = items.filter(it => it.result && !it.result.problem && it.result.rows.length).length
  log(`Code lookups (${from}): ${answered} of ${items.length} answered with pointers. ${items.map(it => `${it.id} ${it.repo}`).join('; ')}`)
  await writeFindings()
}

// The findings Ozymandias has not seen yet, for the prompt of its next task.
function codeNote() {
  if (!unseen.length) return ''
  const text = unseen.map(f => {
    const r = f.result
    if (!r) return `- ${f.id} (${f.repo}): the lookup failed. Question: ${f.question}`
    if (r.problem) return `- ${f.id} (${f.repo}): not answered: ${one(r.problem)}. Question: ${f.question}`
    return `- ${f.id} (${f.repo} → references/code/${one(r.folder)}/ @ ${one(r.commit).slice(0, 12)}): ${f.question}\n  answer: ${one(r.summary)}` +
      r.rows.map(x => `\n  - ${one(x.path)}:${one(x.lines)}${x.symbol ? ` (${one(x.symbol)})` : ''}: ${one(x.reason)}`).join('') +
      (r.not_found ? `\n  not found: ${one(r.not_found)}` : '')
  }).join('\n')
  unseen = []
  return `\n\nCode findings from Bubastis since your last task (also in pipeline/code/findings.md). Read the pointed-to lines in references/code/ before relying on one, and cite it as C-n:\n${text}`
}
const ASK_NOTE = ' If a decision depends on a paper\'s code that you have not seen, return `code_requests` (see your instructions); the answers reach your next task.'

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
    // Which papers link code? Also starts this run's pipeline/code/findings.md afresh.
    const repos = await agent(
      `Do two things. 1. Run exactly \`refs code list --json\` and return in \`linked\` the number of entries in its "linked" list, in \`fetched\` how many of those have "fetched": true, and in \`output\` one line naming the linked repositories. 2. Write the following text to pipeline/code/findings.md exactly, replacing the file.\n\n<<<CONTENT\n${FINDINGS_HEAD.join('\n')}_No code lookups yet._\n` + 'CONTENT>>>',
      { agentType: SCOUT, schema: REPOS, label: 'repositories linked from the papers' },
    )
    codeOn = !!(repos && repos.linked > 0)
    log(codeOn ? `Code: ${repos.linked} repositories linked from the papers (${repos.fetched || 0} already fetched). ${one(repos.output)}` : 'Code: no converted paper links a GitHub or GitLab repository; no code lookups this run')
    if (codeOn) {
      const ask = await agent(
        `Round 1, before drafting: decide what to look up in the papers' code. Read pipeline/brief.md and the table in pipeline/index.md (not the papers yet), and run \`refs code list\`. Return as \`code_requests\` the facts your draft will depend on that a linked repository settles better than the paper text: exact preprocessing, default hyperparameters, loss weighting, architecture details, evaluation protocol. At most ${MAX_PER_TASK}; an empty list if no linked repository would change a decision. Write no files in this task.`,
        { agentType: OZ, schema: ASK, effort: 'medium', label: 'round 1: what to look up in the code' },
      )
      await lookUp(ask && ask.code_requests, 'round 1 (before the draft)')
    }
    const d = await agent(
      'Round 1. First write the environment spec in pipeline/env/ from the brief\'s Environment section and build it with `forge-env create`, as your instructions describe. Then draft pipeline/design.md and pipeline/plan.md from the approved pipeline/brief.md and pipeline/index.md, following your instructions and the templates; where a decision depends on a fact about the data or the tools that a small probe can check, run one with `forge-probe`. Set `round: 1` and `status: draft` in both frontmatters. Return a short summary, the list of key decisions (D-n: one line each), and the probes you ran (P-n: verdict).' + (codeOn ? ASK_NOTE : '') + codeNote(),
      { agentType: OZ, schema: DONE, label: `round ${round}: draft` },
    )
    if (!d) return { stopped: true, reason: 'Ozymandias could not draft the plan.' }
    log(`Round 1 draft: ${d.summary}${probeNote(d)}`)
    await lookUp(d.code_requests, `round ${round} draft`)
  } else {
    const d = await agent(
      `Round ${round}. Revise pipeline/design.md and pipeline/plan.md. Address every accepted critique below, keep the load-bearing decisions unless an accepted critique requires changing one, and set \`round: ${round}\` in both frontmatters. pipeline/ledger.md has the full record.\n\nAccepted critiques to address:\n${pending.map(c => `- ${c.id} [${c.severity}] ${c.claim} (ruling: ${c.reason})`).join('\n')}\n\nLoad-bearing decisions (from Smithers):\n${loadBearing.map(l => `- ${l.id}: ${l.reason}`).join('\n') || '- none listed'}\n\nWhere a critique turns on a fact a small probe can settle, run one (forge-probe) instead of arguing. If the dependencies change, update pipeline/env/ and run \`forge-env create\`. Return a summary of what changed, critique by critique, and the probes you ran (P-n: verdict).${codeOn ? ASK_NOTE : ''}${codeNote()}`,
      { agentType: OZ, schema: DONE, label: `round ${round}: revise` },
    )
    if (!d) return { stopped: true, reason: `Ozymandias could not revise the plan in round ${round}.` }
    log(`Round ${round} revision: ${d.summary}${probeNote(d)}`)
    await lookUp(d.code_requests, `round ${round} revision`)
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
      `Round ${round}. Rule on each critique below: accepted (the next revision must address it) or rejected, with reason and evidence. Weigh Smithers' response on its evidence. If a ruling turns on a fact a small probe can settle, run one (forge-probe) and cite it as P-n.${codeOn ? ' If the next revision will need a fact from a paper\'s code, return `code_requests`; the answers reach that revision.' : ''}${codeNote()}\n\n${list.map(c => {
        const r = responses.find(x => x.id === c.id)
        return `- ${c.id} [${c.severity}] ${c.claim}\n  critic's evidence: ${c.evidence}\n  Smithers: ${r ? `${r.response}: ${r.argument}${r.evidence ? ` (evidence: ${r.evidence})` : ''}` : 'no response'}`
      }).join('\n')}`,
      { agentType: OZ, schema: RULINGS, label: `round ${round}: rule${list.length < critiques.length ? ' (missing ids)' : ''}` },
    )
    const first = await ask(critiques)
    rulings = first ? first.rulings : []
    let requests = first && first.code_requests ? first.code_requests : []
    const missing = critiques.filter(c => !rulings.some(r => r.id === c.id))
    if (missing.length) {
      const second = await ask(missing)
      rulings = rulings.concat(second ? second.rulings : [])
      requests = requests.concat(second && second.code_requests ? second.code_requests : [])
    }
    await lookUp(requests, `round ${round} rulings`)
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
  'Make sure design.md\'s Probes table lists every probe in pipeline/probes/probes.md that a decision relies on, and that `forge-env status` reports the environment READY (run `forge-env create` if not). Set `status: final` in the frontmatter of pipeline/design.md and pipeline/plan.md. Return a summary of the final changes. No code lookups run after this task, so return no `code_requests`.' + codeNote(),
  { agentType: OZ, schema: DONE, label: 'final revision' },
)
log(fin ? `Final: ${fin.summary}` : 'Warning: the final revision did not complete')
if (fin && fin.code_requests && fin.code_requests.length) log(`Code lookups asked for in the final revision were not run: ${fin.code_requests.map(r => `${one(r.repo)}: ${one(r.question)}`).join(' | ')}`)

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
  code_lookups: codeOn ? `${findings.length} (${findings.filter(f => f.result && !f.result.problem && f.result.rows.length).length} answered with pointers)` : 'none: no paper links a repository',
  tests: tests ? `${tests.files.length} files, ${tests.coverage.length} specs covered${tests.not_written && tests.not_written.length ? `, not written: ${tests.not_written.join('; ')}` : ''}` : 'writing tests failed',
  files: ['pipeline/design.md', 'pipeline/plan.md', 'pipeline/ledger.md', 'pipeline/env/', 'pipeline/probes/probes.md', 'pipeline/code/findings.md', 'tests/'],
  next: 'Read pipeline/design.md (and pipeline/ledger.md for the debate, pipeline/probes/probes.md for what the probes showed, pipeline/code/findings.md for what was looked up in the papers\' code). If you agree, run /forge:approve design: that locks tests/, fixes the environment in pipeline/env/, and opens the build stage. If not, do not approve; say what is wrong so the plan can be revised.',
}
