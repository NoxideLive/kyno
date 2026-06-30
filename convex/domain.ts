export type DomainClassification = {
  label: 'on_topic' | 'off_topic'
  confidence: number
  backend: string
  blocked: boolean
}

export type ClassifyDomainResult =
  | { ok: true; classification: DomainClassification }
  | { ok: false; reason: 'disabled' | 'unconfigured' | 'error' }

const OFF_TOPIC_MESSAGE =
  'I only help with South African CAPS Mathematics (Grades 1–12) — syllabus, teaching plans, assessments, and study help.'

const OFF_TOPIC_SUGGESTION =
  'Try asking about a CAPS Maths topic, grade, or ATP week.'

const GATEWAY_UNAVAILABLE_MESSAGE =
  'Domain check is temporarily unavailable. Please try again shortly.'

export function offTopicUserMessage(): string {
  return OFF_TOPIC_MESSAGE
}

export function offTopicSuggestion(): string {
  return OFF_TOPIC_SUGGESTION
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

export async function classifyDomain(text: string): Promise<ClassifyDomainResult> {
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
    const response = await fetch(`${baseUrl.replace(/\/$/, '')}/classify/domain`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ text }),
      signal: AbortSignal.timeout(5000),
    })

    if (!response.ok) {
      return { ok: false, reason: 'error' }
    }

    const payload = (await response.json()) as DomainClassification
    return { ok: true, classification: payload }
  } catch {
    return { ok: false, reason: 'error' }
  }
}

export function shouldBlockDomain(
  classification: DomainClassification,
  threshold?: number,
): boolean {
  const cutoff = threshold ?? Number(process.env.DOMAIN_CONFIDENCE_THRESHOLD ?? '0.55')
  return classification.label === 'off_topic' || classification.confidence < cutoff
}
