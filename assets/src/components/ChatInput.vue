<script setup lang="ts">
import { state } from '../store';
import { ref, watch, nextTick, onUnmounted } from 'vue';
import { processImage } from '../utils/image';
import api from '../utils/api';
import { isMobileDevice } from '../utils/device';


const props = defineProps<{
  isChatStarted: boolean;
}>();

const emit = defineEmits(['send', 'mobile-focus', 'mobile-blur']);

const textInput = ref('');
const images = ref<string[]>([]);
const fileInput = ref<HTMLInputElement | null>(null);
const showOptions = ref(false);
const textareaRef = ref<HTMLTextAreaElement | null>(null);
const isProcessingImage = ref(false);

const adjustHeight = () => {
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto';
    textareaRef.value.style.height = Math.min(textareaRef.value.scrollHeight, 200) + 'px';
  }
};

watch(textInput, () => {
  nextTick(adjustHeight);
});

const handleSend = () => {
  if (state.isStreaming) return;
  if (textInput.value.trim() || images.value.length > 0) {
    const content = [];
    // Images before text
    images.value.forEach(url => {
      content.push({ type: 'image_url', image_url: { url } });
    });
    if (textInput.value.trim()) {
      content.push({ type: 'text', text: textInput.value.trim() });
    }

    emit('send', content);
    textInput.value = '';
    images.value = [];
    if (isMobileDevice()) {
      textareaRef.value?.blur();
    }
    nextTick(adjustHeight);
  }
};

const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Enter') {
    if (!isMobileDevice() && !e.ctrlKey && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    } else if (e.ctrlKey) {
      e.preventDefault();
      const start = textareaRef.value!.selectionStart;
      const end = textareaRef.value!.selectionEnd;
      textInput.value = textInput.value.substring(0, start) + '\n' + textInput.value.substring(end);
      nextTick(() => {
        textareaRef.value!.selectionStart = textareaRef.value!.selectionEnd = start + 1;
        adjustHeight();
      });
    }
  }
};

const handleFileUpload = async (e: Event) => {
  const files = (e.target as HTMLInputElement).files;
  if (files) {
    await addFiles(Array.from(files));
  }
};

const addFiles = async (files: File[]) => {
  isProcessingImage.value = true;
  try {
    for (const file of files) {
      if (images.value.length >= 10) break;
      const isImage = file.type.startsWith('image/') || 
                      file.name.toLowerCase().endsWith('.heic') || 
                      file.name.toLowerCase().endsWith('.heif');
      
      if (isImage) {
        try {
          const base64 = await processImage(file);
          images.value.push(base64);
        } catch (error) {
          console.error('Failed to process image:', error);
          alert('图片处理失败，请稍后重试');
        }
      }
    }
  } finally {
    isProcessingImage.value = false;
  }
};

const handlePaste = async (e: ClipboardEvent) => {
  const items = e.clipboardData?.items;
  if (items) {
    const files = [];
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.indexOf('image') !== -1) {
        const file = items[i].getAsFile();
        if (file) files.push(file);
      }
    }
    await addFiles(files);
  }
};

const handleDrop = async (e: DragEvent) => {
  e.preventDefault();
  const files = e.dataTransfer?.files;
  if (files) {
    await addFiles(Array.from(files));
  }
};

const removeImage = (index: number) => {
  images.value.splice(index, 1);
};

let blurTimeout: any = null;

const handleFocus = () => {
  if (blurTimeout) {
    clearTimeout(blurTimeout);
    blurTimeout = null;
  }
  if (isMobileDevice()) {
    emit('mobile-focus');
    window.scrollTo(0, 0);
    nextTick(() => {
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
    });
  }
};

const handleBlur = () => {
  if (isMobileDevice()) {
    blurTimeout = setTimeout(() => {
      emit('mobile-blur');
      blurTimeout = null;
    }, 200);
  }
};

onUnmounted(() => {
  if (blurTimeout) clearTimeout(blurTimeout);
});

const setDefaultOption = async (type: 'thinking' | 'enable_function', value: boolean) => {
  try {
    const payload: any = {};
    if (type === 'thinking') {
      payload.thinking = value;
      state.defaultSettings.thinking = value;
      state.isThinking = value;
    } else {
      payload.enable_function = value;
      state.defaultSettings.enable_function = value;
      state.isEnableFunction = value;
    }
    await api.post('/api/default', payload);
  } catch (e) {
    console.error('Failed to set default option', e);
  }
  showOptions.value = false;
};
</script>

<template>
  <div 
    class="w-full max-w-4xl mx-auto px-4 layout-transition flex flex-col shrink-0 pb-6 pt-2"
  >
    <div 
      class="transition-all duration-500 ease-in-out overflow-hidden flex flex-col justify-end" 
      :class="props.isChatStarted ? 'opacity-0 max-h-0 mb-0' : 'opacity-100 max-h-20 mb-8'"
    >
      <h1 class="text-2xl font-semibold text-center text-text-main tracking-wide">
        有什么我可以帮您的？
      </h1>
    </div>

    <div 
      class="border border-border-input rounded-lg p-3 flex flex-col focus-within:border-text-muted transition-colors bg-bg-main shadow-[0_2px_10px_rgba(0,0,0,0.05)]"
      @paste="handlePaste"
      @drop="handleDrop"
      @dragover.prevent
    >
      <!-- Image Previews -->
      <div v-if="images.length > 0 || isProcessingImage" class="flex flex-wrap gap-2 mb-2">
        <div v-for="(img, index) in images" :key="index" class="relative group w-16 h-16 rounded-md overflow-hidden border border-border-main">
          <img :src="img" class="w-full h-full object-cover" />
          <button 
            @click="removeImage(index)"
            @mousedown.prevent
            class="absolute top-0 right-0 bg-black/50 text-white w-5 h-5 flex items-center justify-center rounded-bl-md opacity-0 group-hover:opacity-100 transition-opacity"
          >
            <FontAwesomeIcon :icon="['fas', 'xmark']" class="text-[10px]" />
          </button>
        </div>
        <div v-if="isProcessingImage" class="w-16 h-16 rounded-md border border-dashed border-border-main flex items-center justify-center bg-bg-hover">
          <FontAwesomeIcon :icon="['fas', 'spinner']" spin class="text-text-placeholder" />
        </div>
      </div>

      <textarea 
        ref="textareaRef"
        v-model="textInput"
        rows="1" 
        class="w-full resize-none outline-none border-none bg-transparent p-1 text-sm no-scrollbar text-text-main placeholder-text-placeholder min-h-[24px]"
        :placeholder="isMobileDevice() ? '输入消息...' : '输入消息，Shift+Enter 或 Ctrl+Enter 换行，Enter 发送...'"
        @keydown="handleKeydown"
        @focus="handleFocus"
        @blur="handleBlur"
      ></textarea>
    </div>

    <!-- Toggles and Options -->
    <div class="flex items-center justify-between mt-3 ml-1">
      <div class="flex items-center gap-2">
        <button 
          @click="state.isThinking = !state.isThinking"
          @mousedown.prevent
          class="flex items-center gap-1.5 px-3 py-1.5 border border-border-input rounded-md text-xs hover:bg-bg-hover transition-colors"
          :class="state.isThinking ? 'bg-primary-main text-primary-text border-primary-main hover:bg-primary-hover' : 'bg-bg-main text-text-muted'"
        >
          <FontAwesomeIcon :icon="['fas', 'brain']" :class="state.isThinking ? 'text-primary-text' : 'text-text-placeholder'" />
          深度思考
        </button>
        <button 
          @click="state.isEnableFunction = !state.isEnableFunction"
          @mousedown.prevent
          class="flex items-center gap-1.5 px-3 py-1.5 border border-border-input rounded-md text-xs hover:bg-bg-hover transition-colors"
          :class="state.isEnableFunction ? 'bg-primary-main text-primary-text border-primary-main hover:bg-primary-hover' : 'bg-bg-main text-text-muted'"
        >
          <FontAwesomeIcon :icon="['fas', 'wrench']" :class="state.isEnableFunction ? 'text-primary-text' : 'text-text-placeholder'" />
          使用工具
        </button>
        <div class="relative">
          <button 
            @click="showOptions = !showOptions"
            @mousedown.prevent
            class="w-8 h-8 flex items-center justify-center border border-border-input rounded-md text-text-placeholder hover:bg-bg-hover transition-colors" 
            title="默认选项"
          >
            <FontAwesomeIcon
              :icon="['fas', props.isChatStarted ? 'chevron-up' : 'chevron-down']"
              class="text-xs transition-transform"
              :class="showOptions ? 'rotate-180' : ''"
            />
          </button>

          <transition
            @enter="(el: any) => { el.style.transition = 'none'; el.style.height = '0px'; el.style.opacity = '0'; el.offsetHeight; el.style.transition = 'height 0.25s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.25s cubic-bezier(0.4, 0, 0.2, 1)'; el.style.height = el.scrollHeight + 'px'; el.style.opacity = '1'; }"
            @after-enter="(el: any) => { el.style.transition = ''; el.style.height = 'auto'; }"
            @leave="(el: any) => { el.style.transition = 'none'; el.style.height = el.scrollHeight + 'px'; el.style.opacity = '1'; el.offsetHeight; el.style.transition = 'height 0.25s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.25s cubic-bezier(0.4, 0, 0.2, 1)'; el.style.height = '0px'; el.style.opacity = '0'; }"
            @after-leave="(el: any) => { el.style.transition = ''; }"
          >
            <!-- Default Options Popup -->
            <div 
              v-if="showOptions"
              class="absolute left-0 w-48 bg-bg-main border border-border-main rounded-lg shadow-xl z-50 p-1 overflow-hidden"
              :class="[
                props.isChatStarted ? 'bottom-full mb-2 origin-bottom-left' : 'top-full mt-2 origin-top-left'
              ]"
            >
              <div class="px-3 py-2 text-[10px] font-bold text-text-placeholder uppercase tracking-wider">默认选项</div>
              <div 
                @click="setDefaultOption('thinking', !state.defaultSettings.thinking)"
                @mousedown.prevent
                class="px-3 py-2 text-xs hover:bg-bg-hover cursor-pointer flex items-center justify-between"
              >
                <span>深度思考</span>
                <FontAwesomeIcon v-if="state.defaultSettings.thinking" :icon="['fas', 'check']" class="text-text-main" />
              </div>
              <div 
                @click="setDefaultOption('enable_function', !state.defaultSettings.enable_function)"
                @mousedown.prevent
                class="px-3 py-2 text-xs hover:bg-bg-hover cursor-pointer flex items-center justify-between"
              >
                <span>使用工具</span>
                <FontAwesomeIcon v-if="state.defaultSettings.enable_function" :icon="['fas', 'check']" class="text-text-main" />
              </div>
            </div>
          </transition>
        </div>
      </div>

      <div class="flex items-center gap-3">
        <input 
          type="file" 
          ref="fileInput" 
          class="hidden" 
          multiple 
          accept="image/*" 
          @change="handleFileUpload"
        />
        <button 
          @click="fileInput?.click()"
          @mousedown.prevent
          class="text-text-placeholder hover:text-text-main w-8 h-8 flex items-center justify-center rounded-md transition-colors" 
          title="上传图片"
        >
          <FontAwesomeIcon :icon="['far', 'image']" class="text-lg" />
        </button>
        <button 
          @click="handleSend"
          @mousedown.prevent
          class="bg-primary-main text-primary-text hover:bg-primary-hover w-8 h-8 flex items-center justify-center rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="state.isStreaming"
        >
          <FontAwesomeIcon v-if="state.isStreaming" :icon="['fas', 'spinner']" spin class="text-sm" />
          <FontAwesomeIcon v-else :icon="['fas', 'paper-plane']" class="text-sm" />
        </button>
      </div>


    </div>
  </div>
</template>
