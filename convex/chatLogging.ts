const LOG_PREFIX = '[kyno:groq]'

export function logGroq(event: string, data: Record<string, unknown>): void {
  console.log(LOG_PREFIX, event, JSON.stringify(data))
}

/** Short deterministic hash for correlating prompts without logging full text. */
export function hashText(text: string): string {
  let hash = 0
  for (let i = 0; i < text.length; i++) {
    hash = (Math.imul(31, hash) + text.charCodeAt(i)) | 0
  }
  return (hash >>> 0).toString(16).padStart(8, '0')
}

export function truncate(text: string, max = 500): string {
  if (text.length <= max) {
    return text
  }
  return `${text.slice(0, max)}… (${text.length} chars total)`
}

export function systemPromptMeta(systemPrompt: string | undefined): {
  length: number
  hash: string
} | undefined {
  if (!systemPrompt) {
    return undefined
  }
  return {
    length: systemPrompt.length,
    hash: hashText(systemPrompt),
  }
}
