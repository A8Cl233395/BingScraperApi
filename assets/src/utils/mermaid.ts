import DOMPurify from 'dompurify'
import hljs from 'highlight.js/lib/common'

interface MermaidInstance {
  initialize: (config: Record<string, unknown>) => void
  render: (id: string, code: string) => Promise<{ svg: string }>
}

let mermaidPromise: Promise<MermaidInstance> | null = null
let initialized = false
const svgCache = new Map<string, string>()
let renderCounter = 0

const MERMAID_PLACEHOLDER_RE = /<div class="mermaid-placeholder" data-code="([^"]*)" style="min-height: 2rem;"><\/div>/g

async function getMermaid(): Promise<MermaidInstance> {
  if (!mermaidPromise) {
    mermaidPromise = import('mermaid').then(m => (m.default || m) as unknown as MermaidInstance)
  }
  return mermaidPromise
}

async function initMermaid(): Promise<void> {
  if (initialized) return
  const mermaid = await getMermaid()

  const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    || document.documentElement.classList.contains('dark')

  const getVar = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()

  mermaid.initialize({
    startOnLoad: false,
    theme: isDark ? 'dark' : 'default',
    securityLevel: 'strict',
    fontFamily: 'inherit',
    flowchart: {
      useMaxWidth: true,
      htmlLabels: true,
      curve: 'basis',
    },
    sequence: {
      useMaxWidth: true,
      actorMargin: 50,
      mirrorActors: false,
      bottomMarginAdj: 1,
    },
    gantt: {
      useMaxWidth: true,
    },
    themeVariables: {
      primaryColor: getVar('--bg-active'),
      primaryTextColor: getVar('--text-main'),
      primaryBorderColor: getVar('--border-color'),
      lineColor: getVar('--text-placeholder'),
      secondaryColor: getVar('--bg-panel'),
      tertiaryColor: getVar('--bg-main'),
      noteBkgColor: getVar('--bg-panel'),
      noteTextColor: getVar('--text-muted'),
      noteBorderColor: getVar('--border-color'),
      edgeLabelBackground: getVar('--bg-main'),
      clusterBkg: getVar('--bg-panel'),
      clusterBorder: getVar('--border-color'),
      actorTextColor: getVar('--text-main'),
      actorBkg: getVar('--bg-active'),
      actorBorder: getVar('--border-color'),
      signalColor: getVar('--text-main'),
      signalTextColor: getVar('--text-main'),
      labelBoxBkgColor: getVar('--bg-panel'),
      labelBoxBorderColor: getVar('--border-color'),
      labelTextColor: getVar('--text-main'),
      loopTextColor: getVar('--text-main'),
      activationBorderColor: getVar('--border-color'),
      activationBkgColor: getVar('--bg-active'),
      sequenceNumberColor: getVar('--primary-text'),
    },
  })
  initialized = true
}

export function protectMermaidPlaceholders(html: string): { html: string; restore: (h: string) => string } {
  const codes = new Map<string, string>()
  let idx = 0
  const processed = html.replace(MERMAID_PLACEHOLDER_RE, (_match, code) => {
    const key = `__MRM_${idx++}__`
    codes.set(key, code)
    return key
  })
  return {
    html: processed,
    restore: (h: string) => {
      for (const [key, code] of codes) {
        h = h.replace(key, `<div class="mermaid-placeholder" data-code="${code}" style="min-height: 2rem;"></div>`)
      }
      return h
    }
  }
}

export async function renderMermaidPlaceholders(root: Element | Document = document): Promise<void> {
  const blocks = root.querySelectorAll('.mermaid-block:not(.rendered)')
  if (blocks.length === 0) return

  const mermaid = await getMermaid()
  await initMermaid()

  for (const block of Array.from(blocks)) {
    const chartEl = block.querySelector('.mermaid-chart') as HTMLElement
    const sourceEl = block.querySelector('.mermaid-source') as HTMLElement
    if (!chartEl || !sourceEl) continue

    const code = sourceEl.querySelector('code')?.textContent || ''
    if (!code) continue

    block.classList.add('rendered')

    // 对源码进行hljs高亮
    const codeEl = sourceEl.querySelector('code')
    if (codeEl) {
      try {
        const highlighted = hljs.highlight(code, { language: 'mermaid' }).value
        codeEl.innerHTML = highlighted
      } catch {
        // 如果mermaid语言不支持，尝试自动检测
        try {
          const highlighted = hljs.highlightAuto(code).value
          codeEl.innerHTML = highlighted
        } catch {
          // 保持原始文本
        }
      }
    }

    const cached = svgCache.get(code)
    if (cached) {
      chartEl.innerHTML = cached
      enableInteractivity(chartEl)
      continue
    }

    const id = `mermaid-${++renderCounter}-${Date.now()}`
    try {
      const { svg } = await mermaid.render(id, code)
      const sanitized = DOMPurify.sanitize(svg, {
        USE_PROFILES: { svg: true },
        ADD_TAGS: ['foreignObject'],
        ADD_ATTR: ['transform', 'style', 'class']
      })
      svgCache.set(code, sanitized)
      chartEl.innerHTML = sanitized
      enableInteractivity(chartEl)
    } catch (error) {
      console.warn('Mermaid 渲染失败:', error)
      chartEl.innerHTML = `<div class="mermaid-error"><strong>图表渲染失败</strong><pre>${escapeHtml(code)}</pre></div>`
    }
  }
}

function enableInteractivity(container: HTMLElement): void {
  const svg = container.querySelector('svg') as SVGSVGElement | null
  if (!svg) return

  svg.style.maxWidth = '100%'
  svg.style.height = 'auto'
}

function escapeHtml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
