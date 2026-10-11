<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { state } from '../store';

// === 双模式预览 ===
// 视口 ≥1024px 且非移动 UA：右侧分屏面板（参与 Chat.vue 根 flex 布局，左缘可拖宽）；
// 否则：“选择文本”式全屏浮层。matchMedia 响应式监听，跨断点拖动窗口时保持打开并切换形态。
// 抽屉动画与 Sidebar 桌面端同款：外壳保持定宽，动画 margin-right 从 -定宽 到 0（CSS 变量 --panel-w），
// 整块内容平移滑入/滑出，布局占位同步抵消，聊天区平滑缩放。外壳必须有显式宽度——CSS 的 width
// 无法在 0 与 auto 之间过渡（会导致动画直接跳变失效）。依赖 Chat.vue 的 main 有 overflow-hidden——
// 侧栏展开时聊天顶栏以 translate-x-full 滑出隐藏，不裁剪会落到面板区域形成“幽灵顶栏”（z-40 仅作层级双保险）。
const wideQuery = window.matchMedia('(min-width: 1024px)');
const isWide = ref(wideQuery.matches);
const handleMediaChange = (e: MediaQueryListEvent) => { isWide.value = e.matches; };
const splitMode = computed(() => isWide.value && !state.isMobile);

const title = computed(() => (state.htmlPreviewLang === 'svg' ? 'SVG 预览' : 'HTML 预览'));

// === 分屏面板宽度 ===
// store 里的 htmlPreviewWidth 是用户拖拽后的持久化值（0 表示未调整过，用视口 40% 兜底）；
// currentWidth 是实际渲染宽度，打开/拖拽/窗口变化时按当前视口钳制
const MIN_WIDTH = 320;
const CHAT_MIN_WIDTH = 420; // 至少给聊天区保留的宽度
const defaultWidth = () => Math.max(MIN_WIDTH, Math.round(window.innerWidth * 0.4));
const maxWidth = () => Math.max(MIN_WIDTH, window.innerWidth - CHAT_MIN_WIDTH);
const clampWidth = (w: number) => Math.min(Math.max(w, MIN_WIDTH), maxWidth());
const currentWidth = ref(defaultWidth());

// === 移动端浏览器/系统返回键关闭浮层 ===
// 与 TextSelectionOverlay 相同的 pushState/popstate 逻辑；仅浮层形态持有历史记录，
// 分屏面板不压栈（桌面端返回/前进留给页面导航）
let pushed = false;

const pushHistory = () => {
  if (!pushed) {
    pushed = true;
    window.history.pushState({ htmlPreview: true }, '');
  }
};

const popHistory = () => {
  if (pushed) {
    pushed = false;
    window.history.back();
  }
};

const close = () => {
  state.showHtmlPreview = false;
  popHistory();
};

const handlePopState = () => {
  if (!pushed) return;
  pushed = false;
  state.showHtmlPreview = false;
};

// 打开/关闭/跨断点切换形态：维护历史记录 + 打开分屏时按当前视口计算初始宽度
watch([() => state.showHtmlPreview, splitMode], ([open, split]) => {
  if (open && !split) {
    pushHistory();
  } else {
    popHistory();
  }
  if (open && split) {
    currentWidth.value = clampWidth(state.htmlPreviewWidth || defaultWidth());
  }
});

// Esc 关闭（分屏面板的键盘快捷关闭，浮层同样适用）
const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Escape' && state.showHtmlPreview) close();
};

// 窗口尺寸变化：钳制面板宽度，保证聊天区最小宽度
const handleResize = () => {
  if (state.showHtmlPreview && splitMode.value) {
    currentWidth.value = clampWidth(currentWidth.value);
  }
};

// === srcdoc 组装 ===
// 完整文档（含 <html 或 <!doctype）原样使用；片段包一层带 charset/viewport 的骨架
// （svg 片段自然落入 body 渲染）。经 Vue :srcdoc 绑定写入，无需手动转义。
const srcdoc = computed(() => {
  const code = state.htmlPreviewCode;
  if (/<html[\s>]/i.test(code) || /<!doctype\s/i.test(code)) return code;
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head><body>${code}</body></html>`;
});

// 刷新：递增 key 重建 iframe 强制重载（srcdoc 不变时改属性不会触发重新加载）
const refreshKey = ref(0);
const refresh = () => { refreshKey.value++; };

// === 拖拽调整分屏宽度 ===
const dragging = ref(false);
let dragStartX = 0;
let dragStartWidth = 0;

const onHandleDown = (e: PointerEvent) => {
  e.preventDefault();
  dragging.value = true;
  dragStartX = e.clientX;
  dragStartWidth = currentWidth.value;
  document.body.style.userSelect = 'none'; // 拖拽期间禁止选中文本
  window.addEventListener('pointermove', onHandleMove);
  window.addEventListener('pointerup', onHandleUp);
};

const onHandleMove = (e: PointerEvent) => {
  currentWidth.value = clampWidth(dragStartWidth + (dragStartX - e.clientX)); // 面板在右侧，向左拖 = 变宽
  state.htmlPreviewWidth = currentWidth.value;
};

const onHandleUp = () => {
  dragging.value = false;
  document.body.style.userSelect = '';
  localStorage.setItem('html_preview_width', String(state.htmlPreviewWidth));
  window.removeEventListener('pointermove', onHandleMove);
  window.removeEventListener('pointerup', onHandleUp);
};

// 双击拖拽条：复位为视口 40%
const resetWidth = () => {
  state.htmlPreviewWidth = defaultWidth();
  currentWidth.value = state.htmlPreviewWidth;
  localStorage.setItem('html_preview_width', String(state.htmlPreviewWidth));
};

onMounted(() => {
  wideQuery.addEventListener('change', handleMediaChange);
  window.addEventListener('popstate', handlePopState);
  window.addEventListener('keydown', handleKeydown);
  window.addEventListener('resize', handleResize);
});

onUnmounted(() => {
  wideQuery.removeEventListener('change', handleMediaChange);
  window.removeEventListener('popstate', handlePopState);
  window.removeEventListener('keydown', handleKeydown);
  window.removeEventListener('resize', handleResize);
  window.removeEventListener('pointermove', onHandleMove);
  window.removeEventListener('pointerup', onHandleUp);
  if (dragging.value) {
    dragging.value = false;
    document.body.style.userSelect = '';
  }
});
</script>

<template>
  <!-- 分屏面板：参与 Chat.vue 根容器 flex 布局（Sidebar | main | 面板） -->
  <Transition name="panel-slide">
    <aside
      v-if="state.showHtmlPreview && splitMode"
      class="relative z-40 h-full shrink-0 bg-bg-main border-l-[0.5px] border-border-main overflow-hidden"
      :style="{ width: currentWidth + 'px', '--panel-w': currentWidth + 'px' }"
    >
      <div class="h-full flex flex-col">
        <header class="h-14 flex items-center px-4 justify-between border-b-[0.5px] border-border-main shrink-0">
          <span class="font-medium text-text-main">{{ title }}</span>
          <div class="flex items-center">
            <button @click="refresh" class="w-10 h-10 flex items-center justify-center text-text-muted hover:text-text-main transition-colors" title="刷新">
              <RotateCw class="text-base" />
            </button>
            <button @click="close" class="w-10 h-10 flex items-center justify-center text-text-muted hover:text-text-main transition-colors" title="关闭 (Esc)">
              <X class="text-lg" />
            </button>
          </div>
        </header>
        <iframe
          :key="refreshKey"
          :srcdoc="srcdoc"
          sandbox="allow-scripts allow-modals allow-forms"
          title="代码预览"
          class="flex-1 w-full border-0 bg-white"
          :style="dragging ? 'pointer-events: none' : ''"
        ></iframe>
      </div>
      <div
        class="absolute -left-1 top-0 bottom-0 w-2 cursor-col-resize z-10"
        :class="dragging ? 'bg-bg-hover' : 'hover:bg-bg-hover'"
        title="拖拽调整宽度，双击复位"
        @pointerdown="onHandleDown"
        @dblclick="resetWidth"
      ></div>
    </aside>
  </Transition>

  <!-- 全屏浮层：结构对齐 TextSelectionOverlay（移动端返回键可关闭） -->
  <Transition name="fade">
    <div v-if="state.showHtmlPreview && !splitMode" class="fixed inset-0 z-1000 bg-bg-main flex flex-col">
      <header class="h-14 flex items-center px-4 justify-between border-b border-border-main shrink-0">
        <span class="font-medium text-text-main">{{ title }}</span>
        <div class="flex items-center">
          <button @click="refresh" class="w-10 h-10 flex items-center justify-center text-text-muted hover:text-text-main" title="刷新">
            <RotateCw class="text-base" />
          </button>
          <button @click="close" class="w-10 h-10 flex items-center justify-center text-text-muted hover:text-text-main" title="关闭">
            <X class="text-lg" />
          </button>
        </div>
      </header>
      <iframe
        :key="refreshKey"
        :srcdoc="srcdoc"
        sandbox="allow-scripts allow-modals allow-forms"
        title="代码预览"
        class="flex-1 w-full border-0 bg-white"
      ></iframe>
    </div>
  </Transition>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
  transform: scale(0.95);
}

.panel-slide-enter-active, .panel-slide-leave-active {
  /* 负外边距抵消布局占位：整块平移滑入/滑出（Sidebar 桌面端 -ml-64 同款）。
     时长/缓动对齐聊天顶栏的滑动动画（150ms + Material 标准曲线）；
     拖拽调宽不经过 enter/leave 类，保持即时响应 */
  transition: margin-right 0.15s cubic-bezier(0.4, 0, 0.2, 1);
}
.panel-slide-enter-from, .panel-slide-leave-to {
  margin-right: calc(-1 * var(--panel-w));
}
</style>
