/** Prose line while inside an unclosed display-math block — close math before this line. */
function looksLikeProseLine(line: string): boolean {
  const trimmed = line.trim()
  if (!trimmed || trimmed.startsWith('$$')) {
    return false
  }
  return /\b[a-zA-Z]{4,}\b/.test(trimmed)
}

/**
 * Close dangling `$$` display math so markdown-it-katex does not swallow following prose.
 * Handles LLM output like `$$f'(x)=...` without a closing delimiter on the same line.
 */
export function closeUnclosedDisplayMathDelimiters(content: string): string {
  const lines = content.split('\n')
  let inBlock = false
  const result: string[] = []

  for (const line of lines) {
    if (inBlock && looksLikeProseLine(line)) {
      const prev = result[result.length - 1]
      if (prev !== undefined && !/\$\$\s*$/.test(prev.trimEnd())) {
        result[result.length - 1] = `${prev}$$`
      }
      inBlock = false
    }

    result.push(line)

    const dollarCount = (line.match(/\$\$/g) ?? []).length
    if (dollarCount % 2 === 1) {
      inBlock = !inBlock
    }
  }

  if (inBlock) {
    const last = result[result.length - 1]
    if (last !== undefined && !/\$\$\s*$/.test(last.trimEnd())) {
      result[result.length - 1] = `${last}$$`
    }
  }

  return result.join('\n')
}

/** Convert LaTeX delimiters to markdown-it-katex form: `\(\)` → `$ $`, `\[\]` → `$$ $$`. */
export function normalizeMathDelimiters(content: string): string {
  const converted = content
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, math) => `$$\n${math.trim()}\n$$`)
    .replace(/\\\(([\s\S]*?)\\\)/g, (_, math) => `$${math}$`)

  return closeUnclosedDisplayMathDelimiters(converted)
}
