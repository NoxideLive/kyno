import { normalizeMathDelimiters } from './normalizeMathDelimiters'

/** Normalize message source (math delimiters, trim). Safe to run at persist and render. */
export function prepareMessageContent(raw: string): string {
  return normalizeMathDelimiters(raw.trim())
}
