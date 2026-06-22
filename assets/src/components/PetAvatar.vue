<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue';
import { usePet } from '../composables/usePet';
import { state } from '../store';

const { currentImageUrl } = usePet();
const petRef = ref<HTMLElement | null>(null);

const PET_SIZE_KEY = 'pet_size';
const PET_POS_KEY = 'pet_pos';
const MIN_SIZE = 60;
const MAX_SIZE = 300;
const DEFAULT_SIZE = 120;
const BORDER_ZONE = 10;

const size = ref(loadSize());
const pos = ref(loadPos());
const isDragging = ref(false);
const isResizing = ref(false);
const dragOffset = ref({ x: 0, y: 0 });
const resizeStart = ref({ x: 0, y: 0, size: 0 });
const resizeEdge = ref<'se' | 's' | 'e' | null>(null);
const cursorStyle = ref('grab');
const windowWidth = ref(window.innerWidth);
const windowHeight = ref(window.innerHeight);
let lastTouchDistance = 0;

function getTouchDistance(touches: TouchList): number {
  const dx = touches[0].clientX - touches[1].clientX;
  const dy = touches[0].clientY - touches[1].clientY;
  return Math.sqrt(dx * dx + dy * dy);
}

function loadSize(): number {
  try {
    const v = localStorage.getItem(PET_SIZE_KEY);
    if (v) {
      const n = parseInt(v, 10);
      if (!isNaN(n) && n >= MIN_SIZE && n <= MAX_SIZE) return n;
    }
  } catch {}
  return DEFAULT_SIZE;
}

function saveSize() {
  localStorage.setItem(PET_SIZE_KEY, String(size.value));
}

function loadPos(): { x: number; y: number } {
  try {
    const v = localStorage.getItem(PET_POS_KEY);
    if (v) {
      const p = JSON.parse(v);
      if (typeof p.x === 'number' && typeof p.y === 'number') return p;
    }
  } catch {}
  return { x: -1, y: -1 };
}

function savePos() {
  localStorage.setItem(PET_POS_KEY, JSON.stringify(pos.value));
}

function getComputedPos() {
  if (pos.value.x >= 0 && pos.value.y >= 0) {
    const maxX = windowWidth.value - size.value;
    const maxY = windowHeight.value - size.value;
    return {
      left: Math.max(0, Math.min(maxX, pos.value.x)) + 'px',
      top: Math.max(0, Math.min(maxY, pos.value.y)) + 'px',
    };
  }
  return { right: '24px', bottom: '24px' };
}

function detectEdge(el: HTMLElement, clientX: number, clientY: number): 'se' | 's' | 'e' | null {
  const rect = el.getBoundingClientRect();
  const x = clientX - rect.left;
  const y = clientY - rect.top;
  const w = rect.width;
  const h = rect.height;
  const nearRight = x > w - BORDER_ZONE;
  const nearBottom = y > h - BORDER_ZONE;
  if (nearBottom && nearRight) return 'se';
  if (nearBottom) return 's';
  if (nearRight) return 'e';
  return null;
}

const handleElementMouseMove = (e: MouseEvent) => {
  if (isDragging.value || isResizing.value) return;
  const edge = detectEdge(e.currentTarget as HTMLElement, e.clientX, e.clientY);
  resizeEdge.value = edge;
  cursorStyle.value = edge ? `${edge}-resize` : 'grab';
};

const handleElementMouseLeave = () => {
  if (!isResizing.value) {
    resizeEdge.value = null;
    cursorStyle.value = 'grab';
  }
};

const handleMouseDown = (e: MouseEvent) => {
  if (e.button !== 0) return;
  const el = e.currentTarget as HTMLElement;
  const edge = detectEdge(el, e.clientX, e.clientY);
  if (edge) {
    isResizing.value = true;
    resizeEdge.value = edge;
    resizeStart.value = { x: e.clientX, y: e.clientY, size: size.value };
    cursorStyle.value = `${edge}-resize`;
  } else {
    isDragging.value = true;
    const rect = el.getBoundingClientRect();
    dragOffset.value = {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    };
    cursorStyle.value = 'grabbing';
  }
  e.preventDefault();
  e.stopPropagation();
};

const handleMouseMove = (e: MouseEvent) => {
  if (isDragging.value) {
    const newX = e.clientX - dragOffset.value.x;
    const newY = e.clientY - dragOffset.value.y;
    pos.value = {
      x: Math.max(0, Math.min(windowWidth.value - size.value, newX)),
      y: Math.max(0, Math.min(windowHeight.value - size.value, newY)),
    };
  } else if (isResizing.value) {
    const dx = e.clientX - resizeStart.value.x;
    const dy = e.clientY - resizeStart.value.y;
    let delta: number;
    switch (resizeEdge.value) {
      case 'se': delta = Math.max(dx, dy); break;
      case 's': delta = dy; break;
      case 'e': delta = dx; break;
      default: delta = 0;
    }
    size.value = Math.round(Math.min(MAX_SIZE, Math.max(MIN_SIZE, resizeStart.value.size + delta)));
  }
};

const handleMouseUp = () => {
  if (isDragging.value) {
    isDragging.value = false;
    cursorStyle.value = 'grab';
    savePos();
  }
  if (isResizing.value) {
    isResizing.value = false;
    resizeEdge.value = null;
    cursorStyle.value = 'grab';
    saveSize();
  }
};

const handleTouchStart = (e: TouchEvent) => {
  if (e.touches.length === 2) {
    e.preventDefault();
    lastTouchDistance = getTouchDistance(e.touches);
    isResizing.value = true;
    resizeStart.value = { x: 0, y: 0, size: size.value };
  } else if (e.touches.length === 1 && !isResizing.value) {
    isDragging.value = true;
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    dragOffset.value = {
      x: e.touches[0].clientX - rect.left,
      y: e.touches[0].clientY - rect.top,
    };
  }
};

const handleTouchMove = (e: TouchEvent) => {
  if (e.touches.length === 2 && isResizing.value) {
    e.preventDefault();
    const distance = getTouchDistance(e.touches);
    if (lastTouchDistance > 0) {
      const ratio = distance / lastTouchDistance;
      size.value = Math.round(Math.min(MAX_SIZE, Math.max(MIN_SIZE, size.value * ratio)));
    }
    lastTouchDistance = distance;
  } else if (e.touches.length === 1 && isDragging.value) {
    e.preventDefault();
    const newX = e.touches[0].clientX - dragOffset.value.x;
    const newY = e.touches[0].clientY - dragOffset.value.y;
    pos.value = {
      x: Math.max(0, Math.min(windowWidth.value - size.value, newX)),
      y: Math.max(0, Math.min(windowHeight.value - size.value, newY)),
    };
  }
};

const handleTouchEnd = (e: TouchEvent) => {
  if (e.touches.length < 2) {
    lastTouchDistance = 0;
    if (isResizing.value) {
      isResizing.value = false;
      saveSize();
    }
  }
  if (e.touches.length === 0) {
    if (isDragging.value) {
      isDragging.value = false;
      savePos();
    }
  }
};

const handleWindowResize = () => {
  windowWidth.value = window.innerWidth;
  windowHeight.value = window.innerHeight;
};

watch(petRef, (newEl, oldEl) => {
  if (oldEl) oldEl.removeEventListener('touchstart', handleTouchStart);
  if (newEl) newEl.addEventListener('touchstart', handleTouchStart, { passive: false });
});

onMounted(() => {
  document.addEventListener('mousemove', handleMouseMove);
  document.addEventListener('mouseup', handleMouseUp);
  document.addEventListener('touchmove', handleTouchMove, { passive: false });
  document.addEventListener('touchend', handleTouchEnd);
  window.addEventListener('resize', handleWindowResize);
});

onUnmounted(() => {
  document.removeEventListener('mousemove', handleMouseMove);
  document.removeEventListener('mouseup', handleMouseUp);
  document.removeEventListener('touchmove', handleTouchMove);
  document.removeEventListener('touchend', handleTouchEnd);
  window.removeEventListener('resize', handleWindowResize);
});
</script>

<template>
  <Teleport to="body">
    <div
      v-if="state.petEnabled && currentImageUrl"
      ref="petRef"
      class="pet-avatar"
      :class="{ dragging: isDragging, resizing: isResizing }"
      :style="{
        ...getComputedPos(),
        width: size + 'px',
        height: size + 'px',
        cursor: cursorStyle,
      }"
      @mousedown="handleMouseDown"
      @mousemove="handleElementMouseMove"
      @mouseleave="handleElementMouseLeave"
    >
      <img
        :src="currentImageUrl"
        class="pet-img"
        draggable="false"
      >
    </div>
  </Teleport>
</template>

<style scoped>
.pet-avatar {
  position: fixed;
  z-index: 50;
  user-select: none;
  -webkit-user-select: none;
  touch-action: none;
  -webkit-touch-callout: none;
}

.pet-avatar.dragging,
.pet-avatar.resizing {
  opacity: 0.85;
}

.pet-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  pointer-events: none;
}
</style>
