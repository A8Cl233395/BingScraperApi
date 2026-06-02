import DOMPurify from 'dompurify'

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
  const placeholders = root.querySelectorAll('.mermaid-placeholder:not(.rendered)')
  if (placeholders.length === 0) return

  const mermaid = await getMermaid()
  await initMermaid()

  for (const el of Array.from(placeholders)) {
    const code = el.getAttribute('data-code')
    if (!code) continue
    el.classList.add('rendered')

    const cached = svgCache.get(code)
    if (cached) {
      el.innerHTML = cached
      enableInteractivity(el as HTMLElement)
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
      el.innerHTML = sanitized
      enableInteractivity(el as HTMLElement)
    } catch (error) {
      console.warn('Mermaid 渲染失败:', error)
      el.innerHTML = `<div class="mermaid-error"><strong>图表渲染失败</strong><pre>${escapeHtml(code)}</pre></div>`
    }
  }
}

const containerCleanupMap = new WeakMap<HTMLElement, AbortController>()

function enableInteractivity(container: HTMLElement): void {
  // 清理之前的事件监听器
  const existingController = containerCleanupMap.get(container)
  if (existingController) {
    existingController.abort()
  }

  const svg = container.querySelector('svg') as SVGSVGElement | null
  if (!svg) return

  const controller = new AbortController()
  containerCleanupMap.set(container, controller)
  const { signal } = controller

  svg.style.maxWidth = '100%'
  svg.style.height = 'auto'
  svg.style.cursor = 'grab'

  let scale = 1
  let translateX = 0
  let translateY = 0
  let isPanning = false
  let startX = 0
  let startY = 0

  function updateTransform() {
    svg!.style.transform = `translate(${translateX}px, ${translateY}px) scale(${scale})`
    svg!.style.transformOrigin = 'center center'
  }

  svg.addEventListener('wheel', (e) => {
    e.preventDefault()
    const delta = e.deltaY > 0 ? -0.1 : 0.1
    scale = Math.min(Math.max(scale + delta, 0.5), 3)
    updateTransform()
  }, { passive: false, signal })

  svg.addEventListener('mousedown', (e) => {
    isPanning = true
    startX = e.clientX - translateX
    startY = e.clientY - translateY
    svg!.style.cursor = 'grabbing'
  }, { signal })

  window.addEventListener('mousemove', (e) => {
    if (!isPanning) return
    translateX = e.clientX - startX
    translateY = e.clientY - startY
    updateTransform()
  }, { signal })

  window.addEventListener('mouseup', () => {
    isPanning = false
    svg!.style.cursor = 'grab'
  }, { signal })

  svg.addEventListener('dblclick', () => {
    scale = 1
    translateX = 0
    translateY = 0
    svg!.style.transition = 'transform 0.3s ease'
    updateTransform()
    setTimeout(() => { svg!.style.transition = '' }, 300)
  }, { signal })

  svg.setAttribute('title', '滚轮缩放 | 拖拽平移 | 双击重置')
}

function escapeHtml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
