<script setup lang="ts">
import { nextTick, ref, watch, onMounted, onUnmounted } from 'vue';
import { state } from '../store';

const scale = ref(1);
const translateX = ref(0);
const translateY = ref(0);
const isDragging = ref(false);
const startX = ref(0);
const startY = ref(0);

let lastTouchDistance = 0;
let lastTouchMidX = 0;
let lastTouchMidY = 0;

const fitScale = ref(1);
// 打开时的自动适配必须直接落定、不播缩放动画：
// - 适配完成前先隐藏图片，避免 <img> 先按原始尺寸（或 0 尺寸）参与布局后再缩放到位
// - 适配结果落定后再单独开启过渡，保证首帧不会把 1 → fitScale 的跳变补成动画
const fitted = ref(false);
const transitionEnabled = ref(false);
let transitionRaf = 0;

// 移动端浏览器/系统返回键关闭预览：打开时压入一条不改变 URL 的历史记录，
// 返回键触发 popstate 时关闭预览；点击关闭按钮则主动回退该记录，避免历史栈堆积
let previewPushed = false;

const resetView = () => {
  scale.value = fitScale.value;
  translateX.value = 0;
  translateY.value = 0;
};

watch(() => state.previewImageUrl, (newUrl) => {
  if (newUrl) {
    fitScale.value = 1;
    fitted.value = false;
    transitionEnabled.value = false;
    cancelAnimationFrame(transitionRaf);
    resetView();
    if (!previewPushed) {
      previewPushed = true;
      window.history.pushState({ imagePreview: true }, '');
    }
  } else {
    // 关闭时同步清掉显示/过渡状态，避免下次打开复用上一张图的残留
    fitted.value = false;
    transitionEnabled.value = false;
    cancelAnimationFrame(transitionRaf);
  }
});

const handlePopState = () => {
  if (!state.previewImageUrl) return;
  previewPushed = false;
  state.previewImageUrl = null;
};

const handleImageLoad = async (e: Event) => {
  const img = e.target as HTMLImageElement;
  const { naturalWidth, naturalHeight } = img;
  if (naturalWidth && naturalHeight) {
    const scaleX = window.innerWidth / naturalWidth;
    const scaleY = window.innerHeight / naturalHeight;

    fitScale.value = Math.min(scaleX, scaleY, 1);
    resetView();
  }
  // 适配结果先无过渡写入 DOM 并强制重排落定（此时图片仍隐藏），
  // 再显示图片，最后才开启后续缩放/拖拽的过渡
  await nextTick();
  void img.offsetWidth;
  fitted.value = true;
  transitionRaf = requestAnimationFrame(() => {
    if (fitted.value) transitionEnabled.value = true;
  });
};

const handleImageError = () => {
  // 加载失败时也显示出来，至少能看到破损图标/替代文本，避免遮罩一片空白
  fitted.value = true;
  transitionEnabled.value = true;
};

const closePreview = () => {
  state.previewImageUrl = null;
  if (previewPushed) {
    previewPushed = false;
    window.history.back();
  }
};

const handleWheel = (e: WheelEvent) => {
  e.preventDefault();
  const zoomSensitivity = 0.1;
  const delta = e.deltaY > 0 ? -1 : 1;
  let newScale = scale.value + delta * zoomSensitivity;
  newScale = Math.max(0.05, Math.min(newScale, 10));
  
  // 以鼠标位置为缩放中心（transform-origin 默认 center）
  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
  const mouseX = e.clientX - rect.left;
  const mouseY = e.clientY - rect.top;

  const centerX = rect.width / 2;
  const centerY = rect.height / 2;
  const offsetX = mouseX - centerX;
  const offsetY = mouseY - centerY;

  const ratio = newScale / scale.value;
  translateX.value = offsetX * (1 - ratio) + translateX.value * ratio;
  translateY.value = offsetY * (1 - ratio) + translateY.value * ratio;
  scale.value = newScale;
};

const handleMouseDown = (e: MouseEvent) => {
  e.preventDefault();
  isDragging.value = true;
  startX.value = e.clientX - translateX.value;
  startY.value = e.clientY - translateY.value;
};

const handleMouseMove = (e: MouseEvent) => {
  if (!isDragging.value) return;
  translateX.value = e.clientX - startX.value;
  translateY.value = e.clientY - startY.value;
};

const handleMouseUp = () => {
  isDragging.value = false;
};

const getTouchDistance = (touches: TouchList) => {
  const dx = touches[0].clientX - touches[1].clientX;
  const dy = touches[0].clientY - touches[1].clientY;
  return Math.sqrt(dx * dx + dy * dy);
};

const getTouchMidpoint = (touches: TouchList) => {
  return {
    x: (touches[0].clientX + touches[1].clientX) / 2,
    y: (touches[0].clientY + touches[1].clientY) / 2
  };
};

const handleTouchStart = (e: TouchEvent) => {
  if (e.touches.length === 2) {
    e.preventDefault();
    lastTouchDistance = getTouchDistance(e.touches);
    const mid = getTouchMidpoint(e.touches);
    lastTouchMidX = mid.x;
    lastTouchMidY = mid.y;
    isDragging.value = false;
  } else if (e.touches.length === 1) {
    isDragging.value = true;
    startX.value = e.touches[0].clientX - translateX.value;
    startY.value = e.touches[0].clientY - translateY.value;
  }
};

const handleTouchMove = (e: TouchEvent) => {
  if (e.touches.length === 2) {
    e.preventDefault();
    const distance = getTouchDistance(e.touches);
    const mid = getTouchMidpoint(e.touches);
    
    if (lastTouchDistance > 0) {
      const scaleChange = distance / lastTouchDistance;
      let newScale = scale.value * scaleChange;
      newScale = Math.max(0.05, Math.min(newScale, 10));
      
      const dx = mid.x - lastTouchMidX;
      const dy = mid.y - lastTouchMidY;
      translateX.value += dx;
      translateY.value += dy;
      
      scale.value = newScale;
    }
    
    lastTouchDistance = distance;
    lastTouchMidX = mid.x;
    lastTouchMidY = mid.y;
  } else if (e.touches.length === 1 && isDragging.value) {
    e.preventDefault();
    translateX.value = e.touches[0].clientX - startX.value;
    translateY.value = e.touches[0].clientY - startY.value;
  }
};

const handleTouchEnd = (e: TouchEvent) => {
  if (e.touches.length < 2) {
    lastTouchDistance = 0;
  }
  if (e.touches.length === 0) {
    isDragging.value = false;
  }
};

const zoomIn = () => {
  scale.value = Math.min(scale.value + 0.2, 10);
};

const zoomOut = () => {
  scale.value = Math.max(scale.value - 0.2, 0.05);
};

const downloadImage = async () => {
  if (!state.previewImageUrl) return;
  try {
    const response = await fetch(state.previewImageUrl);
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'image.png'; // Provide a default or extracted name
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  } catch (error) {
    console.error('Failed to download image:', error);
    // Fallback if fetch fails (e.g. CORS)
    const a = document.createElement('a');
    a.href = state.previewImageUrl;
    a.download = 'image.png';
    a.target = '_blank';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }
};

onMounted(() => {
  window.addEventListener('mousemove', handleMouseMove);
  window.addEventListener('mouseup', handleMouseUp);
  window.addEventListener('popstate', handlePopState);
});

onUnmounted(() => {
  cancelAnimationFrame(transitionRaf);
  window.removeEventListener('mousemove', handleMouseMove);
  window.removeEventListener('mouseup', handleMouseUp);
  window.removeEventListener('popstate', handlePopState);
});

// Handle escape key to close
const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Escape' && state.previewImageUrl) {
    closePreview();
  }
};

onMounted(() => {
  window.addEventListener('keydown', handleKeydown);
});

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown);
});

</script>

<template>
  <div v-if="state.previewImageUrl"
       class="fixed inset-0 z-100 flex items-center justify-center bg-black/90"
       @wheel="handleWheel"
       @click.self="closePreview">

      <!-- Image Container -->
      <div class="relative w-full h-full flex items-center justify-center overflow-hidden" @click.self="closePreview">
        <img :src="state.previewImageUrl"
             alt="Preview"
             class="max-w-none max-h-none object-contain select-none"
             :class="[
               isDragging ? 'cursor-grabbing' : 'cursor-grab',
               fitted ? '' : 'invisible',
               transitionEnabled ? 'transition-transform duration-75 ease-out' : ''
             ]"
             :style="{ transform: `translate(${translateX}px, ${translateY}px) scale(${scale})`, touchAction: 'none' }"
             @load="handleImageLoad"
             @error="handleImageError"
             @mousedown="handleMouseDown"
             @touchstart="handleTouchStart"
             @touchmove="handleTouchMove"
             @touchend="handleTouchEnd"
             @dragstart.prevent
             @contextmenu.prevent />
      </div>

      <!-- Controls Bottom -->
    <div class="absolute bottom-6 left-1/2 -translate-x-1/2 flex items-center gap-1 px-1.5 py-1.5 bg-bg-panel border border-border-main shadow-xl select-none">
      <button @click="zoomOut" class="w-8 h-8 flex items-center justify-center active:bg-bg-active transition-colors text-text-muted hover:text-text-main" title="缩小">
        <ZoomOut class="text-xs" />
      </button>
      <span class="text-xs font-mono tabular-nums min-w-[2.5rem] text-center select-none text-text-placeholder">{{ Math.round(scale * 100) }}%</span>
      <button @click="zoomIn" class="w-8 h-8 flex items-center justify-center active:bg-bg-active transition-colors text-text-muted hover:text-text-main" title="放大">
        <ZoomIn class="text-xs" />
      </button>
      <div class="w-px h-4 bg-border-main mx-0.5"></div>
      <button @click="resetView" class="w-8 h-8 flex items-center justify-center active:bg-bg-active transition-colors text-text-muted hover:text-text-main" title="适应屏幕">
        <Expand class="text-xs" />
      </button>
      <button @click="downloadImage" class="w-8 h-8 flex items-center justify-center active:bg-bg-active transition-colors text-text-muted hover:text-text-main" title="下载">
        <Download class="text-xs" />
      </button>
      <div class="w-px h-4 bg-border-main mx-0.5"></div>
      <button @click="closePreview" class="w-8 h-8 flex items-center justify-center active:bg-bg-active transition-colors text-text-placeholder hover:text-text-main" title="关闭 (Esc)">
        <X class="text-xs" />
      </button>
    </div>
  </div>
</template>

<style scoped>
@reference "tailwindcss";

:deep(img) {
  touch-action: none;
  user-select: none;
}
</style>
