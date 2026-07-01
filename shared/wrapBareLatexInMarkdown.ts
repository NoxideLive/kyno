/** Common LaTeX commands used to detect bare math in markdown prose. */
const LATEX_CMD =
  /\\(?:frac|sqrt|sum|int|lim|sin|cos|tan|log|ln|alpha|beta|gamma|delta|epsilon|pi|theta|infty|partial|nabla|times|div|pm|cdot|ldots|text|mathrm|mathbf|vec|bar|hat|tilde|left|right|begin|end)\b/

const FENCED_CODE_RE = /(```[\w-]*\n[\s\S]*?```|~~~[\w-]*\n[\s\S]*?~~~)/g

function proseWordCount(line: string): number {
  const stripped = line
    .replace(/\\[a-zA-Z]+/g, ' ')
    .replace(/[^a-zA-Z\s]/g, ' ')
  return (stripped.match(/\b[a-zA-Z]{4,}\b/g) ?? []).length
}

function lineHasMathDelimiters(line: string): boolean {
  return /\$\$[\s\S]+?\$\$/.test(line) || /(?:^|[^\\])\$[^$\n]+?\$/.test(line)
}

function lineHasDisplayMathDelimiter(line: string): boolean {
  return line.includes('$$')
}

/** Entire line is display math without prose — wrap in $$...$$. */
export function isBareLatexLine(line: string): boolean {
  const trimmed = line.trim()
  if (!trimmed) {
    return false
  }
  if (lineHasMathDelimiters(line) || lineHasDisplayMathDelimiter(line)) {
    return false
  }
  if (proseWordCount(trimmed) >= 2) {
    return false
  }
  if (LATEX_CMD.test(trimmed)) {
    return true
  }
  if (/=/.test(trimmed) && /\\|[\^_{}]/.test(trimmed) && proseWordCount(trimmed) === 0) {
    return true
  }
  if (/^[a-zA-Z]'?\([^)]*\)\s*=/.test(trimmed) && /\\|[\^_{}]/.test(trimmed)) {
    return true
  }
  return false
}

/** Parenthetical expression that should render as inline math, e.g. (f(x)=x^n). */
export function looksLikeMathParen(inner: string): boolean {
  const t = inner.trim()
  if (!t || t.length > 120) {
    return false
  }
  if (LATEX_CMD.test(t)) {
    return true
  }
  if (/=/.test(t) && /[\^_]/.test(t) && /^[a-zA-Z0-9'\\^_{}\s=+\-*/.,()]+$/.test(t)) {
    return true
  }
  return false
}

function wrapInlineMathInSegment(segment: string): string {
  return segment.replace(/\(([^()]*(?:\([^()]*\)[^()]*)*)\)/g, (full, inner: string) => {
    if (looksLikeMathParen(inner)) {
      return `$${inner.trim()}$`
    }
    return full
  })
}

function processLine(line: string): string {
  if (isBareLatexLine(line)) {
    const indent = line.match(/^\s*/)?.[0] ?? ''
    return `${indent}$$${line.trim()}$$`
  }

  const parts = line.split(/(`+[^`]*`+)/g)
  return parts
    .map((part) => {
      if (part.startsWith('`')) {
        return part
      }
      return wrapInlineMathInSegment(part)
    })
    .join('')
}

function processTextBlock(text: string): string {
  if (!text) {
    return text
  }

  let inDisplayMath = false
  const lines = text.split('\n')
  const processed: string[] = []

  for (const line of lines) {
    if (inDisplayMath) {
      processed.push(line)
      const dollarCount = (line.match(/\$\$/g) ?? []).length
      if (dollarCount % 2 === 1) {
        inDisplayMath = !inDisplayMath
      }
      continue
    }

    processed.push(processLine(line))

    const dollarCount = (line.match(/\$\$/g) ?? []).length
    if (dollarCount % 2 === 1) {
      inDisplayMath = true
    }
  }

  return processed.join('\n')
}

/**
 * Wrap bare LaTeX in markdown with $ / $$ delimiters for markdown-it-katex.
 * Skips fenced code blocks; respects existing delimiters and inline code.
 */
export function wrapBareLatexInMarkdown(content: string): string {
  if (!content) {
    return content
  }

  const chunks: string[] = []
  let lastIndex = 0

  FENCED_CODE_RE.lastIndex = 0
  let match: RegExpExecArray | null
  while ((match = FENCED_CODE_RE.exec(content)) !== null) {
    if (match.index > lastIndex) {
      chunks.push(processTextBlock(content.slice(lastIndex, match.index)))
    }
    chunks.push(match[1])
    lastIndex = match.index + match[1].length
  }

  if (lastIndex < content.length) {
    chunks.push(processTextBlock(content.slice(lastIndex)))
  }

  return chunks.length > 0 ? chunks.join('') : processTextBlock(content)
}
