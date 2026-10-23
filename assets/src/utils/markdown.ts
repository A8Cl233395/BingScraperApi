import { marked } from 'marked';
import DOMPurify from 'dompurify';
import katex from 'katex';
import 'katex/dist/katex.min.css';
import hljs from 'highlight.js/lib/common';
import { getCachedChartContent, isChartFailed, escapeHtml } from './chart';
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
// 全屏预览（ImagePreview）中操作。已渲染过的图表直接内联缓存内容（成功 SVG 或失败占位），
// 保证流式重写时图表高度稳定（否则会从已渲染图/错误块退回占位符，DOM 高度反复变化导致
// 浏览器调整 scrollTop，表现为莫名滚回底部或视口来回跳；损坏的 mermaid 每帧重试渲染
// 就是这个抖动的最明显来源）。
function renderChartBlockHtml(type: ChartType, token: { text: string; raw: string }): string {
  const escapedCode = escapeHtml(token.text);
  const cachedChart = getCachedChartContent(type, token.text);
  const completeClass = isFenceComplete(token.raw) ? 'chart-complete' : 'chart-incomplete';
  const chartContent = cachedChart || `<div class="chart-placeholder"><svg ${lucideSvgAttrs} width="14" height="14" class="chart-placeholder-icon">${lightbulbIconInner}</svg><span>图表生成中...</span></div>`;
  // 失败图表没有可用的 SVG 预览：按钮直接禁用（样式见 style-chat.css）
  const previewAttrs = isChartFailed(type, token.text)
    ? 'disabled title="图表渲染失败，无法预览"'
    : 'title="查看全屏预览"';

  return `<div class="chart-block ${completeClass} my-4 border-[0.5px] border-border-main overflow-hidden bg-code-bg" data-chart="${type}">
  <div class="flex justify-between items-center bg-bg-panel px-3 py-1.5 border-b-[0.5px] border-border-main">
    <span class="text-[10px] font-medium text-text-placeholder uppercase tracking-wider">${type}</span>
    <div class="flex items-center gap-2">
      <button class="chart-toggle-btn text-text-placeholder hover:text-text-main px-1 transition-colors flex items-center gap-1" title="切换显示">
        <svg ${lucideSvgAttrs} width="10" height="10" class="toggle-icon-svg">${arrowLeftRightIconInner}</svg>
        <span class="toggle-text text-[10px]">文字</span>
      </button>
      <button class="copy-chart-btn text-text-placeholder hover:text-text-main px-1 transition-colors flex items-center gap-1" title="复制代码">
        <svg ${lucideSvgAttrs} width="10" height="10" class="copy-icon-svg">${copyIconInner}</svg>
        <span class="text-[10px]">复制</span>
      </button>
      <button class="chart-fullscreen-btn text-text-placeholder hover:text-text-main px-1 transition-colors flex items-center gap-1" ${previewAttrs}>
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
// 「乱码 → 真文字」解码落定：按单元的出现时刻计算年龄，转成负 animation-delay
// 写入 span，重建出的新元素从上次渲染中断的进度无缝续播；解码在浏览器时间里
// 自行完成，与 chunk 到达节奏无关——停顿期间单元照常落定，不会卡在乱码状态。
// 每个 span 附带两份乱码副本（data-g1/data-g2，纯装饰、无语义，同 Unicode 范围随机），
// 由 CSS 伪元素交替显示后收起、真文字显形；乱码每帧重渲染都会重新随机，解码期间字形
// 自然持续变化。同一批次（出现时刻相同）的单元合并为一个 span。调用方需保存
// 返回的 tailState 并在下次渲染时传回。
// 出现时刻的继承必须按「单元」对齐（实体/代理对整体一格），且要能跨过尾文本节点
// 换身份的渲染（行内标签收拢、换段等）——错位或整批重来都会把特效套到错的字符上：
// 已显形的旧文字被重新隐藏+乱码、再整批解码出来，看起来像输出「攒一段再一起吐」。
export interface StreamTailState {
  text: string;   // 上次渲染的尾区文本（各文本节点按出现顺序的拼接）
  born: number[]; // 各单元的出现时刻（performance.now() 毫秒），与 text 的【单元】尾部对齐
  units: number;  // 上次渲染 text 的单元总数，born 保留末尾 min(units, STREAM_TAIL_KEEP) 个。
                  // 不能用 text.length 代替：那是 UTF-16 码元数，实体（&amp; 占 5 码元）
                  // 与 emoji（占 2 码元）会多算，混用会让 born 映射整体错位
}

const STREAM_TAIL_FADE = 500; // 尾段包裹窗口（ms）：年龄小于该值的单元才带乱码解码效果；style-chat.css 的解码动画 400ms 早于窗口结束
const STREAM_TAIL_WRAP = 6;   // 只有尾部这么多个单元带解码动效（「最后一小段」）——按位置封顶，
                              // 快速流式时不会随 500ms 窗口堆出一长条乱码；被挤出窗口的单元直接落定
const STREAM_TAIL_KEEP = 64;  // 状态中保留出现时刻的尾部单元数

// 同范围乱码：从与原字符相同的 Unicode 区间里随机取码位——大小写字母、数字、
// 标点、CJK、假名、全角、emoji 各在自己的范围里换。不用固定噪声池：固定字形
// 重复几次就容易被认出是「假字」，同范围随机才像信号错码
const GARBLE_RANGES: ReadonlyArray<readonly [number, number]> = [
  [0x0061, 0x007a], // a-z
  [0x0041, 0x005a], // A-Z
  [0x0030, 0x0039], // 0-9
  [0x0021, 0x002f], [0x003a, 0x0040], [0x005b, 0x0060], [0x007b, 0x007e], // ASCII 标点（分段，不跨到字母数字）
  [0x00c0, 0x024f], // 拉丁扩展
  [0x0370, 0x03ff], // 希腊
  [0x0400, 0x04ff], // 西里尔
  [0x2000, 0x206f], // 常用标点（弯引号、破折号等）
  [0x2500, 0x257f], // 制表线（无归属时的兜底，宽度接近）
  [0x2580, 0x259f], // 块状元素
  [0x2600, 0x26ff], // 杂项符号
  [0x3000, 0x303f], // CJK 标点（。，、「」等）
  [0x3040, 0x309f], // 平假名
  [0x30a0, 0x30ff], // 片假名
  [0x4e00, 0x9fff], // CJK 统一汉字
  [0xff00, 0xff60], // 全角形式
  [0x1f300, 0x1f5ff], // emoji / pictographs
];

const FALLBACK_RANGE: readonly [number, number] = [0x2500, 0x257f];

function garbleChar(cp: number): string {
  for (const [lo, hi] of GARBLE_RANGES) {
    if (cp >= lo && cp <= hi) return String.fromCodePoint(lo + Math.floor(Math.random() * (hi - lo + 1)));
  }
  return String.fromCodePoint(FALLBACK_RANGE[0] + Math.floor(Math.random() * (FALLBACK_RANGE[1] - FALLBACK_RANGE[0] + 1)));
}

// HTML 实体先解码回字符再同范围乱码（&amp; 的乱码是「一个」字符，不是六个）
const NAMED_ENTITIES: Record<string, number> = {
  amp: 0x26, lt: 0x3c, gt: 0x3e, quot: 0x22, apos: 0x27, nbsp: 0xa0,
};

function entityCodePoint(ent: string): number {
  const body = ent.slice(1, -1);
  if (body.startsWith('#')) {
    const cp = body[1] === 'x' || body[1] === 'X' ? parseInt(body.slice(2), 16) : parseInt(body.slice(1), 10);
    return Number.isFinite(cp) && cp > 0 ? cp : FALLBACK_RANGE[0];
  }
  return NAMED_ENTITIES[body.toLowerCase()] ?? FALLBACK_RANGE[0];
}

/** 乱码进 data-* 属性前必须转义：同范围随机会取到 " & < > 等属性敏感字符 */
function escapeAttr(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/** 文本节点的「单元」切分：HTML 实体、代理对（emoji）各算一格，其余逐字符。
 *  出现时刻、乱码映射、重叠对齐必须共用同一套单元计数（此前各处正则不一致——
 *  wrapStreamTail 的不认代理对、出现时刻又按 UTF-16 码元对齐，都会错位） */
const UNIT_RE = /&(?:#[0-9]+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);|[\uD800-\uDBFF][\uDC00-\uDFFF]|[\s\S]/gu;

function textUnits(text: string): string[] {
  return Array.from(text.matchAll(UNIT_RE), m => m[0]);
}

/** 把一个文本片段映射成等结构乱码：空白原样保留（保证对齐），
 *  HTML 实体解码后按字符范围取乱码，其余逐字同范围替换 */
function garbleRun(text: string): string {
  let out = '';
  for (const u of textUnits(text)) {
    if (!u.trim()) { out += u; continue; }
    out += u.startsWith('&') ? garbleChar(entityCodePoint(u)) : garbleChar(u.codePointAt(0)!);
  }
  return out;
}

// 对齐第二段：公共前缀之后的「旧余部尾 ↔ 新余部头」重叠单元数（见下方 born 对齐注释）。
// 在单元层比较（实体/代理对整体一格，不会从实体中间错位），上限 OVERLAP_UNITS：
// 更长的重叠早已落定，没必要再对
const OVERLAP_UNITS = 256;

function overlapUnitCount(prevU: string[], curU: string[]): number {
  const max = Math.min(prevU.length, curU.length, OVERLAP_UNITS);
  outer: for (let k = max; k > 0; k--) {
    for (let j = 0; j < k; j++) {
      if (prevU[prevU.length - k + j] !== curU[j]) continue outer;
    }
    return k;
  }
  return 0;
}

/** 尾区起点：最近一个「批量容器」的文本起点。
 *  一次视觉批次 = 一个批量容器（表格一行 <tr>、列表一条 <li>、段落/标题/代码块整体）。
 *  若上一个批量容器与最近一个同名（相邻的表格行/列表项/段落），窗口扩到两个——
 *  新容器开写时上一个容器的尾部还在解码窗口里，不中断解码；异名（段落→代码块等
 *  结构切换）只取最后一个，新容器整体视为新出现，旧容器不重置。
 *  找不到批量容器（纯原始 HTML 等）返回 -1，调用方退回「最后一个文本节点」 */
function tailRegionStart(html: string): number {
  const re = /<(p|li|tr|pre|h[1-6])(?=[\s>])/gi;
  let a: [number, string] = [-1, '']; // 最近一个批量容器
  let b: [number, string] = [-1, '']; // 上一个（任意标签名）
  for (let m = re.exec(html); m; m = re.exec(html)) {
    b = a;
    a = [m.index, m[1].toLowerCase()];
  }
  if (a[0] === -1) return -1;
  const start = b[0] !== -1 && b[1] === a[1] ? b[0] : a[0];
  return html.indexOf('>', start) + 1;
}

function wrapStreamTail(html: string, prev: StreamTailState | undefined, now: number): { html: string; state?: StreamTailState } {
  // === 尾区（region）定位：拖尾特效作用的文本范围 ===
  // 尾区取批量容器内的【全部文本节点】，拆多个节点是必须的，只看「最后一个文本节点」时：
  // - 表格行尾被 marked 补齐成空 <td>，尾节点几乎总是空格子或 2~3 字短格子（表格因此
  //   完全看不到特效）；行内格式把段落拆成多个碎片、hljs 把代码拆成一堆 span，特效
  //   只会落在最后一个小碎片上
  // - 代码块/图表块的按钮文字（复制/查看）也在块内，尾节点可能落在 UI 文字上
  // 各文本节点按出现顺序拼成一条单元流跟踪出现时刻：跨格/跨碎片拼接仍是纯追加
  // （格子/碎片从左到右生长），且 hljs 重新分词只改 span 边界、不改拼接文本，天然稳定
  const batchStart = tailRegionStart(html);
  let regionStart: number;
  if (batchStart !== -1) {
    regionStart = batchStart;
  } else {
    // 兜底：跳过结尾连续闭合标签，定位最后一个文本节点（起于最后一个 '>' 之后）
    const closeMatch = /(?:<\/[a-zA-Z][^>]*>\s*)+$/.exec(html);
    const end = closeMatch ? closeMatch.index : html.length;
    regionStart = html.lastIndexOf('>', end) + 1;
  }

  // 纯空白节点不参与——标签间换行、marked 补齐的空格子都是这类，行补齐不会让拼接错位
  const parts = html.slice(regionStart).split(/(<[^>]*>)/);
  const nodes: { pi: number; units: RegExpExecArray[]; offset: number }[] = [];
  let text = '';
  let total = 0;
  for (let pi = 0; pi < parts.length; pi++) {
    const part = parts[pi];
    if (!part || /^<[^>]*>$/.test(part)) continue; // 标签原样保留
    if (part.includes('<')) return { html }; // 文本节点定位失败（罕见），不带状态
    if (!part.trim()) continue;
    const us = Array.from(part.matchAll(UNIT_RE));
    nodes.push({ pi, units: us, offset: total });
    total += us.length;
    text += part;
  }
  if (!total) return { html };

  // 出现时刻对齐：新单元序列映射回旧单元序列，映射上的继承出现时刻（滑出保留窗口的
  // 视为早已落定），映射不上的才是新出现。映射 = 「公共前缀 + 余部旧尾↔新头」：
  // - 纯追加（最常见）就是全长前缀；
  // - 尾区窗口随容器前移（换行/换格/换条目）时，新尾区以旧尾区的尾部开头；
  // - markdown 重解析（** 收拢成 <strong>、行内代码闭合……）会先共享前缀，旧尾部
  //   再成为新余部的开头（"…包含**加粗重" → "…包含" + "加粗重点"）。
  // 窗口按单元计数，不是 text.length——实体/emoji 的码元数大于单元数，混用会整体错位。
  // 余部对齐的误匹配方向只会「把新字符错当旧字符跳过解码」，不会把旧文字重新隐藏
  let born: number[];
  if (!prev) {
    born = Array.from({ length: total }, () => now);
  } else {
    const prevU = textUnits(prev.text);
    const curU = textUnits(text);
    let c = 0;
    while (c < prevU.length && c < curU.length && prevU[c] === curU[c]) c++;
    const k = overlapUnitCount(prevU.slice(c), curU.slice(c));
    const windowStart = prev.units - prev.born.length;
    born = Array.from({ length: total }, (_, i) => {
      const p = i < c ? i : (i < c + k ? prev.units - k + (i - c) : -1);
      if (p === -1) return now;
      return p >= windowStart ? prev.born[p - windowStart] : now - STREAM_TAIL_FADE * 2;
    });
  }

  // 状态始终带出（哪怕本帧不包裹）：丢状态会让下一帧把旧文字整体当成新出现，
  // 重新隐藏+整批解码（输出「攒一段再一起吐」的直接来源）
  const state: StreamTailState = { text, born: born.slice(-STREAM_TAIL_KEEP), units: total };

  // 逐单元重组各文本节点：解码窗口内的按批次包 span（负 delay 从当前进度续播，
  // 延迟走 --tail-delay 自定义属性——animation-delay 不会被伪元素继承，必须 var 传递）。
  // wrapFrom 按【节点】封顶：每个文本节点只包尾部一小段（正文一段、表格一格都遵守
  // 「最后一小段」），快速流式时不会堆出一长条乱码
  const outs = new Map<number, string>();
  for (const node of nodes) {
    const src = parts[node.pi];
    const wrapFrom = Math.max(0, node.units.length - STREAM_TAIL_WRAP);
    let out = '';
    let plainFrom = 0;
    let i = 0;
    while (i < node.units.length) {
      const g = node.offset + i;
      if (i < wrapFrom || now - born[g] >= STREAM_TAIL_FADE) { i++; continue; }
      if (i > plainFrom) out += src.slice(node.units[plainFrom].index, node.units[i].index);
      const bornAt = born[g];
      let j = i + 1;
      while (j < node.units.length && born[node.offset + j] === bornAt) j++;
      const delay = ((now - bornAt) / 1000).toFixed(2);
      const runText = src.slice(node.units[i].index, j < node.units.length ? node.units[j].index : undefined);
      out += `<span class="stream-tail-unit" style="--tail-delay:-${delay}s" data-g1="${escapeAttr(garbleRun(runText))}" data-g2="${escapeAttr(garbleRun(runText))}">${runText}</span>`;
      i = j;
      plainFrom = i;
    }
    if (plainFrom < node.units.length) out += src.slice(node.units[plainFrom].index);
    outs.set(node.pi, out);
  }

  return {
    html: html.slice(0, regionStart) + parts.map((p, i) => outs.get(i) ?? p).join(''),
    state,
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
// 缓存的滤镜图形在流式重写消毒时不被剥掉；HTML_INTEGRATION_POINTS 放行 foreignObject 内的
// HTML 标签（mermaid htmlLabels 文字，详见 chart.ts 注释，缺了会“图表文字消失”）
const SANITIZE_OPTS = {
  USE_PROFILES: { html: true, svg: true, svgFilters: true },
  ADD_TAGS: ['foreignObject'],
  ADD_ATTR: ['transform', 'style', 'class'],
  HTML_INTEGRATION_POINTS: { foreignobject: true, 'annotation-xml': true },
};

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
