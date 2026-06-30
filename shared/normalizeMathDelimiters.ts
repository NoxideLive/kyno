/** Convert LaTeX delimiters to markdown-it-katex form: `\(\)` → `$ $`, `\[\]` → `$$ $$`. */
export function normalizeMathDelimiters(content: string): string {
  return content
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, math) => `$$\n${math.trim()}\n$$`)
    .replace(/\\\(([\s\S]*?)\\\)/g, (_, math) => `$${math}$`)
}
