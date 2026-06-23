<script setup lang="ts">
/**
 * 文件编辑网格组件
 * 支持图片、音频、其他文件预览和操作
 * - 图片缩略图预览（点击放大）
 * - 音频文件显示音乐图标
 * - 其他文件显示文件名和文档图标
 * - 桌面端 hover 显示删除/转换按钮
 * - 移动端长按显示操作菜单
 */
import { isMobileDevice } from '../utils/device';
import { useLongPress } from '../composables/useLongPress';
import { state } from '../store';

interface FileItem {
  type: 'audio' | 'file';
  data: ArrayBuffer;
  textContent: string;
  originalName: string;
  format: string;
  supported: boolean;
  isTextFile: boolean;
}

const props = defineProps<{
  images: string[];
  audioFiles: FileItem[];
  otherFiles: FileItem[];
  isProcessingImage: boolean;
  isOcrProcessing: boolean;
  isConverting: boolean;
}>();

const emit = defineEmits<{
  removeImage: [index: number];
  removeAudio: [index: number];
  removeOther: [index: number];
  ocr: [index: number];
  convertAudio: [index: number];
  convertFile: [index: number];
}>();

// 移动端长按菜单
const {
  showMenu: showImageMenu,
  menuStyle: imageMenuStyle,
  startLongPress: startImageLongPress,
  cancelLongPress: cancelImageLongPress,
  closeMenu: closeImageMenu,
} = useLongPress({ menuHeight: 100 });

const {
  showMenu: showAudioMenu,
  menuStyle: audioMenuStyle,
  startLongPress: startAudioLongPress,
  cancelLongPress: cancelAudioLongPress,
  closeMenu: closeAudioMenu,
} = useLongPress({ menuHeight: 100 });

const {
  showMenu: showFileMenu,
  menuStyle: fileMenuStyle,
  startLongPress: startFileLongPress,
  cancelLongPress: cancelFileLongPress,
  closeMenu: closeFileMenu,
} = useLongPress({ menuHeight: 100 });

const menuTargetIndex = defineModel<number>('menuTargetIndex', { default: -1 });

// 图片长按处理
const handleImageTouchStart = (e: TouchEvent, index: number) => {
  if (!isMobileDevice()) return;
  menuTargetIndex.value = index;
  startImageLongPress(e);
};

const handleMenuImageOcr = () => {
  emit('ocr', menuTargetIndex.value);
  closeImageMenu();
};

const handleMenuImageDelete = () => {
  emit('removeImage', menuTargetIndex.value);
  closeImageMenu();
};

// 音频长按处理
const handleAudioTouchStart = (e: TouchEvent, index: number) => {
  if (!isMobileDevice()) return;
  menuTargetIndex.value = index;
  startAudioLongPress(e);
};

const handleMenuAudioConvert = () => {
  emit('convertAudio', menuTargetIndex.value);
  closeAudioMenu();
};

const handleMenuAudioDelete = () => {
  emit('removeAudio', menuTargetIndex.value);
  closeAudioMenu();
};

// 文件长按处理
const handleFileTouchStart = (e: TouchEvent, index: number) => {
  if (!isMobileDevice()) return;
  menuTargetIndex.value = index;
  startFileLongPress(e);
};

const handleMenuFileConvert = () => {
  emit('convertFile', menuTargetIndex.value);
  closeFileMenu();
};

const handleMenuFileDelete = () => {
  emit('removeOther', menuTargetIndex.value);
  closeFileMenu();
};
</script>

<template>
  <!-- 图片预览网格 -->
  <div v-if="images.length > 0 || audioFiles.length > 0 || otherFiles.length > 0 || isProcessingImage" class="flex flex-wrap gap-2 mb-2">
    <!-- 图片 -->
    <div v-for="(img, index) in images" :key="'img-' + index" class="relative group w-16 h-16 rounded-md overflow-hidden border border-border-main">
      <img :src="img" class="w-full h-full object-cover cursor-pointer"
        @click="state.previewImageUrl = img"
        @touchstart="handleImageTouchStart($event, index)"
        @touchend="cancelImageLongPress"
        @touchmove="cancelImageLongPress"
        @touchcancel="cancelImageLongPress"
        @contextmenu="isMobileDevice() ? $event.preventDefault() : null"
      />
      <div v-if="isOcrProcessing && isMobileDevice()" class="absolute inset-0 bg-black/50 flex items-center justify-center z-10">
        <FontAwesomeIcon :icon="['fas', 'spinner']" spin class="text-white text-sm" />
      </div>
      <button 
        v-if="!isMobileDevice()"
        @click="emit('removeImage', index)"
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

    <!-- 音频文件 -->
    <div v-for="(item, index) in audioFiles" :key="'audio-' + index" class="relative group w-16 h-16 rounded-md border border-border-main flex flex-col items-center justify-center bg-bg-hover cursor-default"
      @touchstart="handleAudioTouchStart($event, index)"
      @touchend="cancelAudioLongPress"
      @touchmove="cancelAudioLongPress"
      @touchcancel="cancelAudioLongPress"
      @contextmenu="isMobileDevice() ? $event.preventDefault() : null"
    >
      <FontAwesomeIcon :icon="['fas', 'music']" class="text-lg text-text-muted" />
      <span class="text-[9px] text-text-placeholder mt-0.5 px-1 truncate w-full text-center">{{ item.originalName }}</span>
      <div v-if="isConverting && isMobileDevice()" class="absolute inset-0 bg-black/50 flex items-center justify-center z-10">
        <FontAwesomeIcon :icon="['fas', 'spinner']" spin class="text-white text-sm" />
      </div>
      <button 
        v-if="!isMobileDevice()"
        @click="emit('removeAudio', index)"
        @mousedown.prevent
        class="absolute top-0 right-0 bg-black/50 text-white w-5 h-5 flex items-center justify-center rounded-bl-md opacity-0 group-hover:opacity-100 transition-opacity"
      >
        <FontAwesomeIcon :icon="['fas', 'xmark']" class="text-[10px]" />
      </button>
      <button 
        v-if="!isMobileDevice()"
        @click="emit('convertAudio', index)"
        @mousedown.prevent
        class="absolute bottom-0 right-0 bg-black/50 text-white w-5 h-5 flex items-center justify-center rounded-tl-md opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-0"
        :disabled="isConverting"
        title="转文字"
      >
        <FontAwesomeIcon v-if="isConverting" :icon="['fas', 'spinner']" spin class="text-[10px]" />
        <FontAwesomeIcon v-else :icon="['fas', 'file-lines']" class="text-[10px]" />
      </button>
    </div>

    <!-- 其他文件 -->
    <div v-for="(item, index) in otherFiles" :key="'file-' + index" class="relative group w-16 h-16 rounded-md border border-border-main flex flex-col items-center justify-center bg-bg-hover cursor-default"
      @touchstart="handleFileTouchStart($event, index)"
      @touchend="cancelFileLongPress"
      @touchmove="cancelFileLongPress"
      @touchcancel="cancelFileLongPress"
      @contextmenu="isMobileDevice() ? $event.preventDefault() : null"
    >
      <FontAwesomeIcon :icon="['fas', 'file']" class="text-lg text-text-muted" />
      <span class="text-[9px] text-text-placeholder mt-0.5 px-1 truncate w-full text-center">{{ item.originalName }}</span>
      <div v-if="isConverting && isMobileDevice()" class="absolute inset-0 bg-black/50 flex items-center justify-center z-10">
        <FontAwesomeIcon :icon="['fas', 'spinner']" spin class="text-white text-sm" />
      </div>
      <button 
        v-if="!isMobileDevice()"
        @click="emit('removeOther', index)"
        @mousedown.prevent
        class="absolute top-0 right-0 bg-black/50 text-white w-5 h-5 flex items-center justify-center rounded-bl-md opacity-0 group-hover:opacity-100 transition-opacity"
      >
        <FontAwesomeIcon :icon="['fas', 'xmark']" class="text-[10px]" />
      </button>
      <button 
        v-if="!isMobileDevice()"
        @click="emit('convertFile', index)"
        @mousedown.prevent
        class="absolute bottom-0 right-0 bg-black/50 text-white w-5 h-5 flex items-center justify-center rounded-tl-md opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-0"
        :disabled="isConverting"
        title="转文字"
      >
        <FontAwesomeIcon v-if="isConverting" :icon="['fas', 'spinner']" spin class="text-[10px]" />
        <FontAwesomeIcon v-else :icon="['fas', 'file-lines']" class="text-[10px]" />
      </button>
    </div>

    <!-- 处理中占位符 -->
    <div v-if="isProcessingImage" class="w-16 h-16 rounded-md border border-dashed border-border-main flex items-center justify-center bg-bg-hover">
      <FontAwesomeIcon :icon="['fas', 'spinner']" spin class="text-text-placeholder" />
    </div>
    <span v-if="(images.length > 0 || audioFiles.length > 0 || otherFiles.length > 0) && isMobileDevice()" class="text-[10px] text-text-placeholder self-center ml-1">长按操作</span>
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
        <button @click="handleMenuImageOcr" :disabled="isOcrProcessing" class="w-full flex items-center gap-3 px-3 py-2 hover:bg-bg-hover transition-colors text-text-main text-sm disabled:opacity-50">
          <FontAwesomeIcon v-if="isOcrProcessing" :icon="['fas', 'spinner']" spin class="w-4 text-center text-text-muted" />
          <FontAwesomeIcon v-else :icon="['fas', 'file-lines']" class="w-4 text-center text-text-muted" />
          <span>{{ isOcrProcessing ? '识别中...' : '识别文字' }}</span>
        </button>
        <button @click="handleMenuImageDelete" class="w-full flex items-center gap-3 px-3 py-2 hover:bg-bg-hover transition-colors text-text-main text-sm">
          <FontAwesomeIcon :icon="['fas', 'xmark']" class="w-4 text-center text-text-muted" />
          <span>删除</span>
        </button>
      </div>
    </div>
  </Teleport>

  <!-- 移动端音频长按菜单 -->
  <Teleport to="body">
    <div v-if="showAudioMenu" class="fixed inset-0 z-1100" @click="closeAudioMenu" @contextmenu.prevent>
      <div class="fixed inset-0 bg-black/5"></div>
      <div 
        class="absolute bg-bg-panel border border-border-main rounded-lg shadow-xl overflow-hidden animate-in fade-in zoom-in duration-150 py-1" 
        :style="audioMenuStyle"
        @click.stop
      >
        <button @click="handleMenuAudioConvert" :disabled="isConverting" class="w-full flex items-center gap-3 px-3 py-2 hover:bg-bg-hover transition-colors text-text-main text-sm disabled:opacity-50">
          <FontAwesomeIcon v-if="isConverting" :icon="['fas', 'spinner']" spin class="w-4 text-center text-text-muted" />
          <FontAwesomeIcon v-else :icon="['fas', 'file-lines']" class="w-4 text-center text-text-muted" />
          <span>{{ isConverting ? '转换中...' : '转文字' }}</span>
        </button>
        <button @click="handleMenuAudioDelete" class="w-full flex items-center gap-3 px-3 py-2 hover:bg-bg-hover transition-colors text-text-main text-sm">
          <FontAwesomeIcon :icon="['fas', 'xmark']" class="w-4 text-center text-text-muted" />
          <span>删除</span>
        </button>
      </div>
    </div>
  </Teleport>

  <!-- 移动端文件长按菜单 -->
  <Teleport to="body">
    <div v-if="showFileMenu" class="fixed inset-0 z-1100" @click="closeFileMenu" @contextmenu.prevent>
      <div class="fixed inset-0 bg-black/5"></div>
      <div 
        class="absolute bg-bg-panel border border-border-main rounded-lg shadow-xl overflow-hidden animate-in fade-in zoom-in duration-150 py-1" 
        :style="fileMenuStyle"
        @click.stop
      >
        <button @click="handleMenuFileConvert" :disabled="isConverting" class="w-full flex items-center gap-3 px-3 py-2 hover:bg-bg-hover transition-colors text-text-main text-sm disabled:opacity-50">
          <FontAwesomeIcon v-if="isConverting" :icon="['fas', 'spinner']" spin class="w-4 text-center text-text-muted" />
          <FontAwesomeIcon v-else :icon="['fas', 'file-lines']" class="w-4 text-center text-text-muted" />
          <span>{{ isConverting ? '转换中...' : '转文字' }}</span>
        </button>
        <button @click="handleMenuFileDelete" class="w-full flex items-center gap-3 px-3 py-2 hover:bg-bg-hover transition-colors text-text-main text-sm">
          <FontAwesomeIcon :icon="['fas', 'xmark']" class="w-4 text-center text-text-muted" />
          <span>删除</span>
        </button>
      </div>
    </div>
  </Teleport>
</template>
