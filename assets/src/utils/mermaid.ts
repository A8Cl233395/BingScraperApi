// mermaid 库封装（懒加载）：初始化配置与语法渲染，把 mermaid 源码渲染成 SVG 字符串。
// 图表块的构建、缓存、缩放交互等公共逻辑在 chart.ts（mermaid / svg 共用），
// 本文件只负责 mermaid 协议本身，由 chart.ts 在遇到 mermaid 图表块时懒加载

interface MermaidInstance {
  initialize: (config: Record<string, unknown>) => void
  render: (id: string, code: string) => Promise<{ svg: string }>
  parse: (code: string) => Promise<boolean>
}

let mermaidPromise: Promise<MermaidInstance> | null = null
let initialized = false
let renderCounter = 0

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

/** mermaid 源码 → SVG 字符串（解析/渲染失败时抛错，由调用方转为错误占位） */
export async function renderMermaidSvg(code: string): Promise<string> {
  const mermaid = await getMermaid()
  await initMermaid()

  const id = `mermaid-${++renderCounter}-${Date.now()}`
  await mermaid.parse(code)
  const { svg } = await mermaid.render(id, code)
  return svg
}
