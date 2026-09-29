import { marked } from 'marked';
import DOMPurify from 'dompurify';
import katex from 'katex';
import 'katex/dist/katex.min.css';
import hljs from 'highlight.js/lib/common';

// Lucide 图标的 SVG 属性与内部元素（用于 marked 渲染器生成的 HTML 字符串，
// 以及 MarkdownView 中复制反馈的图标交换；v-html 中无法使用 Vue 组件）
const lucideSvgAttrs = 'xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"';
const lightbulbIconInner = '<path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/>';
export const arrowLeftRightIconInner = '<path d="M8 3 4 7l4 4"/><path d="M4 7h16"/><path d="m16 21 4-4-4-4"/><path d="M20 17H4"/>';
export const codeIconInner = '<path d="m16 18 6-6-6-6"/><path d="m8 6-6 6 6 6"/>';
export const copyIconInner = '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>';
const maximizeIconInner = '<path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/>';
export const checkIconInner = '<path d="M20 6 9 17l-5-5"/>';

// mermaid 模块懒加载：marked 渲染器内联缓存图表与组件渲染占位符共用同一实例
let mermaidModule: any = null;
let mermaidModulePromise: Promise<any> | null = null;

/** 同步获取已加载的 mermaid 模块（未加载时返回 null） */
export function getMermaidModule(): any {
  return mermaidModule;
}

/** 懒加载 mermaid 模块（多次调用复用同一个 Promise） */
export function loadMermaid(): Promise<any> {
  if (!mermaidModulePromise) {
    mermaidModulePromise = import('./mermaid').then(m => {
      mermaidModule = m;
      return m;
    });
  }
  return mermaidModulePromise;
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

      if (lang === 'mermaid') {
        const fenceMatch = token.raw.match(/^(?:```+|~~~+)/);
        const isComplete = fenceMatch && token.raw.trimEnd().endsWith(fenceMatch[0]);

        const escapedCode = token.text
          .replace(/&/g, '&amp;')
          .replace(/"/g, '&quot;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;');
        // 已渲染过的图表直接内联缓存 HTML，保证流式重写时图表高度稳定
        const cachedChartHtml = mermaidModule ? (mermaidModule.getCachedMermaidChartHtml(token.text) || mermaidModule.getCachedMermaidSvg(token.text)) : undefined;
        const completeClass = isComplete ? 'mermaid-complete' : 'mermaid-incomplete';
        const chartContent = cachedChartHtml || `<div class="mermaid-placeholder"><svg ${lucideSvgAttrs} width="14" height="14" class="mermaid-placeholder-icon">${lightbulbIconInner}</svg><span>图表生成中...</span></div>`;

        return `<div class="mermaid-block ${completeClass} my-4 border-[0.5px] border-border-main overflow-hidden bg-code-bg">
  <div class="flex justify-between items-center bg-bg-panel px-3 py-1.5 border-b-[0.5px] border-border-main">
    <span class="text-[10px] font-medium text-text-placeholder uppercase tracking-wider">mermaid</span>
    <div class="flex items-center gap-2">
      <button class="mermaid-toggle-btn text-text-placeholder hover:text-text-main transition-colors flex items-center gap-1" title="切换显示">
        <svg ${lucideSvgAttrs} width="10" height="10" class="toggle-icon-svg">${arrowLeftRightIconInner}</svg>
        <span class="toggle-text text-[10px]">文字</span>
      </button>
      <button class="copy-mermaid-btn text-text-placeholder hover:text-text-main transition-colors flex items-center gap-1" title="复制代码">
        <svg ${lucideSvgAttrs} width="10" height="10" class="copy-icon-svg">${copyIconInner}</svg>
        <span class="text-[10px]">复制</span>
      </button>
      <button class="mermaid-fullscreen-btn text-text-placeholder hover:text-text-main transition-colors flex items-center gap-1" title="全屏查看">
        <svg ${lucideSvgAttrs} width="10" height="10">${maximizeIconInner}</svg>
        <span class="text-[10px]">全屏</span>
      </button>
    </div>
  </div>
  <div class="mermaid-content">
    <div class="mermaid-chart">${chartContent}</div>
    <pre class="mermaid-source !m-0 !p-3 !bg-code-bg overflow-x-auto"><code class="hljs language-mermaid">${escapedCode}</code></pre>
  </div>
</div>`;
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

      return `
<div class="code-block-wrapper my-4 border-[0.5px] border-border-main overflow-hidden bg-code-bg" style="touch-action: pan-x pan-y;">
  <div class="flex justify-between items-center bg-bg-panel px-3 py-1.5 border-b-[0.5px] border-border-main">
    <span class="text-[10px] font-medium text-text-placeholder uppercase tracking-wider">${lang}</span>
    <button class="copy-code-btn text-text-placeholder hover:text-text-main transition-colors flex items-center gap-1" title="复制代码">
      <svg ${lucideSvgAttrs} width="10" height="10" class="copy-icon-svg">${copyIconInner}</svg>
      <span class="text-[10px]">复制</span>
    </button>
  </div>
  <pre class="!m-0 !p-3 !bg-code-bg overflow-x-auto" style="touch-action: pan-x pan-y;"><code class="hljs language-${lang}">${highlightedCode}</code></pre>
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

const SANITIZE_OPTS = { USE_PROFILES: { html: true, svg: true }, ADD_TAGS: ['foreignObject'], ADD_ATTR: ['transform', 'style', 'class'] };

/** Markdown → 已消毒的 HTML；解析异常时退回消毒后的原始文本。
 *  streamTail 时必须传入 now（performance.now() 毫秒），返回值带出下次渲染所需的尾部状态 */
export function renderMarkdown(content: string, opts?: { streamTail?: boolean; tailState?: StreamTailState; now?: number }): { html: string; tailState?: StreamTailState } {
  try {
    const raw = marked.parse(content) as string;
    if (opts?.streamTail) {
      const wrapped = wrapStreamTail(raw, opts.tailState, opts.now ?? 0);
      return { html: DOMPurify.sanitize(wrapped.html, SANITIZE_OPTS), tailState: wrapped.state };
    }
    return { html: DOMPurify.sanitize(raw, SANITIZE_OPTS) };
  } catch {
    return { html: DOMPurify.sanitize(content) };
  }
}
