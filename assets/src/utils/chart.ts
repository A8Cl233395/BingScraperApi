import DOMPurify from 'dompurify';
import hljs from 'highlight.js/lib/common';

// === 图表块（mermaid / svg）共用渲染管线 ===
// 两种图表代码块共用一套块结构（构建器在 markdown.ts 的 renderChartBlockHtml）与
// 渲染流程：解析器只输出占位符或缓存 SVG，DOM 写入后由 renderChartPlaceholders
// 统一完成渲染与源码高亮。图表块只显示不交互，缩放/拖拽在「查看」进入的全屏预览
// （ImagePreview）中操作。渲染结果按“类型 + 归一化源码”缓存，流式重写时由构建器
// 直接内联缓存 SVG，保证图表高度稳定。
// mermaid 语法渲染在 mermaid.ts（懒加载），svg 源码消毒后即最终图形。

export type ChartType = 'mermaid' | 'svg';

// 渲染结果缓存：key 为“类型 + 归一化源码”
const chartSvgCache = new Map<string, string>(); // 消毒后的 SVG（挂载与全屏数据源）

export function normalizeChartCode(code: string): string {
  return (code || '').replace(/\r\n/g, '\n').trim();
}

const cacheKey = (type: ChartType, code: string) => `${type}\u0000${normalizeChartCode(code)}`;

/** 已渲染的消毒后 SVG，供 marked 渲染器内联以稳定流式高度 */
export function getCachedChartSvg(type: ChartType, code: string): string | undefined {
  return chartSvgCache.get(cacheKey(type, code));
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

    const cached = chartSvgCache.get(cacheKey(type, code));
    if (cached) {
      chartEl.innerHTML = cached;
      continue;
    }

    try {
      const svgHtml = await renderChartSvg(type, code);
      chartSvgCache.set(cacheKey(type, code), svgHtml);
      chartEl.innerHTML = svgHtml;

      // 若用户主动向上阅读，锚定滚动位置
      if (scrollContainer && isUserScrolledUp) {
        const heightDiff = scrollContainer.scrollHeight - preScrollHeight;
        if (heightDiff > 0 && blockTopRelativeToContainer <= scrollContainer.clientHeight) {
          scrollContainer.scrollTop = preScrollTop + heightDiff;
        }
      }
    } catch {
      chartEl.innerHTML = chartErrorHtml(rawCode);
    }
  }
}
