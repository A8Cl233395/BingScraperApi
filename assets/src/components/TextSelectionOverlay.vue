<script setup lang="ts">
import { onMounted, onUnmounted, watch } from 'vue';
import { state } from '../store';

// 移动端浏览器/系统返回键关闭浮层：打开时压入一条不改变 URL 的历史记录，
// 返回键触发 popstate 时关闭浮层；点击关闭按钮则主动回退该记录，避免历史栈堆积
let overlayPushed = false;

const close = () => {
  state.showSelectionOverlay = false;
  state.selectionText = '';
  if (overlayPushed) {
    overlayPushed = false;
    window.history.back();
  }
};

watch(() => state.showSelectionOverlay, (open) => {
  if (open && !overlayPushed) {
    overlayPushed = true;
    window.history.pushState({ selectionOverlay: true }, '');
  }
});

const handlePopState = () => {
  if (!state.showSelectionOverlay) return;
  overlayPushed = false;
  state.showSelectionOverlay = false;
  state.selectionText = '';
};

onMounted(() => window.addEventListener('popstate', handlePopState));
onUnmounted(() => window.removeEventListener('popstate', handlePopState));
</script>

<template>
  <Transition name="fade">
    <div v-if="state.showSelectionOverlay" class="fixed inset-0 z-1000 bg-bg-main flex flex-col">
      <header class="h-14 flex items-center px-4 justify-between border-b border-border-main shrink-0">
        <span class="font-medium text-text-main">选择文本</span>
        <button @click="close" class="w-10 h-10 flex items-center justify-center text-text-muted hover:text-text-main">
          <X class="text-lg" />
        </button>
      </header>
      <div class="flex-1 overflow-y-auto p-4">
        <pre class="text-text-main text-sm leading-relaxed whitespace-pre-wrap wrap-break-words font-sans">{{ state.selectionText }}</pre>
      </div>
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

pre {
  user-select: text !important;
}
</style>
