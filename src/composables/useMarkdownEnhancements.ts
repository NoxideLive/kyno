import { nextTick, onBeforeUnmount, onMounted, watch, type Ref, type WatchSource } from 'vue'

function enhanceCodeBlocks(root: HTMLElement): void {
  root.querySelectorAll('pre.shiki, pre code.hljs').forEach((pre) => {
    const block = pre instanceof HTMLPreElement ? pre : pre.closest('pre')
    if (!block || block.closest('.code-block')) return

    const wrapper = document.createElement('div')
    wrapper.className = 'code-block'
    block.parentNode?.insertBefore(wrapper, block)
    wrapper.appendChild(block)

    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'code-block__copy'
    button.setAttribute('aria-label', 'Copy code')
    button.dataset.copyCode = ''
    button.innerHTML =
      '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
    wrapper.appendChild(button)
  })
}

async function copyCode(button: HTMLButtonElement): Promise<void> {
  const wrapper = button.closest('.code-block')
  const code = wrapper?.querySelector('pre code') ?? wrapper?.querySelector('pre')
  const text = code?.textContent ?? ''
  if (!text) return

  try {
    await navigator.clipboard.writeText(text)
    button.classList.add('code-block__copy--copied')
    button.setAttribute('aria-label', 'Copied')
    window.setTimeout(() => {
      button.classList.remove('code-block__copy--copied')
      button.setAttribute('aria-label', 'Copy code')
    }, 1500)
  } catch {
    // Clipboard unavailable — leave button unchanged.
  }
}

export function useMarkdownEnhancements(
  containerRef: Ref<HTMLElement | null>,
  watchSource: WatchSource<unknown>,
): void {
  async function refresh(): Promise<void> {
    await nextTick()
    if (containerRef.value) {
      enhanceCodeBlocks(containerRef.value)
    }
  }

  function onClick(event: MouseEvent): void {
    const target = event.target
    if (!(target instanceof Element)) return
    const button = target.closest<HTMLButtonElement>('[data-copy-code]')
    if (!button || !containerRef.value?.contains(button)) return
    void copyCode(button)
  }

  watch(watchSource, () => {
    void refresh()
  }, { flush: 'post' })

  onMounted(() => {
    containerRef.value?.addEventListener('click', onClick)
    void refresh()
  })

  onBeforeUnmount(() => {
    containerRef.value?.removeEventListener('click', onClick)
  })
}
