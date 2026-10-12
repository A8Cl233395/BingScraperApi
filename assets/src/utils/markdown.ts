import { marked } from 'marked';
import DOMPurify from 'dompurify';
import katex from 'katex';
import 'katex/dist/katex.min.css';
import hljs from 'highlight.js/lib/common';
import { getCachedChartSvg, escapeHtml } from './chart';
import type { ChartType } from './chart';

// Lucide 图标的 SVG 属性与内部元素（用于 marked 渲染器生成的 HTML 字符串，
// 以及 MarkdownView 中复制反馈的图标交换；v-html 中无法使用 Vue 组件）
const lucideSvgAttrs = 'xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"';
const lightbulbIconInner = '<path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/>';
export const arrowLeftRightIconInner = '<path d="M8 3 4 7l4 4"/><path d="M4 7h16"/><path d="m16 21 4-4-4-4"/><path d="M20 17H4"/>';
export const codeIconInner = '<path d="m16 18 6-6-6-6"/><path d="m8 6-6 6 6 6"/>';
export const copyIconInner = '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>';
const eyeIconInner = '<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/>';
export const checkIconInner = '<path d="M20 6 9 17l-5-5"/>';

// 围栏是否闭合：流式输出中未闭合的代码块不渲染图表/预览按钮，避免预览到半截内容
function isFenceComplete(raw: string): boolean {
  const fenceMatch = raw.match(/^(?:```+|~~~+)/);
  return !!fenceMatch && raw.trimEnd().endsWith(fenceMatch[0]);
}

// 图表块（mermaid / svg）共用构建器：块结构与按钮完全一致，仅标签/源码语言不同，
// 渲染管线与缓存在 chart.ts 统一处理。图表块只显示不交互，缩放/拖拽在「查看」进入的
// 全屏预览（ImagePreview）中操作。已渲染过的图表直接内联缓存 SVG，
// 保证流式重写时图表高度稳定
function renderChartBlockHtml(type: ChartType, token: { text: string; raw: string }): string {
  const escapedCode = escapeHtml(token.text);
  const cachedSvg = getCachedChartSvg(type, token.text);
  const completeClass = isFenceComplete(token.raw) ? 'chart-complete' : 'chart-incomplete';
  const chartContent = cachedSvg || `<div class="chart-placeholder"><svg ${lucideSvgAttrs} width="14" height="14" class="chart-placeholder-icon">${lightbulbIconInner}</svg><span>图表生成中...</span></div>`;

  return `<div class="chart-block ${completeClass} my-4 border-[0.5px] border-border-main overflow-hidden bg-code-bg" data-chart="${type}">
  <div class="flex justify-between items-center bg-bg-panel px-3 py-1.5 border-b-[0.5px] border-border-main">
    <span class="text-[10px] font-medium text-text-placeholder uppercase tracking-wider">${type}</span>
    <div class="flex items-center gap-2">
      <button class="chart-toggle-btn text-text-placeholder hover:text-text-main transition-colors flex items-center gap-1" title="切换显示">
        <svg ${lucideSvgAttrs} width="10" height="10" class="toggle-icon-svg">${arrowLeftRightIconInner}</svg>
        <span class="toggle-text text-[10px]">文字</span>
      </button>
      <button class="copy-chart-btn text-text-placeholder hover:text-text-main transition-colors flex items-center gap-1" title="复制代码">
        <svg ${lucideSvgAttrs} width="10" height="10" class="copy-icon-svg">${copyIconInner}</svg>
        <span class="text-[10px]">复制</span>
      </button>
      <button class="chart-fullscreen-btn text-text-placeholder hover:text-text-main transition-colors flex items-center gap-1" title="查看全屏预览">
        <svg ${lucideSvgAttrs} width="10" height="10">${eyeIconInner}</svg>
        <span class="text-[10px]">查看</span>
      </button>
    </div>
  </div>
  <div class="chart-content">
    <div class="chart-figure">${chartContent}</div>
    <pre class="chart-source m-0! p-3! bg-code-bg! overflow-x-auto"><code class="hljs language-${type === 'svg' ? 'xml' : 'mermaid'}">${escapedCode}</code></pre>
  </div>
</div>`;
}

marked.use({
  breaks: true,
  gfm: true,
  hooks: {
    postprocess(html) {
      // Wrap tables with a scrollable div for mobile compatibility
      return html.replace(/<table/g, '<div class="table-wrapper"><table')
                 .replace(/<\/table>/g, '</table></div>');
    }
  },
  renderer: {
    code(token) {
      const lang = token.lang || 'text';
      const baseLang = lang.split(/\s+/)[0].toLowerCase();

      // 图表块（mermaid / svg）统一走图表渲染方式（图 + 源码切换、查看全屏预览）
      if (baseLang === 'mermaid' || baseLang === 'svg') {
        return renderChartBlockHtml(baseLang, token);
      }

      let highlightedCode;
      try {
        if (lang && hljs.getLanguage(lang)) {
          highlightedCode = hljs.highlight(token.text, { language: lang }).value;
        } else {
          highlightedCode = hljs.highlightAuto(token.text).value;
        }
      } catch (e) {
        highlightedCode = token.text;
      }

      // html 代码块支持“查看”沙箱预览：与图表块一致仅在围栏闭合后出现，
      // 流式输出中不完整的块不渲染按钮，避免预览到半截 HTML
      const viewBtn = baseLang === 'html' && isFenceComplete(token.raw) ? `
      <button class="view-code-btn text-text-placeholder hover:text-text-main transition-colors flex items-center gap-1" title="查看渲染结果">
        <svg ${lucideSvgAttrs} width="10" height="10">${eyeIconInner}</svg>
        <span class="text-[10px]">查看</span>
      </button>` : '';

      return `
<div class="code-block-wrapper my-4 border-[0.5px] border-border-main overflow-hidden bg-code-bg" style="touch-action: pan-x pan-y;">
  <div class="flex justify-between items-center bg-bg-panel px-3 py-1.5 border-b-[0.5px] border-border-main">
    <span class="text-[10px] font-medium text-text-placeholder uppercase tracking-wider">${lang}</span>
    <div class="flex items-center gap-2">${viewBtn}
    <button class="copy-code-btn text-text-placeholder hover:text-text-main transition-colors flex items-center gap-1" title="复制代码">
      <svg ${lucideSvgAttrs} width="10" height="10" class="copy-icon-svg">${copyIconInner}</svg>
      <span class="text-[10px]">复制</span>
    </button>
    </div>
  </div>
  <pre class="m-0! p-3! bg-code-bg! overflow-x-auto" style="touch-action: pan-x pan-y;"><code class="hljs language-${lang}">${highlightedCode}</code></pre>
</div>`;
    }
  }
});

// Add a custom extension to protect LaTeX from being mangled by marked
marked.use({
  extensions: [
    {
      name: 'strong',
      level: 'inline',
      start(src) { return src.indexOf('**'); },
      tokenizer(src) {
        const match = src.match(/^\*\*([^\s\*](?:[\s\S]*?[^\s\*])??)\*\*(?!\*)/);
        if (match) {
          return {
            type: 'strong',
            raw: match[0],
            text: match[1],
            tokens: this.lexer.inlineTokens(match[1])
          };
        }
      }
    },
    {
      name: 'em',
      level: 'inline',
      start(src) { return src.indexOf('*'); },
      tokenizer(src) {
        const match = src.match(/^\*([^\s\*](?:[\s\S]*?[^\s\*])??)\*(?!\*)/);
        if (match) {
          return {
            type: 'em',
            raw: match[0],
            text: match[1],
            tokens: this.lexer.inlineTokens(match[1])
          };
        }
      }
    },
    {
      name: 'inlineMath',
      level: 'inline',
      start(src) { return src.indexOf('$'); },
      tokenizer(src) {
        const match = src.match(/^\$((?:[^\$]|\\\$)+)\$/);
        if (match) return { type: 'inlineMath', raw: match[0], text: match[1] };
      },
      renderer(token) {
        try {
          return katex.renderToString(token.text, { displayMode: false, throwOnError: false });
        } catch (e) { return token.raw; }
      }
    },
    {
      name: 'blockMath',
      level: 'block',
      start(src) { return src.indexOf('$$'); },
      tokenizer(src) {
        const match = src.match(/^\$\$([\s\S]*?)\$\$/);
        if (match) return { type: 'blockMath', raw: match[0], text: match[1] };
      },
      renderer(token) {
        try {
          return `<div class="math-block">${katex.renderToString(token.text, { displayMode: true, throwOnError: false })}</div>`;
        } catch (e) { return token.raw; }
      }
    },
    {
      name: 'latexInline',
      level: 'inline',
      start(src) { return src.indexOf('\\('); },
      tokenizer(src) {
        const match = src.match(/^\\\(([\s\S]*?)\\\)/);
        if (match) return { type: 'latexInline', raw: match[0], text: match[1] };
        },
      renderer(token) {
        try {
          return katex.renderToString(token.text, { displayMode: false, throwOnError: false });
        } catch (e) { return token.raw; }
      }
    },
    {
      name: 'latexBlock',
      level: 'block',
      start(src) { return src.indexOf('\\['); },
      tokenizer(src) {
        const match = src.match(/^\\\[([\s\S]*?)\\\)/);
        if (match) return { type: 'latexBlock', raw: match[0], text: match[1] };
      },
      renderer(token) {
        try {
          return `<div class="math-block">${katex.renderToString(token.text, { displayMode: true, throwOnError: false })}</div>`;
        } catch (e) { return token.raw; }
      }
    }
  ]
});

// === 流式输出拖尾 ===
// 时间驱动的淡入：按单元的出现时刻计算年龄，转成负 animation-delay 写入 span，
// 重建出的新元素从上次渲染中断的进度无缝续播；淡入在浏览器时间里自行完成，与
// chunk 到达节奏无关——停顿期间字符会正常落定为不透明，不会停在半透明状态。
// 同一批次（出现时刻相同）的单元合并为一个 span。调用方需保存返回的 tailState
// 并在下次渲染时传回；正文结构变化（非纯追加）时状态自动作废重来。
export interface StreamTailState {
  text: string;   // 上次渲染的最后一个文本节点
  born: number[]; // 各单元的出现时刻（performance.now() 毫秒），与 text 尾部对齐
}

const STREAM_TAIL_FADE = 500; // 单元淡入时长（ms），与 style-chat.css 的动画时长保持一致
const STREAM_TAIL_WRAP = 24;  // 单次渲染最多包裹的尾部单元数
const STREAM_TAIL_KEEP = 64;  // 状态中保留出现时刻的尾部单元数

function wrapStreamTail(html: string, prev: StreamTailState | undefined, now: number): { html: string; state?: StreamTailState } {
  // 跳过结尾连续闭合标签，定位最后一个文本节点（起于最后一个 '>' 之后）
  const closeMatch = /(?:<\/[a-zA-Z][^>]*>\s*)+$/.exec(html);
  const end = closeMatch ? closeMatch.index : html.length;
  const textStart = html.lastIndexOf('>', end) + 1;
  const text = html.slice(textStart, end);
  if (!text.trim() || text.includes('<')) return { html };

  const unitRe = /&(?:#[0-9]+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);|[\s\S]/gu;
  const matches: RegExpExecArray[] = [];
  for (let m = unitRe.exec(text); m; m = unitRe.exec(text)) matches.push(m);
  if (matches.length < 3) return { html };

  // 出现时刻：正文为纯追加时按位置沿用上次记录（滑出保留窗口的旧单元视为早已
  // 落定），结构变化则全部视为新出现
  let born: number[];
  if (prev && text.startsWith(prev.text)) {
    const base = prev.text.length - prev.born.length;
    born = matches.map((_, i) => (i >= base ? (i - base < prev.born.length ? prev.born[i - base] : now) : now - STREAM_TAIL_FADE * 2));
  } else {
    born = matches.map(() => now);
  }

  // 逐单元重组文本节点：淡入窗口内的按批次包 span（负 delay 从当前进度续播）
  const wrapFrom = matches.length - STREAM_TAIL_WRAP;
  let out = '';
  let plainFrom = 0;
  let i = 0;
  while (i < matches.length) {
    if (i < wrapFrom || now - born[i] >= STREAM_TAIL_FADE) { i++; continue; }
    if (i > plainFrom) out += text.slice(matches[plainFrom].index, matches[i].index);
    const bornAt = born[i];
    let j = i + 1;
    while (j < matches.length && born[j] === bornAt) j++;
    const delay = ((now - bornAt) / 1000).toFixed(2);
    out += `<span class="stream-tail-unit" style="animation-delay:-${delay}s">${text.slice(matches[i].index, j < matches.length ? matches[j].index : undefined)}</span>`;
    i = j;
    plainFrom = i;
  }
  if (plainFrom < matches.length) out += text.slice(matches[plainFrom].index);

  return {
    html: html.slice(0, textStart) + out + html.slice(end),
    state: { text, born: born.slice(-STREAM_TAIL_KEEP) },
  };
}

// === 消息渲染的样式隔离（Shadow DOM） ===
// 模型可能按系统提示在正文内联完整 HTML 页面，其中 <style> 里的 *、body、h1 等
// 全局选择器与 @keyframes 若直接进入文档会破坏应用排版（已出现真实故障：body 背景
// 被改写、全局边距清零）。隔离由 Shadow DOM 原生承担：消息 HTML 连同 <style> 原文
// 注入自己的影子根（createMessageShadowRoot），样式与 @keyframes 都按树隔离、绝不
// 泄漏到文档；CSS 变量（主题/暗色）从文档继承进来，无需处理。应用自身样式经共享
// 构造样式表注入影子根并包进 @layer shared——层叠层内的规则被无层规则无条件压过，
// 消息内联样式对自身内容有最终决定权。
// 唯一改写：页面级选择器 body/html/:root 映射为 :host（影子树没有 body/html 元素，
// 不映射则页面级背景/字体/变量失去作用目标）；@import/@charset 丢弃（会拉取外部资源）。

/** 跳过 CSS 字符串字面量（处理转义），返回结束引号之后的下标 */
function skipCssString(css: string, i: number): number {
  const quote = css[i];
  i++;
  while (i < css.length) {
    if (css[i] === '\\') i += 2;
    else if (css[i] === quote) return i + 1;
    else i++;
  }
  return i;
}

/** 顶层逗号切分选择器列表（忽略括号、方括号与字符串内的逗号） */
function splitSelectorList(sel: string): string[] {
  const parts: string[] = [];
  let cur = '';
  let depth = 0;
  let i = 0;
  while (i < sel.length) {
    const ch = sel[i];
    if (ch === '"' || ch === "'") {
      const end = skipCssString(sel, i);
      cur += sel.slice(i, end);
      i = end;
      continue;
    }
    if (ch === ',' && depth === 0) {
      parts.push(cur);
      cur = '';
      i++;
      continue;
    }
    if (ch === '(' || ch === '[') depth++;
    else if (ch === ')' || ch === ']') depth = Math.max(0, depth - 1);
    cur += ch;
    i++;
  }
  parts.push(cur);
  return parts;
}

/** 选择器列表里的页面级入口映射为 :host：body/html/:root（含后接后代/子级选择器的
 *  形式，如 body .page）在影子树中没有对应元素，映射后页面级样式作用于消息宿主 */
function mapRootSelectorList(sel: string): string {
  return splitSelectorList(sel)
    .map(part => part.trim().replace(/^(?:body|html|:root)(?=$|[\s>+~])/i, ':host'))
    .join(', ');
}

/** 将一段 CSS 的页面级选择器映射为 :host：普通规则只改选择器前导，条件组 at-rule
 *  递归，@keyframes 等块体与其余内容原样保留 */
function mapPageLevelRules(css: string): string {
  let out = '';
  let i = 0;
  const n = css.length;
  while (i < n) {
    const ch = css[i];
    if (ch === '}' || /\s/.test(ch)) {
      out += ch;
      i++;
      continue;
    }
    // 读取前导（选择器或 at-rule 名）：直到顶层 { 、 ; 或 }
    let j = i;
    let paren = 0;
    while (j < n) {
      const c = css[j];
      if (c === '"' || c === "'") {
        j = skipCssString(css, j);
        continue;
      }
      if (c === '(') paren++;
      else if (c === ')') paren = Math.max(0, paren - 1);
      else if (paren === 0 && (c === '{' || c === ';' || c === '}')) break;
      j++;
    }
    const prelude = css.slice(i, j).trim();
    const term = css[j];

    if (term === ';') {
      // 语句级 at-rule：@import/@charset 丢弃，其余原样保留
      if (!/^@(import|charset)\b/i.test(prelude)) out += prelude + ';';
      i = j + 1;
      continue;
    }
    if (term === undefined) {
      out += prelude;
      break;
    }
    if (term === '}') {
      out += prelude;
      i = j;
      continue;
    }

    // 匹配块体（支持嵌套大括号；流式输出中块体可能未闭合）
    let k = j + 1;
    let depth = 1;
    let bodyParen = 0;
    while (k < n) {
      const c = css[k];
      if (c === '"' || c === "'") {
        k = skipCssString(css, k);
        continue;
      }
      if (c === '(') bodyParen++;
      else if (c === ')') bodyParen = Math.max(0, bodyParen - 1);
      else if (bodyParen === 0) {
        if (c === '{') depth++;
        else if (c === '}' && --depth === 0) break;
      }
      k++;
    }
    const body = css.slice(j + 1, k);
    const closed = depth === 0;
    i = closed ? k + 1 : n;

    if (prelude.startsWith('@')) {
      const atName = (prelude.match(/^@[\w-]+/) || [''])[0].slice(1).toLowerCase();
      if (atName === 'media' || atName === 'supports' || atName === 'container' || atName === 'layer' || atName === 'scope') {
        out += `${prelude}{${mapPageLevelRules(body)}${closed ? '}' : ''}`;
      } else {
        // @keyframes/@font-face 等块体不含选择器，原样保留
        out += `${prelude}{${body}${closed ? '}' : ''}`;
      }
    } else {
      out += `${mapRootSelectorList(prelude)}{${body}${closed ? '}' : ''}`;
    }
  }
  return out;
}

const CSS_COMMENT_RE = /\/\*[\s\S]*?\*\//g;

/** 消毒后的 HTML：把内联 <style> 里的页面级选择器映射为 :host（隔离本身由 Shadow DOM 承担） */
function mapInlineStyles(html: string): string {
  return html.replace(/(<style\b[^>]*>)([\s\S]*?)(<\/style\s*>)/gi, (_whole: string, open: string, css: string) =>
    open + mapPageLevelRules(css.replace(CSS_COMMENT_RE, ' ')) + '</style>');
}

// === 影子根与共享样式表 ===
// 应用全部样式（Tailwind/prose/hljs/KaTeX）收集成一张共享构造样式表，注入每条消息的
// 影子根——所有消息共用一份，内存与消息数无关。包进 @layer shared：层叠层内的规则
// 会被无层规则无条件压过，保证消息内联 <style> 对自身内容有最终决定权；应用样式之间
// 的相对层叠关系在同层内保持不变。@import 必须位于样式表顶层，收集时拆出放在层外；
// 跨域样式表读不到 cssRules 时跳过。@font-face 以文档内定义生效（不受影子树限制），
// KaTeX 字体不受影响。样式表数量变化时重建（懒加载 chunk 注入新样式时）；dev 下 HMR
// 原地替换 <style> 内容不会触发重建，仅影响开发体验。
let sharedSheet: CSSStyleSheet | null = null;
let sharedSheetSources = -1;

function getShadowStyleSheets(): CSSStyleSheet[] {
  const sources = document.styleSheets.length;
  if (!sharedSheet || sharedSheetSources !== sources) {
    const texts: string[] = [];
    for (const sheet of Array.from(document.styleSheets)) {
      try {
        texts.push(Array.from(sheet.cssRules).map(rule => rule.cssText).join('\n'));
      } catch {
        // 跨域样式表读不了 cssRules，跳过（本项目样式全部同源）
      }
    }
    const joined = texts.join('\n');
    const imports = joined.match(/^\s*@import[^;]+;/gm)?.join('\n') ?? '';
    const body = joined.replace(/^\s*@import[^;]+;/gm, '');
    sharedSheet = new CSSStyleSheet();
    sharedSheet.replaceSync(`${imports}\n@layer shared { ${body} }`);
    sharedSheetSources = sources;
  }
  return [sharedSheet];
}

/** 在宿主上创建消息影子根，返回内容容器。prose 类必须放在影子树内层：.prose h1 这类
 *  选择器无法跨影子边界匹配宿主元素 */
export function createMessageShadowRoot(host: HTMLElement): HTMLElement {
  const shadow = host.attachShadow({ mode: 'open' });
  shadow.adoptedStyleSheets = getShadowStyleSheets();
  const content = document.createElement('div');
  content.className = 'prose prose-sm max-w-none text-text-main wrap-anywhere';
  shadow.appendChild(content);
  return content;
}

// 与图表块消毒（chart.ts 的 CHART_SANITIZE_OPTS）同配置：svgFilters 保证图表块内联
// 缓存的滤镜图形在流式重写消毒时不被剥掉
const SANITIZE_OPTS = { USE_PROFILES: { html: true, svg: true, svgFilters: true }, ADD_TAGS: ['foreignObject'], ADD_ATTR: ['transform', 'style', 'class'] };

/** Markdown → 已消毒的 HTML；解析异常时退回消毒后的原始文本。
 *  输出必须写入 createMessageShadowRoot 返回的影子树容器（MarkdownView 已处理），
 *  隔离依赖影子根，写进普通 DOM 会让内联 <style> 泄漏到文档。
 *  streamTail 时必须传入 now（performance.now() 毫秒），返回值带出下次渲染所需的尾部状态 */
export function renderMarkdown(content: string, opts?: { streamTail?: boolean; tailState?: StreamTailState; now?: number }): { html: string; tailState?: StreamTailState } {
  try {
    const raw = marked.parse(content) as string;
    if (opts?.streamTail) {
      const wrapped = wrapStreamTail(raw, opts.tailState, opts.now ?? 0);
      return { html: mapInlineStyles(DOMPurify.sanitize(wrapped.html, SANITIZE_OPTS)), tailState: wrapped.state };
    }
    return { html: mapInlineStyles(DOMPurify.sanitize(raw, SANITIZE_OPTS)) };
  } catch {
    return { html: mapInlineStyles(DOMPurify.sanitize(content)) };
  }
}
