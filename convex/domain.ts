import { ConvexError } from 'convex/values'

export type JailbreakLabel = 'safe' | 'jailbreak_attempted'
export type DomainLabel = 'on_topic' | 'off_topic'
export type BlockReason = 'jailbreak_attempted' | 'off_topic'

export type StageClassification = {
  label: string
  confidence: number
  backend: string
}

export type CompiledClassification = {
  allowed: boolean
  blocked: boolean
  block_reason: BlockReason | null
  jailbreak: StageClassification
  domain: StageClassification
  backend: string
}

export type ClassifyMessageResult =
  | { ok: true; classification: CompiledClassification }
  | { ok: false; reason: 'disabled' | 'unconfigured' | 'error' }

export type MessageHistoryTurn = {
  role: 'user' | 'assistant'
  content: string
}

const DOMAIN_BLOCK_MESSAGE =
  'I can only help with South African CAPS Mathematics (Grades 1–12) — syllabus, teaching plans, assessments, and study help.'

const DOMAIN_BLOCK_SUGGESTION =
  'Try asking about a CAPS Maths topic, grade, or ATP week.'

const GATEWAY_UNAVAILABLE_MESSAGE =
  'Domain check is temporarily unavailable. Please try again shortly.'

export function offTopicUserMessage(): string {
  return DOMAIN_BLOCK_MESSAGE
}

export function offTopicSuggestion(): string {
  return DOMAIN_BLOCK_SUGGESTION
}

export function domainGatewayUnavailableMessage(): string {
  return GATEWAY_UNAVAILABLE_MESSAGE
}

export function isDomainGatewayEnabled(): boolean {
  const flag = process.env.DOMAIN_GATEWAY_ENABLED?.trim().toLowerCase()
  return flag === 'true' || flag === '1'
}

function gatewayUrl(): string | null {
  const url = process.env.PHI_GATEWAY_URL?.trim()
  return url || null
}

export async function classifyMessage(
  text: string,
  history: MessageHistoryTurn[] = [],
): Promise<ClassifyMessageResult> {
  if (!isDomainGatewayEnabled()) {
    return { ok: false, reason: 'disabled' }
  }

  const baseUrl = gatewayUrl()
  if (!baseUrl) {
    return { ok: false, reason: 'unconfigured' }
  }

  const apiKey = process.env.PHI_GATEWAY_API_KEY?.trim()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (apiKey) {
    headers.Authorization = `Bearer ${apiKey}`
  }

  try {
    const response = await fetch(`${baseUrl.replace(/\/$/, '')}/classify/message`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ text, history }),
      signal: AbortSignal.timeout(5000),
    })

    if (!response.ok) {
      return { ok: false, reason: 'error' }
    }

    const payload = (await response.json()) as CompiledClassification
    return { ok: true, classification: payload }
  } catch {
    return { ok: false, reason: 'error' }
  }
}

export function shouldBlockMessage(classification: CompiledClassification): boolean {
  return classification.blocked
}

export function messageBlockPayload(_classification: CompiledClassification): {
  code: 'OFF_TOPIC'
  message: string
  suggestion: string
} {
  return {
    code: 'OFF_TOPIC',
    message: offTopicUserMessage(),
    suggestion: offTopicSuggestion(),
  }
}

export async function assertMessageAllowed(
  text: string,
  history: MessageHistoryTurn[] = [],
): Promise<void> {
  const messageResult = await classifyMessage(text, history)
  if (!messageResult.ok) {
    if (isDomainGatewayEnabled()) {
      throw new ConvexError({
        code: 'DOMAIN_GATEWAY_UNAVAILABLE',
        message: domainGatewayUnavailableMessage(),
      })
    }
    return
  }
  if (shouldBlockMessage(messageResult.classification)) {
    const block = messageBlockPayload(messageResult.classification)
    throw new ConvexError({
      code: block.code,
      message: block.message,
      suggestion: block.suggestion,
    })
  }
}
