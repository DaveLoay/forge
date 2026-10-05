export const meta = {
  name: 'investigate-index',
  description: 'forge stage 2/5, part 2 of 2: check the candidate list is approved, download and convert the kept papers, and write pipeline/index.md (where each sub-question is answered) for your review.',
  phases: [{ title: 'Gate' }, { title: 'Read candidates' }, { title: 'Fetch' }, { title: 'Locate' }, { title: 'Index' }],
}

const HIPPO = 'forge:hungry-hippo'
const POINTER = 'forge:pointer'

const GATE = {
  type: 'object', required: ['ok', 'output'],
  properties: { ok: { type: 'boolean' }, output: { type: 'string' } },
}
const KEPT = {
  type: 'object', required: ['sub_questions'],
  properties: {
    sub_questions: { type: 'array', items: { type: 'object', required: ['id', 'text', 'ids'], properties: {
      id: { type: 'string' }, text: { type: 'string' }, ids: { type: 'array', items: { type: 'string' } },
    } } },
  },
}
const REPORT = {
  type: 'object', required: ['summary'],
  properties: { summary: { type: 'string' }, missing: { type: 'array', items: { type: 'string' } }, problems: { type: 'array', items: { type: 'string' } } },
}
const ROWS = {
  type: 'object', required: ['rows'],
  properties: {
    rows: { type: 'array', items: { type: 'object', required: ['key', 'heading', 'lines', 'reason'], properties: {
      key: { type: 'string' }, heading: { type: 'string' }, lines: { type: 'string' }, reason: { type: 'string' },
    } } },
    gaps: { type: 'string' },
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

log('forge · stage 2/5 · Investigate, part 2 of 2: gate → fetch kept papers → locate → index')

// ---------------------------------------------------------------- Gate
phase('Gate')
const gate = await agent(
  'Run exactly this command and nothing else: `forge-gate candidates`. Return ok=true only if its output starts with "OK", and put its output line in `output`.',
  { agentType: HIPPO, schema: GATE, label: 'is the candidate list approved?' },
)
if (!gate || !gate.ok) {
  log(`Stopped: ${gate ? gate.output : 'the gate check did not run'}`)
  return { stopped: true, reason: gate ? gate.output : 'gate check failed', next: 'Review pipeline/candidates.md, run /forge:approve candidates, then /forge:investigate-index again.' }
}
log(gate.output)

// ---------------------------------------------------------------- Read candidates
phase('Read candidates')
const kept = await agent(
  'Read pipeline/candidates.md. For each "## SQ-n: text" section, return the sub-question id, its text, and the ids of the rows whose `keep` column is yes (ignore rows marked no and the "Dropped" section).',
  { agentType: HIPPO, schema: KEPT, label: 'read kept papers' },
)
if (!kept) return { stopped: true, reason: 'Could not read pipeline/candidates.md.' }
const ids = [...new Set(kept.sub_questions.flatMap(s => s.ids.map(x => x.trim())))]
log(`${ids.length} papers kept across ${kept.sub_questions.length} sub-questions`)

// ---------------------------------------------------------------- Fetch
phase('Fetch')
let fetched = null
if (ids.length) {
  fetched = await agent(
    `Run exactly this one command and report what it printed: \`refs fetch --source curiosity ${ids.join(' ')}\`\nIn \`summary\` say how many were downloaded, already present, and missing (paywalled). List missing IDs in \`missing\` and failures in \`problems\`.`,
    { agentType: HIPPO, schema: REPORT, label: `fetch ${ids.length} papers` },
  )
  log(fetched ? `Fetch: ${fetched.summary}` : 'Fetch: the step did not complete')
}
const conv = await convertAll('Fetched papers')
if (!conv.ok) {
  log(`Stopped before indexing: ${conv.note}. Unconverted: ${conv.waiting.join(', ')}`)
  return {
    stopped: true,
    reason: `Not every fetched paper could be converted (${conv.note}), so no index was built from incomplete material.`,
    unconverted: conv.waiting,
    next: 'Run /forge:investigate-index again (conversion resumes where it stopped). If it keeps failing, run `refs status` and check the Marker log ~/.local/share/forge/marker-server.log.',
  }
}

// ---------------------------------------------------------------- Locate
phase('Locate')
const located = await pipeline(kept.sub_questions, sq => agent(
  `Research sub-question ${sq.id}: ${sq.text}\n\nThe papers chosen for it have these IDs: ${sq.ids.join(', ') || '(none)'}. Map IDs to keys with references/catalog.md. You may also use any other converted paper in references/ that answers this sub-question. Locate the passages that answer it, as your instructions describe, and return them as rows. In \`gaps\`, say what the papers do not answer.`,
  { agentType: POINTER, schema: ROWS, label: `locate ${sq.id}` },
))

// ---------------------------------------------------------------- Index
phase('Index')
const lines = [
  '# Index',
  '',
  'Written by `/forge:investigate-index`. Each row points to the passage of a converted paper (`references/<key>/<key>.md`) that answers a research sub-question. It locates; it does not judge.',
  '',
  '**Your review:** check that the rows point to the right places and that nothing important is missing, then run `/forge:approve index`. Planning works only from what this index points to.',
  '',
  '| sub-question | key | heading | lines | reason |',
  '|---|---|---|---|---|',
]
const gaps = []
kept.sub_questions.forEach((sq, i) => {
  const r = located[i]
  if (!r) { gaps.push(`${sq.id}: locating failed; re-run /forge:investigate-index.`); return }
  for (const row of r.rows) lines.push(`| ${sq.id} | ${cell(row.key)} | ${cell(row.heading)} | ${cell(row.lines)} | ${cell(row.reason)} |`)
  if (r.rows.length === 0) gaps.push(`${sq.id}: no passage found.`)
  if (r.gaps) gaps.push(`${sq.id}: ${cell(r.gaps)}`)
})
lines.push('', '## Gaps', '')
lines.push(...(gaps.length ? gaps.map(g => `- ${g}`) : ['_None reported._']))
if (fetched && fetched.missing && fetched.missing.length) {
  lines.push('', '## Missing papers', '', 'Paywalled; see references/MISSING.md. Drop the PDFs into references/inbox/ and re-run /forge:investigate-index to include them.', '')
  lines.push(...fetched.missing.map(m => `- ${m}`))
}
const md = lines.join('\n') + '\n'

const wrote = await agent(
  `Write the following text to pipeline/index.md exactly, character for character, replacing the file if it exists. Then return {"rows": [], "gaps": "written"}.\n\n<<<CONTENT\n${md}CONTENT>>>`,
  { agentType: POINTER, schema: ROWS, label: 'write pipeline/index.md' },
)

return {
  stage: 'forge · stage 2/5 · Investigate, part 2 of 2 finished',
  fetched: fetched ? fetched.summary : 'nothing to fetch',
  index_rows: lines.filter(l => l.startsWith('| SQ')).length,
  gaps: gaps.length,
  file: wrote ? 'pipeline/index.md' : 'writing pipeline/index.md failed',
  next: 'Review pipeline/index.md, then run /forge:approve index.',
}
