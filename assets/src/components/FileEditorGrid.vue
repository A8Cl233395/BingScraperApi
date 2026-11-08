<script setup lang="ts">
/**
 * 文件与图片编辑网格组件
 * 支持图片缩略图与结构化文件卡片的展示、拖拽排序、点击预览编辑、删除
 */
import { ref } from 'vue';
import { isMobileDevice } from '../utils/device';
import { useLongPress } from '../composables/useLongPress';
import { state } from '../store';
import type { UploadedFileItem } from '../composables/useImageEditor';

const props = defineProps<{
  images: string[];
  files: UploadedFileItem[];
  isProcessingImage: boolean;
  isOcrProcessing: boolean;
}>();

const emit = defineEmits<{
  removeImage: [index: number];
  removeFile: [index: number];
  reorderFile: [fromIndex: number, toIndex: number];
  updateFile: [index: number, newText: string, newName?: string];
  ocr: [index: number];
}>();

// 移动端图片长按菜单
const {
  showMenu: showImageMenu,
  menuStyle: imageMenuStyle,
  startLongPress: startImageLongPress,
  cancelLongPress: cancelImageLongPress,
  closeMenu: closeImageMenu,
} = useLongPress({ menuHeight: 100 });

const menuTargetIndex = defineModel<number>('menuTargetIndex', { default: -1 });

// 长按菜单触发时清除可能已建立的原生选区
const clearNativeSelection = () => window.getSelection()?.removeAllRanges();

const handleImageTouchStart = (e: TouchEvent, index: number) => {
  if (!isMobileDevice()) return;
  menuTargetIndex.value = index;
  startImageLongPress(e, clearNativeSelection);
};

const handleMenuImageOcr = () => {
  emit('ocr', menuTargetIndex.value);
  closeImageMenu();
};

const handleMenuImageDelete = () => {
  emit('removeImage', menuTargetIndex.value);
  closeImageMenu();
};

// 文件类型与字数格式化辅助
const AUDIO_EXTS = ['mp3', 'wav', 'ogg', 'aac', 'flac', 'm4a', 'webm'];

const getFileExt = (name: string): string => {
  const dot = name.lastIndexOf('.');
  return dot >= 0 ? name.slice(dot + 1).toLowerCase() : '';
};

const isAudio = (name: string): boolean => AUDIO_EXTS.includes(getFileExt(name));

const formatFileMeta = (item: UploadedFileItem): string => {
  if (item.status === 'converting') return '正在转换...';
  const ext = getFileExt(item.name).toUpperCase() || 'FILE';
  const len = item.text.length;
  const countStr = len >= 1000 ? `${(len / 1000).toFixed(1)}k 字` : `${len} 字`;
  return `${ext} · ${countStr}`;
};

// 点击文件卡片：打开预览并可修改内容
const handleFileClick = (index: number) => {
  if (touchDragged) return;
  const item = props.files[index];
  if (!item || item.status === 'converting') return;
  state.previewFile = {
    name: item.name,
    text: item.text,
    onSave: (newText: string, newName: string) => {
      emit('updateFile', index, newText, newName);
    },
  };
};

// ====== 桌面端 HTML5 拖拽排序 ======
const draggedIndex = ref<number | null>(null);
const dragOverIndex = ref<number | null>(null);

const handleDragStart = (e: DragEvent, index: number) => {
  const item = props.files[index];
  if (!item || item.status === 'converting') {
    e.preventDefault();
    return;
  }
  draggedIndex.value = index;
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('application/x-webchat-file', String(index));
  }
};

const handleDragOver = (e: DragEvent, index: number) => {
  if (draggedIndex.value === null) return;
  e.preventDefault();
  if (e.dataTransfer) {
    e.dataTransfer.dropEffect = 'move';
  }
  dragOverIndex.value = index;
};

const handleDragLeave = (index: number) => {
  if (dragOverIndex.value === index) {
    dragOverIndex.value = null;
  }
};

const handleDrop = (e: DragEvent, targetIndex: number) => {
  if (draggedIndex.value === null) return;
  e.preventDefault();
  e.stopPropagation();
  const fromIndex = draggedIndex.value;
  draggedIndex.value = null;
  dragOverIndex.value = null;
  if (fromIndex !== targetIndex) {
    emit('reorderFile', fromIndex, targetIndex);
  }
};

const handleDragEnd = () => {
  draggedIndex.value = null;
  dragOverIndex.value = null;
};

// ====== 触屏设备拖拽排序 ======
let touchStartX = 0;
let touchStartY = 0;
let touchDragged = false;

const handleFileTouchStart = (e: TouchEvent, index: number) => {
  const item = props.files[index];
  if (!item || item.status === 'converting' || e.touches.length !== 1) return;
  touchStartX = e.touches[0].clientX;
  touchStartY = e.touches[0].clientY;
  touchDragged = false;
  draggedIndex.value = index;
};

const handleFileTouchMove = (e: TouchEvent) => {
  if (draggedIndex.value === null || e.touches.length !== 1) return;
  const touch = e.touches[0];
  const dx = touch.clientX - touchStartX;
  const dy = touch.clientY - touchStartY;
  if (!touchDragged && Math.hypot(dx, dy) > 10) {
    touchDragged = true;
  }
  if (!touchDragged) return;

  e.preventDefault();
  const el = document.elementFromPoint(touch.clientX, touch.clientY);
  const card = el?.closest?.('[data-file-index]') as HTMLElement | null;
  if (card) {
    const overIdx = Number(card.dataset.fileIndex);
    if (!Number.isNaN(overIdx)) {
      dragOverIndex.value = overIdx;
    }
  }
};

const handleFileTouchEnd = () => {
  if (touchDragged && draggedIndex.value !== null && dragOverIndex.value !== null && draggedIndex.value !== dragOverIndex.value) {
    emit('reorderFile', draggedIndex.value, dragOverIndex.value);
  }
  draggedIndex.value = null;
  dragOverIndex.value = null;
  setTimeout(() => {
    touchDragged = false;
  }, 50);
};
</script>

<template>
  <div v-if="images.length > 0 || files.length > 0 || isProcessingImage" class="flex flex-wrap gap-2 mb-2">
    <!-- 图片缩略图 -->
    <div
      v-for="(img, index) in images"
      :key="'img-' + index"
      class="relative group w-14 h-14 overflow-hidden border border-border-main shrink-0"
      :class="isMobileDevice() ? 'user-select-none' : ''"
    >
      <img
        :src="img"
        class="w-full h-full object-cover cursor-pointer"
        @click="state.previewImageUrl = img"
        @touchstart="handleImageTouchStart($event, index)"
        @touchend="cancelImageLongPress"
        @touchmove="cancelImageLongPress"
        @touchcancel="cancelImageLongPress"
        @contextmenu="isMobileDevice() ? $event.preventDefault() : null"
      />
      <div v-if="isOcrProcessing && isMobileDevice()" class="absolute inset-0 bg-black/50 flex items-center justify-center z-10">
        <Loader2 class="animate-spin text-white text-sm" />
      </div>
      <button
        v-if="!isMobileDevice()"
        @click="emit('removeImage', index)"
        @mousedown.prevent
        class="absolute top-0 right-0 bg-black/60 text-white w-5 h-5 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
        title="删除图片"
      >
        <X class="text-[10px]" />
      </button>
      <button
        v-if="!isMobileDevice()"
        @click="emit('ocr', index)"
        @mousedown.prevent
        class="absolute bottom-0 right-0 bg-black/60 text-white w-5 h-5 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-0"
        :disabled="isOcrProcessing"
        title="识别文字转为文件"
      >
        <Loader2 v-if="isOcrProcessing" class="animate-spin text-[10px]" />
        <FileText v-else class="text-[10px]" />
      </button>
    </div>

    <!-- 结构化文件卡片（支持拖拽调整顺序、点击预览与编辑、删除） -->
    <div
      v-for="(item, index) in files"
      :key="item.id || ('file-' + index)"
      :data-file-index="index"
      :draggable="item.status !== 'converting'"
      class="file-card relative group flex items-center gap-2.5 px-2.5 h-14 w-48 border bg-bg-panel select-none transition-colors shrink-0"
      :class="[
        item.status === 'converting' ? 'cursor-wait opacity-80 border-border-main' : 'cursor-pointer',
        draggedIndex === index ? 'opacity-45' : '',
        dragOverIndex === index && draggedIndex !== index ? 'border-primary-main bg-bg-hover' : 'border-border-main',
      ]"
      :title="item.status === 'converting' ? '正在转换文件内容...' : `${item.name}（点击预览/修改，拖拽调整顺序）`"
      @click="handleFileClick(index)"
      @dragstart="handleDragStart($event, index)"
      @dragover="handleDragOver($event, index)"
      @dragleave="handleDragLeave(index)"
      @drop="handleDrop($event, index)"
      @dragend="handleDragEnd"
      @touchstart="handleFileTouchStart($event, index)"
      @touchmove="handleFileTouchMove"
      @touchend="handleFileTouchEnd"
      @touchcancel="handleFileTouchEnd"
    >
      <!-- 左侧文件类型角标框 -->
      <div class="w-8 h-8 border border-border-main bg-bg-hover flex items-center justify-center shrink-0">
        <Loader2 v-if="item.status === 'converting'" class="animate-spin text-primary-main text-sm" />
        <Music v-else-if="isAudio(item.name)" class="text-sm text-primary-main" />
        <FileText v-else class="text-sm text-primary-main" />
      </div>

      <!-- 中部文件名与元信息 -->
      <div class="flex-1 min-w-0 pr-3">
        <div class="text-xs font-medium text-text-main truncate leading-tight">{{ item.name }}</div>
        <div
          class="text-[10px] font-mono mt-1 truncate leading-none"
          :class="item.status === 'converting' ? 'text-primary-main' : 'text-text-placeholder'"
        >
          {{ formatFileMeta(item) }}
        </div>
      </div>

      <!-- 右上角删除按钮 -->
      <button
        @click.stop="emit('removeFile', index)"
        @mousedown.prevent
        class="
          absolute top-1 right-1 w-4 h-4 flex items-center justify-center
          text-text-placeholder hover:text-danger-main transition-opacity
        "
        :class="isMobileDevice() ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'"
        title="删除文件"
      >
        <X class="text-[11px]" />
      </button>
    </div>

    <!-- 图片处理中占位符 -->
    <div v-if="isProcessingImage" class="w-14 h-14 border border-dashed border-border-main flex items-center justify-center bg-bg-hover shrink-0">
      <Loader2 class="animate-spin text-text-placeholder" />
    </div>
  </div>

  <!-- 移动端图片长按菜单 -->
  <Teleport to="body">
    <div v-if="showImageMenu" class="fixed inset-0 z-1100" @click="closeImageMenu" @contextmenu.prevent>
      <div class="fixed inset-0 bg-black/5"></div>
      <div
        class="absolute bg-bg-panel border border-border-main shadow-xl overflow-hidden animate-in fade-in zoom-in duration-150 py-1"
        :style="imageMenuStyle"
        @click.stop
      >
        <button @click="handleMenuImageOcr" :disabled="isOcrProcessing" class="w-full flex items-center gap-3 px-3 py-2 transition-colors text-text-main text-sm disabled:opacity-50">
          <Loader2 v-if="isOcrProcessing" class="animate-spin min-w-4 text-center text-text-muted" />
          <FileText v-else class="min-w-4 text-center text-text-muted" />
          <span>{{ isOcrProcessing ? '识别中...' : '识别文字' }}</span>
        </button>
        <button @click="handleMenuImageDelete" class="w-full flex items-center gap-3 px-3 py-2 transition-colors text-text-main text-sm">
          <X class="min-w-4 text-center text-text-muted" />
          <span>删除</span>
        </button>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* 移动端长按区域禁用原生文本选择（Chromium/WebView 需保留 -webkit- 前缀） */
.user-select-none {
  -webkit-user-select: none !important;
  user-select: none !important;
}

/* 文件卡片左侧 2px 主色装饰条，强化"这是一个文件附件"的视觉识别 */
.file-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 2px;
  background: var(--primary);
}
</style>
