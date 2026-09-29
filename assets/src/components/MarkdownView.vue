<script setup lang="ts">
import { onBeforeUpdate, onBeforeUnmount, onMounted, onUpdated, ref, watch } from 'vue';
import { state } from '../store';
import {
  renderMarkdown,
  loadMermaid,
  getMermaidModule,
  arrowLeftRightIconInner,
  codeIconInner,
  checkIconInner,
} from '../utils/markdown';
import type { StreamTailState } from '../utils/markdown';

const props = defineProps<{ content: string; streaming?: boolean }>();

const rootRef = ref<HTMLElement | null>(null);

// === 选择期间冻结渲染 ===
// 增长段的 v-html 每次更新都会整体重建子树，选区锚点节点被销毁后浏览器会把选区
// 钳制到存活的祖先节点（表现为选区跳到开头）。实际渲染的 displayedContent 在选择
// 期间保持旧值：冻结期间 chunk 不解析、不写 DOM，恢复时一次性应用最新内容；已完成
// 段落因 props 不变被 Vue 整体跳过更新，天然不受影响。状态标志由 Chat.vue 的全局
// mousedown/touch/selectionchange 监听维护；思考过程等纯插值文本是原地更新
// text node、不销毁节点，无需同样冻结。
// 拖尾淡入是时间驱动的（负 animation-delay）：冻结期间已有动画在真实时间自行推进，
// 恢复后按新年龄重算 delay 无缝衔接；流结束后不再重渲染，最后一批字符自然落定。
const displayedContent = ref(props.content);
const html = ref('');
let tailState: StreamTailState | undefined;
let frozen = state.isMouseDown || state.isTextSelected; // 挂载时可能已处于选择中
let resumeTimer: number | null = null;

const rerender = (tail: boolean) => {
  const res = renderMarkdown(displayedContent.value, { streamTail: tail, tailState, now: performance.now() });
  tailState = res.tailState;
  html.value = res.html;
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

onBeforeUnmount(() => {
  if (resumeTimer) clearTimeout(resumeTimer);
});

// === 内容重写时的状态恢复 ===
// 本组件只在自身 content 变化时更新，此时浏览器会重建整个子树，pre/表格的横向
// 滚动与图表缩放状态会丢失，这里在更新前后保存/恢复。mermaid 重渲染是异步的，
// 且会用缓存 HTML 覆盖图表容器，缩放状态须等它完成后恢复。
let savedPreScrolls: number[] = [];
let savedWrapperScrolls: number[] = [];
let savedZooms: { transform: string; resetDisplay: string }[] = [];

onBeforeUpdate(() => {
  const el = rootRef.value;
  if (!el) return;
  savedPreScrolls = Array.from(el.querySelectorAll('pre'), pre => pre.scrollLeft);
  savedWrapperScrolls = Array.from(el.querySelectorAll<HTMLElement>('.table-wrapper'), wrapper => wrapper.scrollLeft);
  savedZooms = Array.from(el.querySelectorAll<HTMLElement>('.mermaid-zoom-inner'), inner => ({
    transform: inner.style.transform,
    resetDisplay: (inner.parentElement?.querySelector<HTMLElement>('.mermaid-zoom-reset'))?.style.display ?? '',
  }));
});

const restoreScrolls = (el: HTMLElement) => {
  el.querySelectorAll('pre').forEach((pre, i) => {
    if (savedPreScrolls[i] !== undefined) pre.scrollLeft = savedPreScrolls[i];
  });
  el.querySelectorAll<HTMLElement>('.table-wrapper').forEach((wrapper, i) => {
    if (savedWrapperScrolls[i] !== undefined) wrapper.scrollLeft = savedWrapperScrolls[i];
  });
};

const restoreZooms = (el: HTMLElement) => {
  el.querySelectorAll<HTMLElement>('.mermaid-zoom-inner').forEach((inner, i) => {
    const saved = savedZooms[i];
    if (!saved) return;
    inner.style.transform = saved.transform;
    const resetBtn = inner.parentElement?.querySelector<HTMLElement>('.mermaid-zoom-reset');
    if (resetBtn) resetBtn.style.display = saved.resetDisplay;
  });
};

onUpdated(() => {
  const el = rootRef.value;
  if (!el) return;
  restoreScrolls(el);
  // mermaid 代码块在 marked 解析器完成围栏闭合后才输出，流式期间也可安全渲染
  if (getMermaidModule() || el.querySelector('.mermaid-block.mermaid-complete:not(.rendered)')) {
    loadMermaid().then(m => m.renderMermaidPlaceholders(el)).then(() => restoreZooms(el));
  } else {
    restoreZooms(el);
  }
});

onMounted(() => {
  const el = rootRef.value;
  if (el && el.querySelector('.mermaid-block.mermaid-complete:not(.rendered)')) {
    loadMermaid().then(m => m.renderMermaidPlaceholders(el));
  }
});

// 代码块/mermaid 复制按钮的统一反馈动画（与消息操作栏复制按钮一致：图标换对勾 + 主题成功色 + "已复制"淡入）
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

// 内容为 v-html，点击事件在这里统一委托处理（图片预览 / mermaid 与代码块按钮）
const handleContentClick = (e: MouseEvent) => {
  const target = e.target as HTMLElement;
  if (target.tagName === 'IMG') {
    const src = (target as HTMLImageElement).src;
    if (src) {
      state.previewImageUrl = src;
    }
    return;
  }

  // 处理mermaid切换按钮
  const toggleBtn = target.closest('.mermaid-toggle-btn');
  if (toggleBtn) {
    e.stopPropagation();
    const block = toggleBtn.closest('.mermaid-block');
    if (block) {
      const content = block.querySelector('.mermaid-content');
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

  // 处理mermaid复制按钮
  const copyMermaidBtn = target.closest<HTMLElement>('.copy-mermaid-btn');
  if (copyMermaidBtn) {
    e.stopPropagation();
    const block = copyMermaidBtn.closest('.mermaid-block');
    if (block) {
      const codeElement = block.querySelector('.mermaid-source code');
      if (codeElement) {
        const code = codeElement.textContent || '';
        navigator.clipboard.writeText(code).then(() => showInlineCopyFeedback(copyMermaidBtn));
      }
    }
    return;
  }

  // 处理mermaid全屏按钮
  const fullscreenMermaidBtn = target.closest('.mermaid-fullscreen-btn');
  if (fullscreenMermaidBtn) {
    e.stopPropagation();
    const block = fullscreenMermaidBtn.closest('.mermaid-block');
    if (block) {
      const code = block.querySelector('.mermaid-source code')?.textContent || '';
      if (code) {
        loadMermaid().then(m => {
          const dataUrl = m.getSvgDataUrl(code);
          if (dataUrl) state.previewImageUrl = dataUrl;
        });
      }
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
  <div
    ref="rootRef"
    class="relative z-10 prose prose-sm max-w-none text-text-main wrap-anywhere"
    v-html="html"
    @click="handleContentClick"
  ></div>
</template>
