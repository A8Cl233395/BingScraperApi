import DOMPurify from 'dompurify';
import hljs from 'highlight.js/lib/common';

// === 图表块（mermaid / svg）共用渲染管线 ===
// 两种图表代码块共用一套块结构（构建器在 markdown.ts 的 renderChartBlockHtml）与
// 渲染流程：解析器只输出占位符或缓存内容，DOM 写入后由 renderChartPlaceholders
// 统一完成渲染与源码高亮。图表块只显示不交互，缩放/拖拽在「查看」进入的全屏预览
// （ImagePreview）中操作。渲染结果（成功 SVG 与失败占位）按“类型 + 归一化源码”缓存，
// 流式重写时由构建器直接内联，保证图表高度稳定。
// mermaid 语法渲染在 mermaid.ts（懒加载），svg 源码消毒后即最终图形。

export type ChartType = 'mermaid' | 'svg';

// 渲染结果缓存：key 为“类型 + 归一化源码”
const chartSvgCache = new Map<string, string>(); // 消毒后的 SVG（挂载与全屏数据源）
// 失败缓存：同一份源码的失败是确定的。失败占位必须和成功 SVG 一样由解析器内联——
// 否则流式每重写一次 DOM，图表块都会从「图表生成中...」重新渲染、失败后换成更高的
// 错误块，块高度反复变化把视口推来推去（表现为一直滚回底部/位置来回跳）。
const chartErrorCache = new Map<string, string>(); // 失败占位 HTML（含原始源码）
// 同一份源码只跑一次渲染：上一帧的渲染可能还没结束，新帧已经重写 DOM 并再次触发，
// 失败结果尚未落入缓存时会并发重试很多次
const chartRenderTasks = new Map<string, Promise<string>>();

export function normalizeChartCode(code: string): string {
  return (code || '').replace(/\r\n/g, '\n').trim();
}

const cacheKey = (type: ChartType, code: string) => `${type}\u0000${normalizeChartCode(code)}`;

/** 已渲染的图表内容（成功 SVG 或失败占位），供 marked 渲染器内联以稳定流式高度 */
export function getCachedChartContent(type: ChartType, code: string): string | undefined {
  const key = cacheKey(type, code);
  return chartSvgCache.get(key) ?? chartErrorCache.get(key);
}

/** 该图表是否已渲染失败：失败块没有可用的 SVG，全屏预览按钮应禁用 */
export function isChartFailed(type: ChartType, code: string): boolean {
  return chartErrorCache.has(cacheKey(type, code));
}

/** 图表 SVG 的 data URL（全屏预览）；未渲染完成返回 null。
 *  必须转成 XML 方言输出：缓存里的 SVG 是 DOMPurify 的 HTML 序列化（<br> 等 void 元素
 *  不自闭合），data:image/svg+xml 按 XML 解析会整体失败、预览直接空白（mermaid 多行
 *  标签的 <br> 就中招）；顺带给根节点补数值宽高——mermaid 输出 width="100%"，
 *  img 没有固有尺寸无法按比例适配屏幕 */
export function getChartSvgDataUrl(type: ChartType, code: string): string | null {
  const svg = chartSvgCache.get(cacheKey(type, code));
  if (!svg) return null;
  return `data:image/svg+xml,${encodeURIComponent(toXmlSvg(svg))}`;
}

/** HTML 序列化的 SVG 字符串 → XML 方言（void 元素自闭合、补 xmlns），并给根节点补数值宽高 */
function toXmlSvg(svgHtml: string): string {
  const doc = new DOMParser().parseFromString(svgHtml, 'text/html');
  const el = doc.querySelector('svg');
  if (!el) return svgHtml;
  const viewBox = (el.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number);
  if (viewBox.length === 4 && viewBox.every(n => Number.isFinite(n))) {
    const width = el.getAttribute('width');
    const height = el.getAttribute('height');
    if (!width || width.endsWith('%')) el.setAttribute('width', String(viewBox[2]));
    if (!height || height.endsWith('%')) el.setAttribute('height', String(viewBox[3]));
  }
  return new XMLSerializer().serializeToString(el);
}

/** 图表块元素对应的图表类型（data-chart 缺省视为 mermaid） */
export function chartTypeOf(el: Element): ChartType {
  return (el as HTMLElement).dataset.chart === 'svg' ? 'svg' : 'mermaid';
}

export function escapeHtml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// 与消息级消毒（markdown.ts 的 SANITIZE_OPTS）同配置：svgFilters 保证滤镜图形不被剥掉；
// HTML_INTEGRATION_POINTS 必须把 foreignobject 算作 HTML 集成点——mermaid 的 htmlLabels
// 标签（div/span）位于 SVG 命名空间的 foreignObject 下，DOMPurify 默认只认 annotation-xml，
// 会走 _checkValidNamespace 失败 → _forceRemove 把标签连同文字整体删掉（“图表文字消失”坑）
const CHART_SANITIZE_OPTS = {
  USE_PROFILES: { html: true, svg: true, svgFilters: true },
  ADD_TAGS: ['foreignObject'],
  ADD_ATTR: ['transform', 'style', 'class'],
  HTML_INTEGRATION_POINTS: { foreignobject: true, 'annotation-xml': true },
};

/** 图表源码 → 消毒后的 SVG；不含 <svg> 视为渲染失败 */
function sanitizeChartSvg(raw: string): string {
  const sanitized = DOMPurify.sanitize(raw, CHART_SANITIZE_OPTS);
  if (!/<svg[\s>]/i.test(sanitized)) throw new Error('图表源码中没有可渲染的 <svg> 元素');
  return sanitized;
}

/** 按类型渲染出消毒后的 SVG：svg 直接消毒源码，mermaid 懒加载 mermaid.ts 解析 */
async function renderChartSvg(type: ChartType, code: string): Promise<string> {
  const raw = type === 'svg' ? code : await (await import('./mermaid')).renderMermaidSvg(code);
  return sanitizeChartSvg(raw);
}

/** 同一图表复用同一个在途渲染任务；成功后直接写入 SVG 缓存，失败由调用方写失败缓存 */
function renderChartOnce(type: ChartType, code: string, key: string): Promise<string> {
  let task = chartRenderTasks.get(key);
  if (!task) {
    task = renderChartSvg(type, code)
      .then(svg => {
        chartSvgCache.set(key, svg);
        return svg;
      })
      .finally(() => chartRenderTasks.delete(key));
    chartRenderTasks.set(key, task);
  }
  return task;
}

/** 源码高亮：优先图表语言，不支持时自动检测，兜底纯文本 */
function highlightChartSource(code: string, lang: string): string {
  try {
    return hljs.highlight(code, { language: lang }).value;
  } catch {
    try {
      return hljs.highlightAuto(code).value;
    } catch {
      return escapeHtml(code);
    }
  }
}

/** 图表渲染失败的占位 */
function chartErrorHtml(rawCode: string): string {
  return `<div class="chart-error"><strong>图表渲染失败</strong><pre>${escapeHtml(rawCode)}</pre></div>`;
}

/** 失败图表没有可用的 SVG data URL：禁用「查看」按钮，避免点击无反应 */
function disableChartPreview(block: Element): void {
  const btn = block.querySelector<HTMLButtonElement>('.chart-fullscreen-btn');
  if (!btn || btn.disabled) return;
  btn.disabled = true;
  btn.title = '图表渲染失败，无法预览';
}

/**
 * 渲染消息内的图表块（mermaid / svg 共用）：源码高亮、图表渲染与缓存。
 * 图表块只显示不交互，流式重写后 DOM 是全新子树，缓存命中也要重新写入图表
 */
export async function renderChartPlaceholders(root: Element | Document = document): Promise<void> {
  const blocks = root.querySelectorAll('.chart-block.chart-complete:not(.rendered)');
  if (blocks.length === 0) return;

  const scrollContainer = document.getElementById('message-container');

  for (const block of Array.from(blocks)) {
    const type = chartTypeOf(block);
    const chartEl = block.querySelector('.chart-figure') as HTMLElement;
    const sourceEl = block.querySelector('.chart-source') as HTMLElement;
    if (!chartEl || !sourceEl) continue;

    const rawCode = sourceEl.querySelector('code')?.textContent || '';
    if (!rawCode) continue;
    const code = normalizeChartCode(rawCode);

    block.classList.add('rendered');

    // 对源码进行 hljs 高亮
    const codeEl = sourceEl.querySelector('code');
    if (codeEl) codeEl.innerHTML = highlightChartSource(rawCode, type === 'svg' ? 'xml' : 'mermaid');

    // 记录 DOM 更改前视口及 scrollContainer 状态，避免注入大图引发视觉跳动
    let preScrollTop = 0;
    let preScrollHeight = 0;
    let isUserScrolledUp = false;
    let blockTopRelativeToContainer = 0;
    if (scrollContainer) {
      preScrollTop = scrollContainer.scrollTop;
      preScrollHeight = scrollContainer.scrollHeight;
      const isAtBottom = Math.abs(preScrollHeight - preScrollTop - scrollContainer.clientHeight) <= 20;
      isUserScrolledUp = !isAtBottom;
      const cRect = scrollContainer.getBoundingClientRect();
      const bRect = block.getBoundingClientRect();
      blockTopRelativeToContainer = bRect.top - cRect.top;
    }

    const key = cacheKey(type, code);
    const cached = getCachedChartContent(type, code);
    if (cached) {
      chartEl.innerHTML = cached;
      if (!chartSvgCache.has(key)) disableChartPreview(block);
      continue;
    }

    try {
      const svgHtml = await renderChartOnce(type, code, key);
      // 等待期间流式重写可能已替换整棵子树：旧块只把结果留在缓存里，不再写 DOM
      if (block.isConnected) chartEl.innerHTML = svgHtml;
    } catch {
      // 失败结果同样缓存：流式重写后构建器直接内联错误块，不再反复「占位符 → 失败」抖动
      const errorHtml = chartErrorHtml(rawCode);
      chartErrorCache.set(key, errorHtml);
      if (block.isConnected) {
        chartEl.innerHTML = errorHtml;
        disableChartPreview(block);
      }
    }

    // 旧子树已脱离文档：上面的滚动快照对应的是被替换的布局，继续补偿只会让视口乱跳
    if (!block.isConnected) continue;

    // 若用户主动向上阅读，锚定滚动位置（成功与失败都会改变块高度）
    if (scrollContainer && isUserScrolledUp) {
      const heightDiff = scrollContainer.scrollHeight - preScrollHeight;
      if (heightDiff > 0 && blockTopRelativeToContainer <= scrollContainer.clientHeight) {
        scrollContainer.scrollTop = preScrollTop + heightDiff;
      }
    }
  }
}
