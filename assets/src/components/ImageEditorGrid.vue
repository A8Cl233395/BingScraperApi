<script setup lang="ts">
/**
 * 图片编辑网格组件
 * 从 ChatInput 和 MessageBubble 中提取的共享模板，包含：
 * - 图片缩略图预览（点击放大）
 * - 桌面端 hover 显示删除/OCR 按钮
 * - 移动端长按显示操作菜单
 * - 图片处理中的加载占位符
 */
import { isMobileDevice } from '../utils/device';
import { useLongPress } from '../composables/useLongPress';
import { state } from '../store';

const props = defineProps<{
  images: string[];
  isProcessingImage: boolean;
  isOcrProcessing: boolean;
}>();

const emit = defineEmits<{
  remove: [index: number];
  ocr: [index: number];
}>();

// 移动端长按菜单
const {
  showMenu: showImageMenu,
  menuStyle: imageMenuStyle,
  startLongPress: startImageLongPress,
  cancelLongPress: cancelImageLongPress,
  closeMenu: closeImageMenu,
} = useLongPress({ menuHeight: 100 });

const menuTargetIndex = defineModel<number>('menuTargetIndex', { default: -1 });

const handleTouchStart = (e: TouchEvent, index: number) => {
  if (!isMobileDevice()) return;
  menuTargetIndex.value = index;
  startImageLongPress(e);
};

const handleMenuOcr = () => {
  emit('ocr', menuTargetIndex.value);
  closeImageMenu();
};

const handleMenuDelete = () => {
  emit('remove', menuTargetIndex.value);
  closeImageMenu();
};
</script>

<template>
  <!-- 图片预览网格 -->
  <div v-if="images.length > 0 || isProcessingImage" class="flex flex-wrap gap-2 mb-2">
    <div v-for="(img, index) in images" :key="index" class="relative group w-16 h-16 rounded-md overflow-hidden border border-border-main">
      <img :src="img" class="w-full h-full object-cover cursor-pointer"
        @click="state.previewImageUrl = img"
        @touchstart="handleTouchStart($event, index)"
        @touchend="cancelImageLongPress"
        @touchmove="cancelImageLongPress"
        @touchcancel="cancelImageLongPress"
        @contextmenu.prevent
      />
      <!-- 移动端 OCR 加载遮罩 -->
      <div v-if="isOcrProcessing && isMobileDevice()" class="absolute inset-0 bg-black/50 flex items-center justify-center z-10">
        <FontAwesomeIcon :icon="['fas', 'spinner']" spin class="text-white text-sm" />
      </div>
      <button 
        v-if="!isMobileDevice()"
        @click="emit('remove', index)"
        @mousedown.prevent
        class="absolute top-0 right-0 bg-black/50 text-white w-5 h-5 flex items-center justify-center rounded-bl-md opacity-0 group-hover:opacity-100 transition-opacity"
      >
        <FontAwesomeIcon :icon="['fas', 'xmark']" class="text-[10px]" />
      </button>
      <button 
        v-if="!isMobileDevice()"
        @click="emit('ocr', index)"
        @mousedown.prevent
        class="absolute bottom-0 right-0 bg-black/50 text-white w-5 h-5 flex items-center justify-center rounded-tl-md opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-0"
        :disabled="isOcrProcessing"
        title="识别文字"
      >
        <FontAwesomeIcon v-if="isOcrProcessing" :icon="['fas', 'spinner']" spin class="text-[10px]" />
        <FontAwesomeIcon v-else :icon="['fas', 'file-lines']" class="text-[10px]" />
      </button>
    </div>
    <div v-if="isProcessingImage" class="w-16 h-16 rounded-md border border-dashed border-border-main flex items-center justify-center bg-bg-hover">
      <FontAwesomeIcon :icon="['fas', 'spinner']" spin class="text-text-placeholder" />
    </div>
    <span v-if="images.length > 0 && isMobileDevice()" class="text-[10px] text-text-placeholder self-center ml-1">长按操作</span>
  </div>

  <!-- 移动端图片长按菜单 -->
  <Teleport to="body">
    <div v-if="showImageMenu" class="fixed inset-0 z-1100" @click="closeImageMenu" @contextmenu.prevent>
      <div class="fixed inset-0 bg-black/5"></div>
      <div 
        class="absolute bg-bg-panel border border-border-main rounded-lg shadow-xl overflow-hidden animate-in fade-in zoom-in duration-150 py-1" 
        :style="imageMenuStyle"
        @click.stop
      >
        <button @click="handleMenuOcr" :disabled="isOcrProcessing" class="w-full flex items-center gap-3 px-3 py-2 hover:bg-bg-hover transition-colors text-text-main text-sm disabled:opacity-50">
          <FontAwesomeIcon v-if="isOcrProcessing" :icon="['fas', 'spinner']" spin class="w-4 text-center text-text-muted" />
          <FontAwesomeIcon v-else :icon="['fas', 'file-lines']" class="w-4 text-center text-text-muted" />
          <span>{{ isOcrProcessing ? '识别中...' : '识别文字' }}</span>
        </button>
        <button @click="handleMenuDelete" class="w-full flex items-center gap-3 px-3 py-2 hover:bg-bg-hover transition-colors text-text-main text-sm">
          <FontAwesomeIcon :icon="['fas', 'xmark']" class="w-4 text-center text-text-muted" />
          <span>删除</span>
        </button>
      </div>
    </div>
  </Teleport>
</template>
