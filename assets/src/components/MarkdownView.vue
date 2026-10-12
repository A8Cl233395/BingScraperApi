<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { state } from '../store';
import {
  renderMarkdown,
  createMessageShadowRoot,
  arrowLeftRightIconInner,
  codeIconInner,
  checkIconInner,
} from '../utils/markdown';
import { renderChartPlaceholders, getChartSvgDataUrl, chartTypeOf } from '../utils/chart';
import type { StreamTailState } from '../utils/markdown';

const props = defineProps<{ content: string; streaming?: boolean }>();

const rootRef = ref<HTMLElement | null>(null);

// === 选择期间冻结渲染 ===
// 内容更新会整体重建子树，选区锚点节点被销毁后浏览器会把选区钳制到存活的祖先节点
// （表现为选区跳到开头）。实际渲染的 displayedContent 在选择期间保持旧值：冻结期间
// chunk 不解析、不写 DOM，恢复时一次性应用最新内容；已完成段落因 props 不变被 Vue
// 整体跳过更新，天然不受影响。状态标志由 Chat.vue 的全局 mousedown/touch/selectionchange
// 监听维护；思考过程等纯插值文本是原地更新 text node、不销毁节点，无需同样冻结。
// 拖尾淡入是时间驱动的（负 animation-delay）：冻结期间已有动画在真实时间自行推进，
// 恢复后按新年龄重算 delay 无缝衔接；流结束后不再重渲染，最后一批字符自然落定。
const displayedContent = ref(props.content);
const html = ref('');
let tailState: StreamTailState | undefined;
let frozen = state.isMouseDown || state.isTextSelected; // 挂载时可能已处于选择中
let resumeTimer: number | null = null;

// === Shadow DOM 渲染 ===
// 消息 HTML（含模型内联 <style>）写进影子根，样式隔离由浏览器原生保证（详见
// markdown.ts）。v-html 写不进影子根，内容更新改为手动写 DOM；子树整体重建会丢失
// pre/表格横向滚动，重写前后保存/恢复。图表块只显示不交互（缩放/拖拽在「查看」
// 进入的全屏预览里），无需恢复缩放状态。
let contentEl: HTMLElement | null = null;
let savedPreScrolls: number[] = [];
let savedWrapperScrolls: number[] = [];

const applyHtml = () => {
  const el = contentEl;
  if (!el) return;
  savedPreScrolls = Array.from(el.querySelectorAll('pre'), pre => pre.scrollLeft);
  savedWrapperScrolls = Array.from(el.querySelectorAll<HTMLElement>('.table-wrapper'), wrapper => wrapper.scrollLeft);
  el.innerHTML = html.value;
  el.querySelectorAll('pre').forEach((pre, i) => {
    if (savedPreScrolls[i] !== undefined) pre.scrollLeft = savedPreScrolls[i];
  });
  el.querySelectorAll<HTMLElement>('.table-wrapper').forEach((wrapper, i) => {
    if (savedWrapperScrolls[i] !== undefined) wrapper.scrollLeft = savedWrapperScrolls[i];
  });
  // 图表块（mermaid/svg）在解析器完成围栏闭合后才输出，流式期间也可安全渲染
  if (el.querySelector('.chart-block.chart-complete:not(.rendered)')) {
    renderChartPlaceholders(el);
  }
};

const rerender = (tail: boolean) => {
  const res = renderMarkdown(displayedContent.value, { streamTail: tail, tailState, now: performance.now() });
  tailState = res.tailState;
  html.value = res.html;
  applyHtml();
};

watch(
  [() => props.content, () => state.isMouseDown, () => state.isTextSelected],
  ([content, down, selected]) => {
    if (resumeTimer) {
      clearTimeout(resumeTimer);
      resumeTimer = null;
    }
    if (down || selected) {
      frozen = true;
      return;
    }
    if (frozen) {
      frozen = false;
      if (displayedContent.value === content) return;
      // 从冻结恢复：短暂缓冲等选区状态稳定（mouseup 可能先于最终的 selectionchange）
      resumeTimer = window.setTimeout(() => {
        resumeTimer = null;
        if (!state.isMouseDown && !state.isTextSelected && displayedContent.value !== props.content) {
          displayedContent.value = props.content;
          rerender(props.streaming);
        }
      }, 300);
    } else if (displayedContent.value !== content) {
      displayedContent.value = content; // 正常流式：立即应用
      rerender(props.streaming);
    }
  }
);

rerender(props.streaming); // 首次渲染（含挂载时已在流式中的情况）

onMounted(() => {
  contentEl = createMessageShadowRoot(rootRef.value!);
  applyHtml();
});

onBeforeUnmount(() => {
  if (resumeTimer) clearTimeout(resumeTimer);
});

// 代码块/图表块复制按钮的统一反馈动画（与消息操作栏复制按钮一致：图标换对勾 + 主题成功色 + "已复制"淡入）
const INLINE_COPY_FEEDBACK_MS = 2000;
const showInlineCopyFeedback = (btn: HTMLElement) => {
  const copySvg = btn.querySelector<SVGElement>('.copy-icon-svg');
  const textEl = btn.querySelector<HTMLElement>('span');
  if (!copySvg || !textEl) return;
  if (btn.dataset.copyTimer) clearTimeout(Number(btn.dataset.copyTimer));
  // 仅首次捕获原始图标，避免反馈期间二次点击把对勾当成"原图标"
  const originalInner = btn.dataset.copyIcon ?? copySvg.innerHTML;
  btn.dataset.copyIcon = originalInner;
  btn.classList.add('text-success-main');
  btn.classList.remove('text-text-placeholder', 'hover:text-text-main');
  copySvg.innerHTML = checkIconInner;
  textEl.textContent = '已复制';
  textEl.classList.remove('copy-feedback-fade');
  void textEl.offsetWidth; // 强制重排以重新触发淡入动画
  textEl.classList.add('copy-feedback-fade');
  btn.dataset.copyTimer = String(setTimeout(() => {
    delete btn.dataset.copyTimer;
    delete btn.dataset.copyIcon;
    btn.classList.remove('text-success-main');
    btn.classList.add('text-text-placeholder', 'hover:text-text-main');
    copySvg.innerHTML = originalInner;
    textEl.textContent = '复制';
  }, INLINE_COPY_FEEDBACK_MS));
};

// 内容渲染在影子树内，点击事件冒泡（composed）到宿主后在这里统一委托处理
// （图片预览 / 图表块与代码块按钮）。注意影子树内事件的 e.target 会被重定向到
// 宿主元素，真实目标必须取 composedPath 的首位
const handleContentClick = (e: MouseEvent) => {
  const target = (e.composedPath()[0] as HTMLElement) ?? (e.target as HTMLElement);
  if (target.tagName === 'IMG') {
    const src = (target as HTMLImageElement).src;
    if (src) {
      state.previewImageUrl = src;
    }
    return;
  }

  // 处理图表块切换按钮（mermaid / svg 共用）
  const toggleBtn = target.closest('.chart-toggle-btn');
  if (toggleBtn) {
    e.stopPropagation();
    const block = toggleBtn.closest('.chart-block');
    if (block) {
      const content = block.querySelector('.chart-content');
      const toggleText = toggleBtn.querySelector('.toggle-text');
      const toggleIcon = toggleBtn.querySelector('.toggle-icon-svg');
      if (content && toggleText && toggleIcon) {
        content.classList.toggle('show-source');
        const isSource = content.classList.contains('show-source');
        toggleText.textContent = isSource ? '图表' : '文字';
        // 切换图标：代码图标 <-> 图表图标
        if (isSource) {
          toggleIcon.innerHTML = codeIconInner;
        } else {
          toggleIcon.innerHTML = arrowLeftRightIconInner;
        }
      }
    }
    return;
  }

  // 处理图表块复制按钮（mermaid / svg 共用）
  const copyChartBtn = target.closest<HTMLElement>('.copy-chart-btn');
  if (copyChartBtn) {
    e.stopPropagation();
    const block = copyChartBtn.closest('.chart-block');
    if (block) {
      const codeElement = block.querySelector('.chart-source code');
      if (codeElement) {
        const code = codeElement.textContent || '';
        navigator.clipboard.writeText(code).then(() => showInlineCopyFeedback(copyChartBtn));
      }
    }
    return;
  }

  // 处理图表块“查看”按钮（mermaid / svg 共用）：打开全屏预览（ImagePreview），
  // 缩放/拖拽在预览里操作；data URL 来自 chart.ts 的渲染缓存
  const fullscreenChartBtn = target.closest<HTMLElement>('.chart-fullscreen-btn');
  if (fullscreenChartBtn) {
    e.stopPropagation();
    const block = fullscreenChartBtn.closest('.chart-block');
    if (block) {
      const code = block.querySelector('.chart-source code')?.textContent || '';
      const dataUrl = getChartSvgDataUrl(chartTypeOf(block), code);
      if (dataUrl) state.previewImageUrl = dataUrl;
    }
    return;
  }

  // 处理代码块“查看”按钮（html 沙箱预览）：textContent 即还原后的源码，
  // 预览内容为点击时刻的快照，不随流式输出更新
  const viewBtn = target.closest<HTMLElement>('.view-code-btn');
  if (viewBtn) {
    e.stopPropagation();
    const codeElement = viewBtn.closest('.code-block-wrapper')?.querySelector('pre code');
    if (codeElement) {
      state.htmlPreviewCode = codeElement.textContent || '';
      state.showHtmlPreview = true;
    }
    return;
  }

  // 处理代码块复制按钮
  const btn = target.closest<HTMLElement>('.copy-code-btn');
  if (!btn) return;
  const wrapper = btn.closest('.code-block-wrapper');
  const codeElement = wrapper?.querySelector('code');
  if (codeElement) {
    const code = codeElement.textContent || '';
    navigator.clipboard.writeText(code).then(() => showInlineCopyFeedback(btn));
  }
};
</script>

<template>
  <!-- prose 类在影子树内层（createMessageShadowRoot），宿主只负责定位与点击委托 -->
  <div ref="rootRef" class="relative z-10 max-w-none" @click="handleContentClick"></div>
</template>
