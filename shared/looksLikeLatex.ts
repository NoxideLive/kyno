/** Heuristic: treat content as LaTeX when it uses common math delimiters/commands. */
export function looksLikeLatex(text: string): boolean {
  const trimmed = text.trim()
  if (!trimmed) {
    return false
  }

  if (trimmed.includes('\\frac') || trimmed.includes('\\sqrt') || trimmed.includes('\\')) {
    return true
  }

  return /[\^_]/.test(trimmed)
}

/** Heuristic: content should live in a notation widget, not question/confirm/response text. */
export function looksLikeNotationContent(text: string): boolean {
  const trimmed = text.trim()
  if (!trimmed) {
    return false
  }

  if (looksLikeLatex(trimmed)) {
    return true
  }

  // Chemical subscripts/superscripts (H₂O, CO₂, x²)
  if (/[\u2080-\u209F\u00B2\u00B3]/.test(trimmed)) {
    return true
  }

  // Algebraic exponent like x^2
  if (/[a-zA-Z]\s*\^/.test(trimmed)) {
    return true
  }

  // Equation or symbolic math with =
  if (trimmed.includes('=')) {
    if (/[\+\-\*\/]|\d\s*[a-zA-Z]|[a-zA-Z]\s*\d/.test(trimmed)) {
      return true
    }
  }

  return false
}
