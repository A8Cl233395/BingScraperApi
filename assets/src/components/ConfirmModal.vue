<script setup lang="ts">
defineProps<{
  show: boolean;
  title?: string;
  message?: string;
  confirmText?: string;
  cancelText?: string;
  isDanger?: boolean;
}>();

const emit = defineEmits(['confirm', 'cancel']);
</script>

<template>
  <Transition name="modal">
    <div v-if="show" class="fixed inset-0 z-1000 flex items-center justify-center p-4 sm:p-6">
      <!-- Backdrop -->
      <div 
        class="absolute inset-0 bg-black/40 transition-opacity" 
        @click="emit('cancel')"
      ></div>

      <!-- Modal Content：打开时播一次「窗口上电」（扫描线 + 左上角标 + 标题/图标短分离）。
           不使用整块 outline：大面板上的描边位移像页面级脏边，且 text-shadow 会继承到所有文字。
           过渡只列 transform，不用 transition-all，避免特效属性被拖入过渡 -->
      <div 
        class="modal-signal relative bg-bg-main shadow-2xl w-full max-w-sm overflow-hidden transform transition-transform border border-border-main"
        :class="{ 'modal-signal-danger': isDanger }"
        @click.stop
      >
        <div class="p-6">
          <div class="flex items-center justify-center w-12 h-12 mb-4 mx-auto" :class="isDanger ? 'bg-danger-main/10' : 'bg-primary-main/10'">
            <component
              :is="isDanger ? 'TriangleAlert' : 'Info'"
              :class="[isDanger ? 'text-danger-main' : 'text-primary-main', 'modal-signal-icon', 'text-xl']"
            />
          </div>
          
          <h3 class="modal-signal-title text-lg font-semibold text-text-main text-center mb-2">
            {{ title || '确认操作' }}
          </h3>
          <p class="text-sm text-text-muted text-center">
            {{ message || '您确定要执行此操作吗？' }}
          </p>
        </div>

        <div class="flex border-t border-border-main">
          <button 
            @click="emit('cancel')"
            class="flex-1 px-4 py-4 text-sm font-medium text-text-muted transition-colors border-r border-border-main"
          >
            {{ cancelText || '取消' }}
          </button>
          <button 
            @click="emit('confirm')"
            class="flex-1 px-4 py-4 text-sm font-semibold transition-colors"
            :class="isDanger ? 'text-danger-main' : 'text-primary-main'"
          >
            {{ confirmText || '确认' }}
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.3s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .relative {
  transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.modal-leave-active .relative {
  transition: transform 0.2s ease-in;
}

.modal-enter-from .relative {
  transform: scale(0.9) translateY(10px);
}

.modal-leave-to .relative {
  transform: scale(0.95) translateY(5px);
}

/*
 * 打开信号：一条 2px 扫描线自上而下把窗口「上电」，左上角标同时收拢锁定。
 * 只做一次性动作，稳定后几乎不可见；danger 只换信号色 + 图标警示回抽。
 */
.modal-signal {
  --modal-signal: var(--primary);
}

.modal-signal-danger {
  --modal-signal: var(--danger);
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

/* 只有标题做短促的 RGB 分离；正文保持干净，避免整窗文字一起发彩边 */
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

/* danger：图标多一次「警示回抽」，但不动面板本体 */
.modal-signal-danger .modal-signal-icon {
  animation: modal-signal-alert 240ms steps(1, end) 70ms forwards;
}

@keyframes modal-signal-alert {
  0% { transform: scale(1); filter: drop-shadow(1.5px 0 var(--glitch-cyan)) drop-shadow(-1px 0 var(--glitch-magenta)); }
  20% { transform: scale(1.08); }
  40% { transform: scale(1); }
  60% { transform: scale(1.03); filter: drop-shadow(0.5px 0 var(--glitch-cyan)) drop-shadow(-0.5px 0 var(--glitch-magenta)); }
  100% { transform: none; filter: none; }
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
  .modal-signal-icon,
  .modal-signal-danger .modal-signal-icon {
    animation: none;
  }
}
</style>
