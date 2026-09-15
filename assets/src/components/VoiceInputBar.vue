<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue';
import { useVoiceInput } from '../composables/useVoiceInput';

const emit = defineEmits(['result', 'busy']);

const { isRecording, isRecognizing, startRecording, stopRecording, cancelRecording } = useVoiceInput();

/** 上滑超过该距离后松手视为取消 */
const CANCEL_DISTANCE = 60;

const isPressing = ref(false);
const isCancelling = ref(false);
const elapsed = ref(0);

let pressId = 0;
let startY = 0;
let timer: number | null = null;

const isBusy = computed(() => isRecording.value || isRecognizing.value);

watch(isBusy, (v) => emit('busy', v), { immediate: true });

const formattedTime = computed(() => {
  const total = Math.floor(elapsed.value);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
});

const startTimer = () => {
  stopTimer();
  elapsed.value = 0;
  timer = window.setInterval(() => {
    elapsed.value += 0.1;
  }, 100);
};

const stopTimer = () => {
  if (timer !== null) {
    clearInterval(timer);
    timer = null;
  }
};

onUnmounted(() => {
  stopTimer();
});

const handlePointerDown = async (e: PointerEvent) => {
  if (isBusy.value) return;
  (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);

  pressId++;
  const id = pressId;
  startY = e.clientY;
  isPressing.value = true;
  isCancelling.value = false;

  const ok = await startRecording();
  if (id !== pressId) {
    // 等待权限期间已松手/取消
    if (ok) cancelRecording();
    return;
  }
  if (!ok) {
    isPressing.value = false;
    return;
  }
  startTimer();
};

const handlePointerMove = (e: PointerEvent) => {
  if (!isPressing.value) return;
  isCancelling.value = startY - e.clientY > CANCEL_DISTANCE;
};

const handlePointerUp = async () => {
  if (!isPressing.value) return;
  pressId++;
  isPressing.value = false;
  stopTimer();

  if (isCancelling.value) {
    isCancelling.value = false;
    elapsed.value = 0;
    cancelRecording();
    return;
  }

  const text = await stopRecording();
  elapsed.value = 0;
  if (text) emit('result', text);
};

const handlePointerCancel = () => {
  if (!isPressing.value) return;
  pressId++;
  isPressing.value = false;
  isCancelling.value = false;
  stopTimer();
  elapsed.value = 0;
  cancelRecording();
};
</script>

<template>
  <button
    @pointerdown="handlePointerDown"
    @pointermove="handlePointerMove"
    @pointerup="handlePointerUp"
    @pointercancel="handlePointerCancel"
    @contextmenu.prevent
    @dragstart.prevent
    aria-label="按住说话"
    class="w-full h-10 flex items-center justify-center gap-2 text-sm transition-colors touch-none select-none"
    :class="[
      isRecognizing
        ? 'bg-bg-hover text-text-placeholder cursor-not-allowed'
        : isCancelling
          ? 'bg-bg-active text-danger-main'
          : isRecording
            ? 'bg-danger-main text-primary-text'
            : 'bg-transparent text-text-placeholder hover:bg-bg-hover'
    ]"
  >
    <template v-if="isRecording">
      <div v-if="!isCancelling" class="flex items-center gap-[3px] h-4">
        <span class="voice-bar w-[3px] h-full bg-current rounded-full" style="animation-delay: 0s"></span>
        <span class="voice-bar w-[3px] h-full bg-current rounded-full" style="animation-delay: 0.15s"></span>
        <span class="voice-bar w-[3px] h-full bg-current rounded-full" style="animation-delay: 0.3s"></span>
        <span class="voice-bar w-[3px] h-full bg-current rounded-full" style="animation-delay: 0.45s"></span>
      </div>
      <Mic v-else class="text-base" />
      <span>{{ isCancelling ? '松开手指，取消发送' : '松开发送，上滑取消' }}</span>
      <span v-if="!isCancelling" class="font-mono tabular-nums text-xs">{{ formattedTime }}</span>
    </template>
    <template v-else-if="isRecognizing">
      <Loader2 class="text-base animate-spin" />
      <span>识别中...</span>
    </template>
    <template v-else>
      <Mic class="text-base" />
      <span>按住说话</span>
    </template>
  </button>
</template>

<style scoped>
@keyframes voice-bar {
  0%, 100% { transform: scaleY(0.3); }
  50% { transform: scaleY(1); }
}

.voice-bar {
  animation: voice-bar 0.7s ease-in-out infinite;
}
</style>
