<script setup lang="ts">
import { state } from '../store';
import { ref, watch, nextTick } from 'vue';
import { processImage } from '../utils/image';
import api from '../utils/api';
import { isMobileDevice } from '../utils/device';


const props = defineProps<{
  isChatStarted: boolean;
}>();

const emit = defineEmits(['send']);

const textInput = ref('');
const images = ref<string[]>([]);
const fileInput = ref<HTMLInputElement | null>(null);
const showOptions = ref(false);
const textareaRef = ref<HTMLTextAreaElement | null>(null);

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
  for (const file of files) {
    if (images.value.length >= 10) break;
    if (file.type.startsWith('image/')) {
      const base64 = await processImage(file);
      images.value.push(base64);
    }
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
    class="w-full max-w-4xl mx-auto px-4 layout-transition flex flex-col flex-shrink-0"
    :class="props.isChatStarted ? 'pb-6 pt-2' : 'pb-[15vh] pt-4'"
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
      <div v-if="images.length > 0" class="flex flex-wrap gap-2 mb-2">
        <div v-for="(img, index) in images" :key="index" class="relative group w-16 h-16 rounded-md overflow-hidden border border-border-main">
          <img :src="img" class="w-full h-full object-cover" />
          <button 
            @click="removeImage(index)"
            class="absolute top-0 right-0 bg-black/50 text-white w-5 h-5 flex items-center justify-center rounded-bl-md opacity-0 group-hover:opacity-100 transition-opacity"
          >
            <i class="fas fa-times text-[10px]"></i>
          </button>
        </div>
      </div>

      <textarea 
        ref="textareaRef"
        v-model="textInput"
        rows="1" 
        class="w-full resize-none outline-none border-none bg-transparent p-1 text-sm no-scrollbar text-text-main placeholder-text-placeholder min-h-[24px]"
        :placeholder="isMobileDevice() ? '输入消息...' : '输入消息，Shift+Enter 或 Ctrl+Enter 换行，Enter 发送...'"
        @keydown="handleKeydown"

      ></textarea>
    </div>

    <!-- Toggles and Options -->
    <div class="flex items-center justify-between mt-3 ml-1">
      <div class="flex items-center gap-2">
        <button 
          @click="state.isThinking = !state.isThinking"
          class="flex items-center gap-1.5 px-3 py-1.5 border border-border-input rounded-md text-xs hover:bg-bg-hover transition-colors"
          :class="state.isThinking ? 'bg-text-main text-bg-main border-text-main hover:bg-text-muted' : 'bg-bg-main text-text-muted'"
        >
          <i class="fa-solid fa-brain" :class="state.isThinking ? 'text-bg-main' : 'text-text-placeholder'"></i>
          深度思考
        </button>
        <button 
          @click="state.isEnableFunction = !state.isEnableFunction"
          class="flex items-center gap-1.5 px-3 py-1.5 border border-border-input rounded-md text-xs hover:bg-bg-hover transition-colors"
          :class="state.isEnableFunction ? 'bg-text-main text-bg-main border-text-main hover:bg-text-muted' : 'bg-bg-main text-text-muted'"
        >
          <i class="fa-solid fa-wrench" :class="state.isEnableFunction ? 'text-bg-main' : 'text-text-placeholder'"></i>
          使用工具
        </button>
        <div class="relative">
          <button 
            @click="showOptions = !showOptions"
            class="w-8 h-8 flex items-center justify-center border border-border-input rounded-md text-text-placeholder hover:bg-bg-hover transition-colors" 
            title="默认选项"
          >
            <i 
              class="fas text-xs transition-transform" 
              :class="[
                props.isChatStarted ? 'fa-chevron-up' : 'fa-chevron-down',
                showOptions ? 'rotate-180' : ''
              ]"
            ></i>
          </button>

          <transition
            enter-active-class="transition duration-300 ease-out"
            enter-from-class="transform scale-y-0 opacity-0"
            enter-to-class="transform scale-y-100 opacity-100"
            leave-active-class="transition duration-200 ease-in"
            leave-from-class="transform scale-y-100 opacity-100"
            leave-to-class="transform scale-y-0 opacity-0"
          >
            <!-- Default Options Popup -->
            <div 
              v-if="showOptions"
              class="absolute left-0 w-48 bg-bg-main border border-border-main rounded-lg shadow-xl z-50 p-1"
              :class="[
                props.isChatStarted ? 'bottom-full mb-2 origin-bottom-left' : 'top-full mt-2 origin-top-left'
              ]"
            >
              <div class="px-3 py-2 text-[10px] font-bold text-text-placeholder uppercase tracking-wider">默认选项</div>
              <div 
                @click="setDefaultOption('thinking', !state.defaultSettings.thinking)"
                class="px-3 py-2 text-xs hover:bg-bg-hover cursor-pointer flex items-center justify-between"
              >
                <span>深度思考</span>
                <i v-if="state.defaultSettings.thinking" class="fas fa-check text-text-main"></i>
              </div>
              <div 
                @click="setDefaultOption('enable_function', !state.defaultSettings.enable_function)"
                class="px-3 py-2 text-xs hover:bg-bg-hover cursor-pointer flex items-center justify-between"
              >
                <span>使用工具</span>
                <i v-if="state.defaultSettings.enable_function" class="fas fa-check text-text-main"></i>
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
          class="text-text-placeholder hover:text-text-main w-8 h-8 flex items-center justify-center rounded-md transition-colors" 
          title="上传图片"
        >
          <i class="far fa-image text-lg"></i>
        </button>
        <button 
          @click="handleSend"
          class="bg-primary-main text-primary-text hover:bg-primary-hover w-8 h-8 flex items-center justify-center rounded-md transition-colors"
        >
          <i class="fas fa-paper-plane text-sm"></i>
        </button>
      </div>


    </div>
  </div>
</template>
