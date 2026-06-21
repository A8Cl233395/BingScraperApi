<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { usePet } from '../composables/usePet';
import { state } from '../store';

const { currentImageUrl } = usePet();

const PET_SIZE_KEY = 'pet_size';
const PET_POS_KEY = 'pet_pos';
const MIN_SIZE = 60;
const MAX_SIZE = 300;
const DEFAULT_SIZE = 120;

const size = ref(loadSize());
const pos = ref(loadPos());
const isDragging = ref(false);
const isResizing = ref(false);
const dragOffset = ref({ x: 0, y: 0 });
const resizeStart = ref({ x: 0, y: 0, size: 0 });

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
    return { left: pos.value.x + 'px', top: pos.value.y + 'px' };
  }
  return { right: '24px', bottom: '24px' };
}

const handleMouseDown = (e: MouseEvent) => {
  if (e.button !== 0 || isResizing.value) return;
  isDragging.value = true;
  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
  dragOffset.value = {
    x: e.clientX - rect.left,
    y: e.clientY - rect.top,
  };
  e.preventDefault();
  e.stopPropagation();
};

const handleResizeStart = (e: MouseEvent) => {
  if (e.button !== 0) return;
  isResizing.value = true;
  resizeStart.value = {
    x: e.clientX,
    y: e.clientY,
    size: size.value,
  };
  e.preventDefault();
  e.stopPropagation();
};

const handleMouseMove = (e: MouseEvent) => {
  if (isDragging.value) {
    const newX = e.clientX - dragOffset.value.x;
    const newY = e.clientY - dragOffset.value.y;
    pos.value = {
      x: Math.max(0, Math.min(window.innerWidth - size.value, newX)),
      y: Math.max(0, Math.min(window.innerHeight - size.value, newY)),
    };
  } else if (isResizing.value) {
    const dx = e.clientX - resizeStart.value.x;
    const dy = e.clientY - resizeStart.value.y;
    const delta = Math.max(dx, dy);
    const newSize = Math.round(Math.min(MAX_SIZE, Math.max(MIN_SIZE, resizeStart.value.size + delta)));
    size.value = newSize;
  }
};

const handleMouseUp = () => {
  if (isDragging.value) {
    isDragging.value = false;
    savePos();
  }
  if (isResizing.value) {
    isResizing.value = false;
    saveSize();
  }
};

onMounted(() => {
  document.addEventListener('mousemove', handleMouseMove);
  document.addEventListener('mouseup', handleMouseUp);
});

onUnmounted(() => {
  document.removeEventListener('mousemove', handleMouseMove);
  document.removeEventListener('mouseup', handleMouseUp);
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
      }"
      @mousedown="handleMouseDown"
    >
      <img
        :src="currentImageUrl"
        class="pet-img"
        draggable="false"
      >
      <div
        class="resize-handle"
        @mousedown="handleResizeStart"
      >
        <svg viewBox="0 0 10 10" fill="none">
          <path d="M9 1L1 9M9 5L5 9M9 9L9 9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.pet-avatar {
  position: fixed;
  z-index: 50;
  cursor: grab;
  user-select: none;
}

.pet-avatar.dragging {
  cursor: grabbing;
  opacity: 0.85;
}

.pet-avatar.resizing {
  opacity: 0.85;
}

.pet-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  pointer-events: none;
}

.resize-handle {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 20px;
  height: 20px;
  cursor: se-resize;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.pet-avatar:hover .resize-handle {
  opacity: 0.7;
}

.resize-handle:hover {
  opacity: 1 !important;
}

.resize-handle svg {
  width: 10px;
  height: 10px;
  color: white;
  filter: drop-shadow(0 0 2px rgba(0, 0, 0, 0.5));
}
</style>
