export const meta = {
  name: 'investigate',
  description: 'forge stage 2/5, part 1 of 2: check the brief is approved, bring in the seed papers, search the literature for each sub-question, verify every ID, and write pipeline/candidates.md for your review.',
  phases: [{ title: 'Gate' }, { title: 'Read brief' }, { title: 'Seed papers' }, { title: 'Search' }, { title: 'Verify' }, { title: 'Candidate list' }],
}

const HIPPO = 'forge:hungry-hippo'
const CURIOSITY = 'forge:mr-curiosity'

const GATE = {
  type: 'object', required: ['ok', 'output'],
  properties: { ok: { type: 'boolean' }, output: { type: 'string' } },
}
const BRIEF = {
  type: 'object', required: ['sub_questions', 'seeds'],
  properties: {
    sub_questions: { type: 'array', items: { type: 'object', required: ['id', 'text'], properties: { id: { type: 'string' }, text: { type: 'string' } } } },
    seeds: { type: 'array', items: { type: 'string' } },
  },
}
const REPORT = {
  type: 'object', required: ['summary'],
  properties: { summary: { type: 'string' }, problems: { type: 'array', items: { type: 'string' } } },
}
const CANDIDATES = {
  type: 'object', required: ['candidates'],
  properties: {
    candidates: { type: 'array', items: { type: 'object', required: ['id', 'title', 'why'], properties: { id: { type: 'string' }, title: { type: 'string' }, why: { type: 'string' } } } },
    unresolved: { type: 'array', items: { type: 'object', properties: { id: { type: 'string' }, title: { type: 'string' } } } },
    notes: { type: 'string' },
  },
}
const RESOLVED = {
  type: 'object', required: ['results'],
  properties: {
    results: { type: 'array', items: { type: 'object', required: ['input', 'resolved'], properties: {
      input: { type: 'string' }, resolved: { type: 'boolean' }, id: { type: 'string' }, title: { type: 'string' },
      year: { type: ['integer', 'null'] }, first_author: { type: ['string', 'null'] }, in_project: { type: 'boolean' },
      error: { type: 'string' }, retry: { type: 'boolean' },
    } } },
  },
}

const CONVERT = {
  type: 'object', required: ['inbox_waiting', 'converted', 'output'],
  properties: {
    inbox_waiting: { type: 'integer' }, converted: { type: 'integer' },
    inbox_files: { type: 'array', items: { type: 'string' } }, output: { type: 'string' },
  },
}

// Convert everything in references/inbox/. One `refs convert` per round (it stops starting new
// papers after ~5 minutes), repeated until the inbox is empty. The script, not an agent, decides
// whether to go on, and reports exactly what is still unconverted.
async function convertAll(label) {
  let last = null
  for (let round = 1; round <= 6; round++) {
    const r = await agent(
      'Run exactly these two commands, each as its own shell call:\n' +
      '1. `refs convert` with the Bash tool timeout set to 600000 (10 minutes). It may print that PDFs are still waiting; that is expected.\n' +
      '2. `refs status --json`\n' +
      'Return `inbox_waiting`, `converted` and `inbox_files` exactly as the JSON of command 2 says, and in `output` the last 5 lines command 1 printed.',
      { agentType: HIPPO, schema: CONVERT, label: `${label}: convert round ${round}` },
    )
    if (!r) return { ok: false, waiting: last ? last.inbox_files || [] : ['(unknown)'], note: 'the convert step failed' }
    last = r
    log(`${label}, convert round ${round}: ${r.converted} converted, ${r.inbox_waiting} still waiting`)
    if (r.inbox_waiting === 0) return { ok: true, converted: r.converted, waiting: [] }
  }
  return { ok: false, waiting: last.inbox_files || [], note: 'PDFs were still waiting after 6 rounds' }
}

const cell = s => String(s == null ? '' : s).replace(/\|/g, '/').replace(/\s+/g, ' ').trim()

log('forge · stage 2/5 · Investigate, part 1 of 2: gate → seed papers → search → verify → candidate list')

// ---------------------------------------------------------------- Gate
phase('Gate')
const gate = await agent(
  'Run exactly this command and nothing else: `forge-gate brief`. Return ok=true only if its output starts with "OK", and put its output line in `output`.',
  { agentType: HIPPO, schema: GATE, label: 'is the brief approved?' },
)
if (!gate || !gate.ok) {
  log(`Stopped: ${gate ? gate.output : 'the gate check did not run'}`)
  return { stopped: true, reason: gate ? gate.output : 'gate check failed', next: 'Approve the brief with /forge:approve brief, then run /forge:investigate again.' }
}
log(gate.output)

// ---------------------------------------------------------------- Read brief
phase('Read brief')
const brief = await agent(
  'Read pipeline/brief.md. Return (1) every research sub-question from its "Research sub-questions" table, with its id and text exactly as written, and (2) the seed references as identifiers `refs fetch` accepts: DOIs or arXiv IDs only (if an entry also names a key, return just the ID; skip plain PDF file names).',
  { agentType: HIPPO, schema: BRIEF, label: 'read sub-questions and seeds' },
)
if (!brief || brief.sub_questions.length === 0) {
  return { stopped: true, reason: 'No research sub-questions found in pipeline/brief.md.' }
}
log(`${brief.sub_questions.length} sub-questions, ${brief.seeds.length} seed references`)

// ---------------------------------------------------------------- Seed papers
phase('Seed papers')
let seed = null
if (brief.seeds.length) {
  seed = await agent(
    `Run exactly this one command and report what it printed: \`refs fetch --source brief ${brief.seeds.join(' ')}\`\nIn \`summary\` say how many papers were downloaded, already present, and missing (paywalled). List failures in \`problems\`.`,
    { agentType: HIPPO, schema: REPORT, label: 'fetch seed papers' },
  )
  log(seed ? `Seed papers: ${seed.summary}` : 'Seed papers: the fetch did not complete')
}
const seedConv = await convertAll('Seed papers')
if (!seedConv.ok) log(`Warning: still unconverted: ${seedConv.waiting.join(', ')}. The search continues; /forge:investigate-index will convert them before indexing.`)

// ---------------------------------------------------------------- Search
phase('Search')
const searches = await pipeline(brief.sub_questions, sq => agent(
  `Research sub-question ${sq.id}: ${sq.text}\n\nThe approved brief is pipeline/brief.md; read its Goal and Constraints if you need context. Find the candidate papers for this sub-question as your instructions describe.`,
  { agentType: CURIOSITY, schema: CANDIDATES, label: `search ${sq.id}` },
))

// ---------------------------------------------------------------- Verify
phase('Verify')
// Re-check the searchers' candidates and also the IDs they could not confirm themselves
// (often an arXiv rate limit during the search, not a bad ID).
const allIds = [...new Set(searches.filter(Boolean).flatMap(r => [
  ...r.candidates.map(c => c.id.trim()),
  ...(r.unresolved || []).map(u => (u.id || '').trim()).filter(Boolean),
]))]
let byInput = {}
if (allIds.length) {
  const resolved = await agent(
    `Run exactly this one command: \`refs resolve ${allIds.join(' ')}\`\nIt prints a JSON list. Return that list as \`results\`, copying every field exactly as printed. A non-zero exit status only means some IDs did not resolve; still return the list.`,
    { agentType: HIPPO, schema: RESOLVED, label: `verify ${allIds.length} IDs` },
  )
  for (const r of (resolved ? resolved.results : [])) byInput[r.input] = r
}

// ---------------------------------------------------------------- Candidate list
phase('Candidate list')
const lines = [
  '# Candidate papers',
  '',
  'Written by `/forge:investigate`. Every ID below was checked with `refs resolve`; titles are the resolved ones.',
  '',
  '**Your review:** set `keep` to `no` (or delete the row) for papers you don\'t want, add rows if you know better papers, then run `/forge:approve candidates`. After that, `/forge:investigate-index` downloads and converts the kept papers and builds the index.',
  '',
]
const dropped = []
let kept = 0
brief.sub_questions.forEach((sq, i) => {
  const r = searches[i]
  lines.push(`## ${sq.id}: ${cell(sq.text)}`, '')
  if (!r) { lines.push('_The search for this sub-question failed; re-run /forge:investigate or add papers by hand._', ''); return }
  lines.push('| keep | id | title | year | first author | why | already in project |', '|---|---|---|---|---|---|---|')
  const offered = [...r.candidates, ...(r.unresolved || []).filter(u => u.id).map(u => ({ id: u.id, title: u.title || '', why: '(found by the searcher, confirmed in Verify; check its relevance)' }))]
  for (const c of offered) {
    const v = byInput[c.id.trim()]
    if (!v || !v.resolved) {
      const reason = v && v.retry ? 'could not check now (rate limit or outage): re-run /forge:investigate' : 'does not exist in Crossref or arXiv'
      dropped.push({ sq: sq.id, id: c.id, title: c.title, reason })
      continue
    }
    kept++
    lines.push(`| yes | ${cell(v.id)} | ${cell(v.title)} | ${cell(v.year)} | ${cell(v.first_author)} | ${cell(c.why)} | ${v.in_project ? 'yes' : 'no'} |`)
  }
  for (const u of (r.unresolved || [])) if (!u.id) dropped.push({ sq: sq.id, id: '', title: u.title || '', reason: 'no ID given' })
  if (r.notes) lines.push('', `_Searcher's note: ${cell(r.notes)}_`)
  lines.push('')
})
lines.push('## Dropped (not verifiable)', '', 'Not offered for download because `refs resolve` could not confirm them. Add a DOI or arXiv ID above if one of these matters.', '')
if (dropped.length) {
  lines.push('| sub-question | id | title as found | reason |', '|---|---|---|---|')
  for (const d of dropped) lines.push(`| ${d.sq} | ${cell(d.id)} | ${cell(d.title)} | ${d.reason} |`)
} else {
  lines.push('_None._')
}
const md = lines.join('\n') + '\n'

const wrote = await agent(
  `Write the following text to pipeline/candidates.md exactly, character for character, replacing the file if it exists. Then return a one-line summary.\n\n<<<CONTENT\n${md}CONTENT>>>`,
  { agentType: HIPPO, schema: REPORT, label: 'write pipeline/candidates.md' },
)

return {
  stage: 'forge · stage 2/5 · Investigate, part 1 of 2 finished',
  seed_papers: seed ? seed.summary : 'not completed',
  candidates_kept: kept,
  candidates_dropped: dropped.length,
  file: wrote ? 'pipeline/candidates.md' : 'writing pipeline/candidates.md failed',
  next: 'Review pipeline/candidates.md (set keep to no for papers you do not want), then run /forge:approve candidates, then /forge:investigate-index.',
}
