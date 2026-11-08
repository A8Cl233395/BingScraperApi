<script setup lang="ts">
import { ref, watch, computed, onMounted, onUnmounted, nextTick } from 'vue';
import { state } from '../store';
import { useToast } from '../composables/useToast';

const { showToast } = useToast();

const editName = ref('');
const editText = ref('');
const copied = ref(false);
let copiedTimer: ReturnType<typeof setTimeout> | null = null;
const textareaRef = ref<HTMLTextAreaElement | null>(null);

// 移动端浏览器/系统返回键关闭预览弹窗
let modalPushed = false;

watch(() => state.previewFile, (file) => {
  if (file) {
    editName.value = file.name;
    editText.value = file.text;
    copied.value = false;
    if (!modalPushed) {
      modalPushed = true;
      window.history.pushState({ filePreview: true }, '');
    }
    nextTick(() => {
      const el = textareaRef.value;
      if (!el) return;
      el.setSelectionRange(0, 0);
      if (!state.isMobile) {
        el.focus();
      }
      el.scrollTop = 0;
    });
  } else {
    editName.value = '';
    editText.value = '';
  }
});

const closeModal = () => {
  state.previewFile = null;
  if (modalPushed) {
    modalPushed = false;
    window.history.back();
  }
};

const handlePopState = () => {
  if (!state.previewFile) return;
  modalPushed = false;
  state.previewFile = null;
};

const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Escape' && state.previewFile) {
    closeModal();
  }
};

onMounted(() => {
  window.addEventListener('popstate', handlePopState);
  window.addEventListener('keydown', handleKeydown);
});

onUnmounted(() => {
  if (copiedTimer) clearTimeout(copiedTimer);
  window.removeEventListener('popstate', handlePopState);
  window.removeEventListener('keydown', handleKeydown);
});

const isAudioExt = (name: string) => {
  const ext = name.split('.').pop()?.toLowerCase() || '';
  return ['mp3', 'wav', 'ogg', 'aac', 'flac', 'm4a', 'webm'].includes(ext);
};

const charCountText = computed(() => {
  const len = editText.value.length;
  return len >= 1000 ? `${(len / 1000).toFixed(1)}k 字符` : `${len} 字符`;
});

const handleCopy = () => {
  navigator.clipboard.writeText(editText.value);
  if (copiedTimer) clearTimeout(copiedTimer);
  copied.value = true;
  copiedTimer = setTimeout(() => { copied.value = false; }, 2000);
};

const handleSave = () => {
  if (!state.previewFile) return;
  const trimmedName = editName.value.trim() || state.previewFile.name || '未命名文件.txt';
  if (trimmedName.length > 255) {
    showToast('文件名不能超过255个字符', 'error');
    return;
  }
  if (!editText.value.trim()) {
    showToast('文件内容不能为空', 'error');
    return;
  }
  if (editText.value.length > 1000000) {
    showToast('文件内容不能超过100万字符', 'error');
    return;
  }
  state.previewFile.onSave?.(editText.value, trimmedName);
  closeModal();
};
</script>

<template>
  <Transition name="modal">
    <div v-if="state.previewFile" class="fixed inset-0 z-1000 flex items-center justify-center p-4 sm:p-6">
      <!-- Backdrop -->
      <div
        class="absolute inset-0 bg-black/40 transition-opacity"
        @click="closeModal"
      ></div>

      <!-- Modal Panel -->
      <div
        class="modal-signal relative bg-bg-main shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden transform transition-transform border border-border-main"
        @click.stop
      >
        <!-- Header -->
        <div class="flex items-center justify-between gap-3 px-4 py-3 border-b border-border-main bg-bg-panel shrink-0">
          <div class="flex items-center gap-2.5 min-w-0 flex-1">
            <div class="w-7 h-7 flex items-center justify-center bg-bg-hover border border-border-main shrink-0">
              <component
                :is="isAudioExt(editName) ? 'Music' : 'FileText'"
                class="modal-signal-icon text-sm text-primary-main"
              />
            </div>
            <input
              v-model="editName"
              maxlength="255"
              class="edge-control modal-signal-title bg-bg-main border border-border-input px-2 py-1 text-xs font-medium text-text-main min-w-0 flex-1 outline-none"
              placeholder="文件名"
              title="修改文件名"
            />
            <span class="text-[11px] font-mono text-text-placeholder shrink-0 px-1.5 py-0.5 bg-bg-hover border border-border-main">
              {{ charCountText }}
            </span>
          </div>
          <button
            @click="closeModal"
            class="w-7 h-7 flex items-center justify-center text-text-placeholder hover:text-text-main transition-colors shrink-0"
            title="关闭 (Esc)"
          >
            <X class="text-sm" />
          </button>
        </div>

        <!-- Content Editor -->
        <div class="flex-1 min-h-0 p-4 flex flex-col bg-bg-main">
          <textarea
            ref="textareaRef"
            v-model="editText"
            maxlength="1000000"
            class="edge-control w-full h-[50vh] max-h-[60vh] bg-bg-panel border border-border-input p-3 text-xs font-mono leading-relaxed text-text-main resize-none outline-none overflow-y-auto"
            placeholder="文件文本内容..."
          ></textarea>
        </div>

        <!-- Footer Actions -->
        <div class="flex items-center justify-between px-4 py-3 border-t border-border-main bg-bg-panel shrink-0">
          <button
            @click="handleCopy"
            class="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-border-main bg-bg-main transition-colors"
            :class="copied ? 'text-success-main' : 'text-text-muted hover:text-text-main'"
          >
            <component :is="copied ? 'Check' : 'Copy'" class="text-xs" />
            <span>{{ copied ? '已复制' : '复制内容' }}</span>
          </button>

          <div class="flex items-center gap-2">
            <button
              @click="closeModal"
              class="px-4 py-1.5 text-xs font-medium text-text-muted hover:text-text-main border border-border-main bg-bg-main transition-colors"
            >
              取消
            </button>
            <button
              @click="handleSave"
              class="px-4 py-1.5 text-xs font-semibold bg-primary-main text-primary-text transition-colors"
            >
              保存修改
            </button>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.25s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .modal-signal {
  transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.modal-leave-active .modal-signal {
  transition: transform 0.18s ease-in;
}

.modal-enter-from .modal-signal {
  transform: scale(0.95) translateY(8px);
}

.modal-leave-to .modal-signal {
  transform: scale(0.97) translateY(4px);
}

.modal-signal {
  --modal-signal: var(--primary);
}

.modal-signal::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--glitch-cyan);
  opacity: 0;
  pointer-events: none;
  z-index: 2;
  animation: modal-signal-scan 320ms steps(1, end) 60ms forwards;
}

.modal-signal::after {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  width: 20px;
  height: 20px;
  border-top: 2px solid var(--modal-signal);
  border-left: 2px solid var(--modal-signal);
  opacity: 0;
  pointer-events: none;
  z-index: 2;
  animation: modal-signal-bracket 320ms steps(1, end) 60ms forwards;
}

@keyframes modal-signal-scan {
  0% { top: 0; opacity: 0.55; background: var(--glitch-cyan); }
  22% { top: 20%; opacity: 0.55; background: var(--glitch-cyan); }
  46% { top: 48%; opacity: 0.5; background: var(--modal-signal); }
  70% { top: 74%; opacity: 0.42; background: var(--glitch-magenta); }
  88% { top: 94%; opacity: 0.3; background: var(--modal-signal); }
  100% { top: 100%; opacity: 0; background: var(--modal-signal); }
}

@keyframes modal-signal-bracket {
  0% { width: 20px; height: 20px; opacity: 0.9; }
  30% { width: 13px; height: 13px; opacity: 0.9; }
  60% { width: 9px; height: 9px; opacity: 0.7; }
  100% { width: 8px; height: 8px; opacity: 0.35; }
}

.modal-signal-title {
  animation: modal-signal-title 220ms steps(1, end) 80ms forwards;
}

@keyframes modal-signal-title {
  0% { text-shadow: none; }
  18% { text-shadow: 1px 0 var(--glitch-text-cyan), -0.75px 0 var(--glitch-text-magenta); }
  40% { text-shadow: -0.75px 0 var(--glitch-text-cyan), 0.5px 0 var(--glitch-text-magenta); }
  62% { text-shadow: 0.4px 0 var(--glitch-text-cyan), -0.4px 0 var(--glitch-text-magenta); animation-timing-function: ease-out; }
  100% { text-shadow: none; }
}

.modal-signal-icon {
  animation: modal-signal-icon 200ms steps(1, end) 70ms forwards;
}

@keyframes modal-signal-icon {
  0% { filter: drop-shadow(1.5px 0 var(--glitch-cyan)) drop-shadow(-1px 0 var(--glitch-magenta)); }
  32% { filter: drop-shadow(-1px 0 var(--glitch-cyan)) drop-shadow(1px 0 var(--glitch-magenta)); }
  60% { filter: drop-shadow(0.5px 0 var(--glitch-cyan)) drop-shadow(-0.5px 0 var(--glitch-magenta)); }
  100% { filter: none; }
}

@media (prefers-reduced-motion: reduce) {
  .modal-signal::before {
    animation: none;
    opacity: 0;
  }

  .modal-signal::after {
    animation: none;
    width: 8px;
    height: 8px;
    opacity: 0.35;
  }

  .modal-signal-title,
  .modal-signal-icon {
    animation: none;
  }
}
</style>
