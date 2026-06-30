declare module 'markdown-it-multimd-table' {
  import type MarkdownIt from 'markdown-it'

  interface MultimdTableOptions {
    multiline?: boolean
    rowspan?: boolean
    headerless?: boolean
  }

  function markdownItMultimdTable(
    md: MarkdownIt,
    options?: MultimdTableOptions,
  ): void

  export default markdownItMultimdTable
}
