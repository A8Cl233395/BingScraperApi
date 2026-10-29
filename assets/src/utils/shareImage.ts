// AI 输出导出为图片（直接下载 PNG，仅正文）。
//
// 为什么要做离屏重组：正文渲染在影子根内（adoptedStyleSheets 共享样式表 + 模型内联
// <style> 的 :host 规则），样式依赖影子结构；而 html-to-image 只克隆 light DOM 里能
// 走到的宿主——直接截 #bubble-*-assistant 会把工具调用折叠块也带上，也做不出「仅正文」
// 的范围。因此把各正文段（MarkdownView 宿主）的影子内容克隆进离屏容器的新影子根
// （复用 createMessageShadowRoot，:host 规则与计算样式都和页面所见一致），再交给
// html-to-image：它会遍历 open shadow root 并逐节点复制计算样式（伪元素一并处理）、
// 内嵌 web 字体与图片。
//
// 懒加载：html-to-image 走动态 import，只在首次导出时拉取独立 chunk、不进主包；
// 调用方（MessageBubble）对本模块同样是动态 import。

import { createMessageShadowRoot } from './markdown';

// 克隆内容里要剥离的交互按钮：代码块复制/查看渲染结果、图表切换/复制/全屏
const STRIP_SELECTORS = '.copy-code-btn, .view-code-btn, .chart-toggle-btn, .copy-chart-btn, .chart-fullscreen-btn';

/** 把指定消息的 AI 正文导出为 PNG 并触发下载；失败抛错由调用方提示 */
export async function exportAssistantImage(nodeId: string): Promise<void> {
  const source = document.getElementById(`bubble-${nodeId}-assistant`);
  if (!source) throw new Error('未找到消息内容');

  // 正文段宿主 = 消息容器内带影子根的元素（MarkdownView）；思考、工具调用块是光 DOM，天然排除
  const hosts = Array.from(source.querySelectorAll<HTMLElement>('*')).filter(el => !!el.shadowRoot);
  if (!hosts.length) throw new Error('未找到正文内容');

  // 离屏挂进文档：样式表与主题变量（--bg-*，暗色自动跟随）正常生效。
  // 负定位只加在不参与截图的外层——html-to-image 会把节点的计算样式（含 position/left）
  // 逐条内联进克隆，被截的 wrapper 必须保持常规文档流
  const offscreen = document.createElement('div');
  offscreen.style.cssText = 'position:fixed;left:-10000px;top:0;';
  const wrapper = document.createElement('div');
  offscreen.appendChild(wrapper);

  try {
    // 宽度取正文实际宽度，换行与页面所见一致；隐藏节点量不到宽度时退回固定值
    const measured = Math.round(Math.max(...hosts.map(h => h.getBoundingClientRect().width)));
    wrapper.style.cssText = `width:${measured > 0 ? measured : 720}px;background:var(--bg-main);padding:24px;box-sizing:border-box;`;
    document.body.appendChild(offscreen);

    for (const host of hosts) {
      const srcContent = host.shadowRoot?.firstElementChild; // createMessageShadowRoot 建的 .prose 容器
      if (!srcContent) continue;
      const segHost = document.createElement('div');
      wrapper.appendChild(segHost);
      const seg = createMessageShadowRoot(segHost);
      for (const child of Array.from(srcContent.childNodes)) {
        seg.appendChild(child.cloneNode(true));
      }
      // 剥离交互按钮；流式乱码装饰 span 拆掉（其 ::before/::after 靠 data-g1/data-g2
      // 播解码动效，克隆进新影子根会重播动画），只留真文字
      seg.querySelectorAll(STRIP_SELECTORS).forEach(el => el.remove());
      seg.querySelectorAll('.stream-tail-unit').forEach(el => {
        el.replaceWith(document.createTextNode(el.textContent ?? ''));
      });
    }

    const bg = getComputedStyle(wrapper).backgroundColor;
    const { toBlob } = await import('html-to-image');
    const blob = await toBlob(wrapper, { pixelRatio: 2, backgroundColor: bg });
    if (!blob) throw new Error('生成图片失败');

    const now = new Date();
    const pad = (n: number) => String(n).padStart(2, '0');
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `AI输出-${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}.png`;
    a.click();
    // 立即撤销可能中断下载，延迟清理
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  } finally {
    offscreen.remove();
  }
}
