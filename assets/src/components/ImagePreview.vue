<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue';
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

const resetView = () => {
  scale.value = 1;
  translateX.value = 0;
  translateY.value = 0;
};

watch(() => state.previewImageUrl, (newUrl) => {
  if (newUrl) {
    resetView();
  }
});

const closePreview = () => {
  state.previewImageUrl = null;
};

const handleWheel = (e: WheelEvent) => {
  e.preventDefault();
  const zoomSensitivity = 0.1;
  const delta = e.deltaY > 0 ? -1 : 1;
  let newScale = scale.value + delta * zoomSensitivity;
  newScale = Math.max(0.1, Math.min(newScale, 10));
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
      newScale = Math.max(0.1, Math.min(newScale, 10));
      
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
  scale.value = Math.max(scale.value - 0.2, 0.1);
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
});

onUnmounted(() => {
  window.removeEventListener('mousemove', handleMouseMove);
  window.removeEventListener('mouseup', handleMouseUp);
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

     <!-- Close Button - Circle shape -->
     <button @click="closePreview"
             class="absolute top-4 right-4 z-10 w-10 h-10 flex items-center justify-center text-white/70 hover:text-white transition-colors rounded-full bg-white/10 hover:bg-white/20"
             title="关闭 (Esc)">
       <i class="fas fa-times text-xl"></i>
     </button>

     <!-- Image Container -->
     <div class="relative w-full h-full flex items-center justify-center overflow-hidden" @click.self="closePreview">
<img :src="state.previewImageUrl"
             alt="Preview"
             class="max-w-none max-h-none object-contain transition-transform duration-75 ease-out select-none"
             :class="isDragging ? 'cursor-grabbing' : 'cursor-grab'"
             :style="{ transform: `translate(${translateX}px, ${translateY}px) scale(${scale})` }"
             style="touch-action: none;"
             @mousedown="handleMouseDown"
             @touchstart="handleTouchStart"
             @touchmove="handleTouchMove"
             @touchend="handleTouchEnd"
             @dragstart.prevent
             @contextmenu.prevent />
      </div>

      <!-- Controls Bottom -->
    <div class="absolute bottom-6 left-1/2 -translate-x-1/2 flex items-center gap-4 px-6 py-3 bg-black/50 text-white rounded-full">
      <button @click="zoomOut" class="w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/20 transition-colors" title="缩小">
        <i class="fas fa-search-minus"></i>
      </button>
      <span class="text-sm font-mono min-w-[3rem] text-center select-none">{{ Math.round(scale * 100) }}%</span>
      <button @click="zoomIn" class="w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/20 transition-colors" title="放大">
        <i class="fas fa-search-plus"></i>
      </button>
      <div class="w-px h-4 bg-white/30 mx-1"></div>
      <button @click="resetView" class="w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/20 transition-colors" title="重置">
        <i class="fas fa-expand"></i>
      </button>
      <button @click="downloadImage" class="w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/20 transition-colors" title="下载">
        <i class="fas fa-download"></i>
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
