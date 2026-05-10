<script setup lang="ts">
import { state } from '../store';

const close = () => {
  state.showSelectionOverlay = false;
  state.selectionText = '';
};
</script>

<template>
  <Transition name="fade">
    <div v-if="state.showSelectionOverlay" class="fixed inset-0 z-1000 bg-bg-main flex flex-col">
      <header class="h-14 flex items-center px-4 justify-between border-b border-border-main shrink-0">
        <span class="font-medium text-text-main">选择文本</span>
        <button @click="close" class="w-10 h-10 flex items-center justify-center text-text-muted hover:text-text-main">
          <FontAwesomeIcon :icon="['fas', 'xmark']" class="text-lg" />
        </button>
      </header>
      <div class="flex-1 overflow-y-auto p-4 select-text">
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
