/**
 * Dev script: exercise WIDGET_SYSTEM_PROMPT + Groq json_schema against representative user messages.
 * Run: npx tsx scripts/test-widget-prompts.ts
 * Requires GROQ_API_KEY (env, .env.local, or Convex: npx convex env get GROQ_API_KEY).
 */

import { execSync } from 'node:child_process'
import { readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  KYNO_WIDGET_JSON_SCHEMA,
  parseKynoWidgetBatchDetailed,
  widgetRetryHint,
  type WidgetParseFailure,
} from '../convex/widgets.ts'
import { WIDGET_CORRECTION_PREFIX, WIDGET_SYSTEM_PROMPT } from '../shared/prompts.ts'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(__dirname, '..')

const DEFAULT_MODEL = 'openai/gpt-oss-20b'
const GROQ_CHAT_URL = 'https://api.groq.com/openai/v1/chat/completions'
const SCHEMA_NAME = 'kyno_widget'
const MAX_WIDGET_ATTEMPTS = 3

type GroqChatMessage = {
  role: 'user' | 'assistant' | 'system'
  content: string
}

type GroqResponseMode = 'json' | 'json_object'

type Scenario = {
  id: string
  userMessage: string
  /** Subsequence of expected widget types (order preserved). */
  expectTypes: string[]
  notes?: string
}

const SCENARIOS: Scenario[] = [
  // --- response (4) ---
  {
    id: 'response-plain-explain',
    userMessage: 'Explain photosynthesis in simple terms.',
    expectTypes: ['response'],
    notes: 'Plain explanation, single response widget',
  },
  {
    id: 'response-rhetorical',
    userMessage: 'Why is the sky blue? Tell me about it.',
    expectTypes: ['response'],
    notes: 'Rhetorical question phrasing — should stay response, not question widget',
  },
  {
    id: 'response-short-ack',
    userMessage: 'hello',
    expectTypes: ['response'],
    notes: 'Short acknowledgment',
  },
  {
    id: 'response-multi-paragraph',
    userMessage:
      'Explain the main causes of World War I in detail, covering alliances, militarism, and nationalism.',
    expectTypes: ['response'],
    notes: 'Multi-paragraph explanation',
  },

  // --- notation (4) ---
  {
    id: 'notation-power-rule',
    userMessage: 'Show the power rule formula for derivatives.',
    expectTypes: ['notation'],
    notes: 'LaTeX power rule; leading response widget also acceptable',
  },
  {
    id: 'notation-water-formula',
    userMessage: "What is water's chemical formula?",
    expectTypes: ['notation'],
    notes: 'H₂O in notation widget',
  },
  {
    id: 'notation-linear-equation',
    userMessage: 'Display the equation 2x + 5 = 17.',
    expectTypes: ['notation'],
    notes: 'Simple equation in notation',
  },
  {
    id: 'notation-fraction',
    userMessage: 'Show the fraction three-quarters in mathematical notation.',
    expectTypes: ['notation'],
    notes: 'Fraction notation (e.g. \\frac{3}{4})',
  },

  // --- question (4) ---
  {
    id: 'question-pure-mcq',
    userMessage: 'What is the capital of France? Give me multiple choice options.',
    expectTypes: ['question'],
    notes: 'Pure MCQ, no notation',
  },
  {
    id: 'question-topic-pick',
    userMessage: 'Which topic should we study: fractions or decimals?',
    expectTypes: ['question'],
    notes: 'Topic pick with 2 options',
  },
  {
    id: 'question-four-options',
    userMessage: 'Pick a primary color: red, blue, green, or yellow.',
    expectTypes: ['question'],
    notes: 'Question with 4 options',
  },
  {
    id: 'question-two-options',
    userMessage: 'Do you prefer studying in the morning or at night?',
    expectTypes: ['question'],
    notes: 'Minimum 2-option question',
  },

  // --- confirm (4) ---
  {
    id: 'confirm-ready',
    userMessage: 'Ready to continue?',
    expectTypes: ['confirm'],
    notes: 'Yes/No confirm',
  },
  {
    id: 'confirm-yes-no-not-sure',
    userMessage: 'Do you understand the concept? Answer yes, no, or not sure.',
    expectTypes: ['confirm'],
    notes: 'Yes/No/Not sure — 3 suggestedAnswers',
  },
  {
    id: 'confirm-after-notation',
    userMessage: 'Does 2x + 5 = 17 mean x is 6? Answer yes or no.',
    expectTypes: ['notation', 'confirm'],
    notes: 'Notation split from confirm when equation present',
  },
  {
    id: 'confirm-understanding',
    userMessage: 'Does that make sense?',
    expectTypes: ['confirm'],
    notes: 'Simple understanding check',
  },
]

function loadDotEnvFile(path: string, overwrite = false): void {
  if (!existsSync(path)) return
  const text = readFileSync(path, 'utf8')
  for (const line of text.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const eq = trimmed.indexOf('=')
    if (eq <= 0) continue
    const key = trimmed.slice(0, eq).trim()
    let value = trimmed.slice(eq + 1).trim()
    const hashIdx = value.indexOf(' #')
    if (hashIdx >= 0) {
      value = value.slice(0, hashIdx).trim()
    }
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1)
    }
    if (overwrite || process.env[key] === undefined) {
      process.env[key] = value
    }
  }
}

function loadGroqApiKey(): string {
  loadDotEnvFile(resolve(ROOT, '.env.local'), true)
  loadDotEnvFile(resolve(ROOT, '.env'))

  let key = process.env.GROQ_API_KEY?.trim()
  if (key) return key

  try {
    const env = { ...process.env }
    if (env.CONVEX_DEPLOYMENT) {
      env.CONVEX_DEPLOYMENT = env.CONVEX_DEPLOYMENT.split('#')[0]?.trim() ?? env.CONVEX_DEPLOYMENT
    }
    key = execSync('npx convex env get GROQ_API_KEY', {
      cwd: ROOT,
      encoding: 'utf8',
      shell: '/bin/sh',
      env,
    }).trim()
    if (key) return key
  } catch {
    // Convex CLI unavailable or key not set
  }

  throw new Error(
    'GROQ_API_KEY not found. Set in env, .env.local, or Convex (npx convex env set GROQ_API_KEY ...).',
  )
}

function resolveModel(): string {
  return process.env.GROQ_MODEL?.trim() || DEFAULT_MODEL
}

function isSchemaMismatchMessage(message: string): boolean {
  return (
    message.includes('does not match the expected schema') ||
    message.includes('jsonschema') ||
    message.includes('failed_generation')
  )
}

async function fetchGroqCompletion(
  apiKey: string,
  model: string,
  messages: GroqChatMessage[],
  mode: GroqResponseMode,
): Promise<{ content: string; schemaMismatch?: { message: string; failedGeneration?: string } }> {
  const body: Record<string, unknown> = {
    model,
    messages,
    stream: false,
  }

  if (mode === 'json') {
    body.response_format = {
      type: 'json_schema',
      json_schema: {
        name: SCHEMA_NAME,
        strict: true,
        schema: KYNO_WIDGET_JSON_SCHEMA,
      },
    }
  } else {
    body.response_format = { type: 'json_object' }
  }

  const response = await fetch(GROQ_CHAT_URL, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })

  const payload = (await response.json()) as {
    choices?: Array<{ message?: { content?: string | null } }>
    error?: { message?: string; failed_generation?: string }
  }

  if (!response.ok) {
    const groqMessage = payload.error?.message ?? `Groq request failed (${response.status})`
    if (isSchemaMismatchMessage(groqMessage)) {
      return {
        content: '',
        schemaMismatch: {
          message: groqMessage,
          failedGeneration: payload.error?.failed_generation,
        },
      }
    }
    throw new Error(groqMessage)
  }

  const content = payload.choices?.[0]?.message?.content?.trim()
  if (!content) {
    throw new Error('Empty Groq response')
  }

  return { content }
}

function buildCorrectionMessage(failure: WidgetParseFailure, rejectedOutput?: string): string {
  const lines = [WIDGET_CORRECTION_PREFIX, '', widgetRetryHint(failure)]
  const snippet = rejectedOutput?.trim() || failure.raw?.trim() || ''
  if (snippet) {
    lines.push('', `Rejected output:\n${snippet.slice(0, 1000)}`)
  }
  return lines.join('\n')
}

type FetchResult = {
  raw: string
  attempts: number
  widgetTypes: string[]
  validationOk: boolean
  failureMessage?: string
}

async function fetchWidgetReply(
  apiKey: string,
  model: string,
  userMessage: string,
): Promise<FetchResult> {
  let groqMessages: GroqChatMessage[] = [
    { role: 'system', content: WIDGET_SYSTEM_PROMPT },
    { role: 'user', content: userMessage },
  ]

  let lastRaw = ''
  let lastFailureMessage = 'Validation failed'
  let attempts = 0

  for (let attempt = 1; attempt <= MAX_WIDGET_ATTEMPTS; attempt++) {
    attempts = attempt
    const mode: GroqResponseMode = attempt === 1 ? 'json' : 'json_object'

    const result = await fetchGroqCompletion(apiKey, model, groqMessages, mode)

    if (result.schemaMismatch) {
      lastFailureMessage = result.schemaMismatch.message
      if (attempt >= MAX_WIDGET_ATTEMPTS) {
        return {
          raw: result.schemaMismatch.failedGeneration ?? '',
          attempts,
          widgetTypes: [],
          validationOk: false,
          failureMessage: lastFailureMessage,
        }
      }

      const schemaFailure: WidgetParseFailure = {
        stage: 'batch',
        message: result.schemaMismatch.message,
        raw: result.schemaMismatch.failedGeneration ?? '',
      }
      const correction = buildCorrectionMessage(schemaFailure, result.schemaMismatch.failedGeneration)
      groqMessages = [
        ...groqMessages,
        ...(result.schemaMismatch.failedGeneration
          ? [{ role: 'assistant' as const, content: result.schemaMismatch.failedGeneration }]
          : []),
        { role: 'user', content: correction },
      ]
      continue
    }

    lastRaw = result.content
    const parsed = parseKynoWidgetBatchDetailed(result.content, { applyDefaults: true })

    if (parsed.ok) {
      return {
        raw: result.content,
        attempts,
        widgetTypes: parsed.widgets.map((w) => w.type),
        validationOk: true,
      }
    }

    lastFailureMessage = parsed.failure.message

    if (attempt >= MAX_WIDGET_ATTEMPTS) {
      return {
        raw: result.content,
        attempts,
        widgetTypes: [],
        validationOk: false,
        failureMessage: lastFailureMessage,
      }
    }

    const correction = buildCorrectionMessage(parsed.failure, result.content)
    groqMessages = [
      ...groqMessages,
      { role: 'assistant', content: result.content },
      { role: 'user', content: correction },
    ]
  }

  return {
    raw: lastRaw,
    attempts,
    widgetTypes: [],
    validationOk: false,
    failureMessage: lastFailureMessage,
  }
}

/** True if actual types contain expectTypes as an ordered subsequence. */
function typesMatchExpectation(actual: string[], expect: string[]): boolean {
  if (expect.length === 0) return true
  let j = 0
  for (const t of actual) {
    if (t === expect[j]) j++
    if (j === expect.length) return true
  }
  return j === expect.length
}

function scenarioPass(result: FetchResult, scenario: Scenario): boolean {
  if (!result.validationOk) return false
  return typesMatchExpectation(result.widgetTypes, scenario.expectTypes)
}

async function main(): Promise<void> {
  const apiKey = loadGroqApiKey()
  const model = resolveModel()

  console.log(`\nKyno widget prompt test — model: ${model}\n`)
  console.log('='.repeat(80))

  const rows: Array<{
    id: string
    expect: string
    actual: string
    valid: boolean
    semantic: boolean
    attempts: number
    issue?: string
  }> = []

  for (const scenario of SCENARIOS) {
    console.log(`\n▶ ${scenario.id}: "${scenario.userMessage}"`)
    if (scenario.notes) console.log(`  (${scenario.notes})`)

    try {
      const result = await fetchWidgetReply(apiKey, model, scenario.userMessage)
      const semantic = scenarioPass(result, scenario)

      console.log(`  attempts: ${result.attempts}`)
      console.log(`  validation: ${result.validationOk ? 'PASS' : 'FAIL'}`)
      console.log(`  semantic: ${semantic ? 'PASS' : 'FAIL'}`)
      console.log(`  widget types: [${result.widgetTypes.join(', ')}]`)
      console.log(`  expected (subsequence): [${scenario.expectTypes.join(', ')}]`)
      if (result.failureMessage) console.log(`  failure: ${result.failureMessage}`)
      console.log(`  raw JSON:\n${result.raw.slice(0, 1200)}${result.raw.length > 1200 ? '…' : ''}`)

      rows.push({
        id: scenario.id,
        expect: scenario.expectTypes.join(' → '),
        actual: result.widgetTypes.join(' → ') || '(none)',
        valid: result.validationOk,
        semantic,
        attempts: result.attempts,
        issue: !result.validationOk
          ? result.failureMessage
          : !semantic
            ? `got [${result.widgetTypes.join(', ')}], wanted subsequence [${scenario.expectTypes.join(', ')}]`
            : undefined,
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      console.log(`  ERROR: ${message}`)
      rows.push({
        id: scenario.id,
        expect: scenario.expectTypes.join(' → '),
        actual: 'ERROR',
        valid: false,
        semantic: false,
        attempts: 0,
        issue: message,
      })
    }

    // Brief pause to avoid rate limits
    await new Promise((r) => setTimeout(r, 500))
  }

  const validCount = rows.filter((r) => r.valid).length
  const semanticCount = rows.filter((r) => r.semantic).length
  const total = rows.length

  console.log('\n' + '='.repeat(80))
  console.log('\n## Summary table\n')
  console.log('| Scenario | Expected | Actual | Valid | Semantic | Attempts | Issue |')
  console.log('|----------|----------|--------|-------|----------|----------|-------|')
  for (const r of rows) {
    const issue = (r.issue ?? '').replace(/\|/g, '/').slice(0, 60)
    console.log(
      `| ${r.id} | ${r.expect} | ${r.actual} | ${r.valid ? '✓' : '✗'} | ${r.semantic ? '✓' : '✗'} | ${r.attempts} | ${issue} |`,
    )
  }

  console.log(`\nValidation pass rate: ${validCount}/${total} (${Math.round((validCount / total) * 100)}%)`)
  console.log(`Semantic pass rate: ${semanticCount}/${total} (${Math.round((semanticCount / total) * 100)}%)`)

  const failed = rows.filter((r) => !r.semantic)
  if (failed.length > 0) {
    console.log('\n## Issues\n')
    for (const r of failed) {
      console.log(`- **${r.id}**: ${r.issue}`)
    }
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error)
  process.exit(1)
})
