import DOMPurify from 'dompurify'
import hljs from 'highlight.js/lib/common'

// Lucide 图标的 SVG 属性与内部元素（用于重置按钮的 HTML 字符串）
const lucideSvgAttrs = 'xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"';
const rotateCcwIconInner = '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>';

interface MermaidInstance {
  initialize: (config: Record<string, unknown>) => void
  render: (id: string, code: string) => Promise<{ svg: string }>
  parse: (code: string) => Promise<boolean>
}

let mermaidPromise: Promise<MermaidInstance> | null = null
let initialized = false
const svgCache = new Map<string, string>()
const chartCache = new Map<string, string>()
let renderCounter = 0
const cleanupMap = new WeakMap<HTMLElement, () => void>()

export function normalizeMermaidCode(code: string): string {
  return (code || '').replace(/\r\n/g, '\n').trim()
}

export function getCachedMermaidSvg(code: string): string | undefined {
  return svgCache.get(normalizeMermaidCode(code))
}

export function getCachedMermaidChartHtml(code: string): string | undefined {
  return chartCache.get(normalizeMermaidCode(code))
}

export function getSvgDataUrl(code: string): string | null {
  const svg = svgCache.get(normalizeMermaidCode(code))
  if (!svg) return null
  return `data:image/svg+xml,${encodeURIComponent(svg)}`
}


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


/** 用新 SVG 替换 inner 中的旧 SVG（复用缩放 wrapper 时保留缩放状态） */
function swapInnerSvg(inner: HTMLElement, svg: SVGSVGElement): void {
  const oldSvg = inner.querySelector('svg')
  if (oldSvg) oldSvg.remove()
  inner.appendChild(svg)
}

/**
 * 将 SVG 接入图表容器：无缩放 wrapper 时整体注入；
 * 已有 wrapper 时仅替换其中的 SVG（流式更新时保留缩放状态）
 */
function mountChartSvg(chartEl: HTMLElement, svgHtml: string): void {
  const existingWrapper = chartEl.querySelector('.mermaid-zoom-wrapper')
  if (!existingWrapper) {
    chartEl.innerHTML = svgHtml
    return
  }
  const inner = existingWrapper.querySelector('.mermaid-zoom-inner') as HTMLElement | null
  const temp = document.createElement('div')
  temp.innerHTML = svgHtml
  const newSvg = temp.querySelector('svg')
  if (inner && newSvg) swapInnerSvg(inner, newSvg)
}

export async function renderMermaidPlaceholders(root: Element | Document = document): Promise<void> {
  const blocks = root.querySelectorAll('.mermaid-block.mermaid-complete:not(.rendered)')
  if (blocks.length === 0) return

  const mermaid = await getMermaid()
  await initMermaid()

  const scrollContainer = document.getElementById('message-container')

  for (const block of Array.from(blocks)) {
    const chartEl = block.querySelector('.mermaid-chart') as HTMLElement
    const sourceEl = block.querySelector('.mermaid-source') as HTMLElement
    if (!chartEl || !sourceEl) continue

    const rawCode = sourceEl.querySelector('code')?.textContent || ''
    if (!rawCode) continue
    const code = normalizeMermaidCode(rawCode)

    block.classList.add('rendered')

    // 对源码进行hljs高亮
    const codeEl = sourceEl.querySelector('code')
    if (codeEl) {
      try {
        const highlighted = hljs.highlight(rawCode, { language: 'mermaid' }).value
        codeEl.innerHTML = highlighted
      } catch {
        // 如果mermaid语言不支持，尝试自动检测
        try {
          const highlighted = hljs.highlightAuto(rawCode).value
          codeEl.innerHTML = highlighted
        } catch {
          // 保持原始文本
        }
      }
    }

    // 记录 DOM 更改前视口及 scrollContainer 状态，避免注入大图引发视觉跳动
    let preScrollTop = 0
    let preScrollHeight = 0
    let isUserScrolledUp = false
    let blockTopRelativeToContainer = 0
    if (scrollContainer) {
      preScrollTop = scrollContainer.scrollTop
      preScrollHeight = scrollContainer.scrollHeight
      const isAtBottom = Math.abs(preScrollHeight - preScrollTop - scrollContainer.clientHeight) <= 20
      isUserScrolledUp = !isAtBottom
      const cRect = scrollContainer.getBoundingClientRect()
      const bRect = block.getBoundingClientRect()
      blockTopRelativeToContainer = bRect.top - cRect.top
    }

    const cached = svgCache.get(code)
    if (cached) {
      mountChartSvg(chartEl, cached)
      enableInteractivity(chartEl)
      chartCache.set(code, chartEl.innerHTML)
      continue
    }

    const id = `mermaid-${++renderCounter}-${Date.now()}`
    try {
      await mermaid.parse(code)
      const { svg } = await mermaid.render(id, code)
      const sanitized = DOMPurify.sanitize(svg, {
        USE_PROFILES: { svg: true },
        ADD_TAGS: ['foreignObject'],
        ADD_ATTR: ['transform', 'style', 'class']
      })
      svgCache.set(code, sanitized)

      mountChartSvg(chartEl, sanitized)
      enableInteractivity(chartEl)
      chartCache.set(code, chartEl.innerHTML)

      // 若用户主动向上阅读，锚定滚动位置
      if (scrollContainer && isUserScrolledUp) {
        const heightDiff = scrollContainer.scrollHeight - preScrollHeight
        if (heightDiff > 0 && blockTopRelativeToContainer <= scrollContainer.clientHeight) {
          scrollContainer.scrollTop = preScrollTop + heightDiff
        }
      }
    } catch {
      chartEl.innerHTML = `<div class="mermaid-error"><strong>图表渲染失败</strong><pre>${escapeHtml(rawCode)}</pre></div>`
    }
  }
}

/** 为 mermaid 图表容器启用缩放与拖拽交互 */
function enableInteractivity(container: HTMLElement): void {
  const svg = container.querySelector('svg') as SVGSVGElement | null
  if (!svg) return

  // 清理旧的交互容器（如果存在）
  const oldCleanup = cleanupMap.get(container)
  if (oldCleanup) oldCleanup()

  svg.style.maxWidth = '100%'
  svg.style.height = 'auto'

  const abortController = new AbortController()
  const signal = abortController.signal

  // 检查是否已存在缩放容器（流式更新时复用）
  const existingWrapper = container.querySelector('.mermaid-zoom-wrapper') as HTMLElement
  let wrapper: HTMLElement
  let inner: HTMLElement
  let resetBtn: HTMLElement

  if (existingWrapper) {
    // 复用现有的缩放容器，保留缩放状态
    wrapper = existingWrapper
    inner = wrapper.querySelector('.mermaid-zoom-inner') as HTMLElement
    resetBtn = wrapper.querySelector('.mermaid-zoom-reset') as HTMLElement

    swapInnerSvg(inner, svg)
  } else {
    // 创建新的缩放/拖拽容器
    wrapper = document.createElement('div')
    wrapper.className = 'mermaid-zoom-wrapper'
    wrapper.style.cursor = 'grab'
    wrapper.style.touchAction = 'none'

    inner = document.createElement('div')
    inner.className = 'mermaid-zoom-inner'
    inner.style.transform = 'scale(1) translate(0px, 0px)'

    // 将 SVG 移入 inner 容器
    svg.parentNode!.insertBefore(wrapper, svg)
    inner.appendChild(svg)
    wrapper.appendChild(inner)

    // 添加重置按钮
    resetBtn = document.createElement('button')
    resetBtn.className = 'mermaid-zoom-reset'
    resetBtn.title = '重置缩放'
    resetBtn.innerHTML = `<svg ${lucideSvgAttrs} width="12" height="12">${rotateCcwIconInner}</svg>`
    resetBtn.style.display = 'none'
    wrapper.appendChild(resetBtn)
  }

  // 从现有的 transform 解析当前缩放状态（复用时保留状态）
  let scale = 1
  let translateX = 0
  let translateY = 0
  const MIN_SCALE = 0.5
  const MAX_SCALE = 5

  if (existingWrapper) {
    const transform = inner.style.transform
    const scaleMatch = transform.match(/scale\(([^)]+)\)/)
    const translateMatch = transform.match(/translate\(([^,]+)px,\s*([^)]+)px\)/)
    if (scaleMatch && translateMatch) {
      scale = parseFloat(scaleMatch[1])
      translateX = parseFloat(translateMatch[1])
      translateY = parseFloat(translateMatch[2])
    }
  }

  const applyTransform = () => {
    inner.style.transform = `scale(${scale}) translate(${translateX}px, ${translateY}px)`
    resetBtn.style.display = (scale !== 1 || translateX !== 0 || translateY !== 0) ? '' : 'none'
  }

  const resetTransform = () => {
    scale = 1
    translateX = 0
    translateY = 0
    applyTransform()
  }

  resetBtn.addEventListener('click', (e) => {
    e.stopPropagation()
    resetTransform()
  }, { signal })

  // === 桌面端：滚轮缩放 + 鼠标拖拽 ===
  wrapper.addEventListener('wheel', (e) => {
    e.preventDefault()
    e.stopPropagation()
    const rect = wrapper.getBoundingClientRect()
    const originX = e.clientX - rect.left
    const originY = e.clientY - rect.top

    const delta = e.deltaY > 0 ? 0.9 : 1.1
    const newScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale * delta))

    // 以鼠标位置为缩放中心
    translateX = originX / newScale - originX / scale + translateX
    translateY = originY / newScale - originY / scale + translateY
    scale = newScale
    applyTransform()
  }, { passive: false, signal })

  // 鼠标拖拽
  let isDragging = false
  let dragStartX = 0
  let dragStartY = 0
  let dragStartTranslateX = 0
  let dragStartTranslateY = 0

  wrapper.addEventListener('mousedown', (e) => {
    e.preventDefault()
    isDragging = true
    dragStartX = e.clientX
    dragStartY = e.clientY
    dragStartTranslateX = translateX
    dragStartTranslateY = translateY
    wrapper.style.cursor = 'grabbing'
  }, { signal })

  const handleMouseMove = (e: MouseEvent) => {
    if (!isDragging) return
    const dx = (e.clientX - dragStartX) / scale
    const dy = (e.clientY - dragStartY) / scale
    translateX = dragStartTranslateX + dx
    translateY = dragStartTranslateY + dy
    applyTransform()
  }

  const handleMouseUp = () => {
    if (!isDragging) return
    isDragging = false
    wrapper.style.cursor = 'grab'
  }

  document.addEventListener('mousemove', handleMouseMove, { signal })
  document.addEventListener('mouseup', handleMouseUp, { signal })

  // === 移动端：双指缩放 + 双指拖拽 ===
  let lastTouchDist = 0
  let lastTouchCenterX = 0
  let lastTouchCenterY = 0
  let isTouchZooming = false

  wrapper.addEventListener('touchstart', (e) => {
    if (e.touches.length === 2) {
      isTouchZooming = true
      const dx = e.touches[0].clientX - e.touches[1].clientX
      const dy = e.touches[0].clientY - e.touches[1].clientY
      lastTouchDist = Math.sqrt(dx * dx + dy * dy)
      lastTouchCenterX = (e.touches[0].clientX + e.touches[1].clientX) / 2
      lastTouchCenterY = (e.touches[0].clientY + e.touches[1].clientY) / 2
    }
  }, { passive: true, signal })

  wrapper.addEventListener('touchmove', (e) => {
    if (e.touches.length === 2 && isTouchZooming) {
      const dx = e.touches[0].clientX - e.touches[1].clientX
      const dy = e.touches[0].clientY - e.touches[1].clientY
      const dist = Math.sqrt(dx * dx + dy * dy)
      const centerX = (e.touches[0].clientX + e.touches[1].clientX) / 2
      const centerY = (e.touches[0].clientY + e.touches[1].clientY) / 2

      // 缩放
      const pinchRatio = dist / lastTouchDist
      const newScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale * pinchRatio))
      const rect = wrapper.getBoundingClientRect()
      const originX = lastTouchCenterX - rect.left
      const originY = lastTouchCenterY - rect.top
      translateX = originX / newScale - originX / scale + translateX
      translateY = originY / newScale - originY / scale + translateY
      scale = newScale

      // 双指平移
      const panDx = (centerX - lastTouchCenterX) / scale
      const panDy = (centerY - lastTouchCenterY) / scale
      translateX += panDx
      translateY += panDy

      lastTouchDist = dist
      lastTouchCenterX = centerX
      lastTouchCenterY = centerY
      applyTransform()
    }
  }, { passive: true, signal })

  wrapper.addEventListener('touchend', (e) => {
    if (e.touches.length < 2) {
      isTouchZooming = false
    }
  }, { signal })

  // 双击重置（桌面和移动端通用）
  wrapper.addEventListener('dblclick', (e) => {
    e.stopPropagation()
    resetTransform()
  }, { signal })

  // 存储清理函数，供下次调用或元素移除时使用
  const cleanup = () => abortController.abort()
  cleanupMap.set(container, cleanup)

  // 元素从 DOM 移除时自动清理
  const observer = new MutationObserver(() => {
    if (!wrapper.isConnected) {
      cleanup()
      observer.disconnect()
    }
  })
  if (wrapper.parentNode) {
    observer.observe(wrapper.parentNode, { childList: true })
  } else {
    observer.disconnect()
  }
}

function escapeHtml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
