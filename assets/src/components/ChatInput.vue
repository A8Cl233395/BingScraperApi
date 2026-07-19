<script setup lang="ts">
import { state } from '../store';
import { ref, watch, nextTick, onUnmounted, computed } from 'vue';
import { isMobileDevice } from '../utils/device';
import { useImageEditor } from '../composables/useImageEditor';
import { useVoiceInput } from '../composables/useVoiceInput';
import { useToast } from '../composables/useToast';
import FileEditorGrid from './FileEditorGrid.vue';

const { showToast } = useToast();


const props = defineProps<{
  isChatStarted: boolean;
}>();

const emit = defineEmits(['send', 'stop', 'mobile-focus', 'mobile-blur']);

const textInput = ref('');
const showOptions = ref(false);
const textareaRef = ref<HTMLTextAreaElement | null>(null);

// 文件编辑（使用 composable）
const {
  images,
  audioFiles,
  otherFiles,
  isProcessingImage,
  isOcrProcessing,
  isConverting,
  fileInputRef: fileInput,
  handleFileUpload,
  handlePaste,
  handleDrop,
  removeImage,
  removeAudio,
  removeOtherFile,
  handleOcr,
  handleAudioConvert,
  handleFileConvert,
  clearImages,
} = useImageEditor({ trackDraft: true });

const { isRecording, isRecognizing, startRecording, stopRecording, toggleRecording } = useVoiceInput(textInput);

const hasUnconvertedFiles = computed(() =>
  audioFiles.value.length > 0 || otherFiles.value.length > 0 || isOcrProcessing.value
);

const handleImageOcr = (index: number) => {
  handleOcr(index, textInput);
};

const handleAudioConvertAction = (index: number) => {
  handleAudioConvert(index, textInput);
};

const handleFileConvertAction = (index: number) => {
  handleFileConvert(index, textInput);
};

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
  if (state.isStreaming || isRecording.value || isRecognizing.value) return;
  if (textInput.value.trim() || images.value.length > 0) {
    if (hasUnconvertedFiles.value) return;
    
    // 只有文本没有图片时，直接以字符串形式传输
    if (images.value.length === 0 && textInput.value.trim()) {
      emit('send', textInput.value.trim());
    } else {
      const content: any[] = [];
      images.value.forEach(url => {
        content.push({ type: 'image_url', image_url: { url } });
      });
      if (textInput.value.trim()) {
        content.push({ type: 'text', text: textInput.value.trim() });
      }
      emit('send', content);
    }
    
    textInput.value = '';
    clearImages();
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

const handleStop = () => {
  emit('stop');
};

const restoreInput = (content: any) => {
  if (!content) return;
  if (typeof content === 'string') {
    textInput.value = content;
  } else if (Array.isArray(content)) {
    const textObj = content.find((c: any) => c.type === 'text');
    if (textObj) {
      textInput.value = textObj.text;
    }
    const imageObjs = content.filter((c: any) => c.type === 'image_url');
    images.value = imageObjs.map((c: any) => c.image_url.url);
  }
};

defineExpose({ restoreInput });

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
    await state.updateConfig(payload);
    showToast('默认选项已更新');
  } catch (e) {
    console.error('Failed to set default option', e);
    showToast('更新默认选项失败', 'error');
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
      class="relative border border-border-input rounded-lg p-3 flex flex-col focus-within:border-text-muted transition-colors bg-bg-main shadow-[0_2px_10px_rgba(0,0,0,0.05)]"
      @paste="handlePaste"
      @drop="handleDrop"
      @dragover.prevent
    >
      <!-- File Previews -->
      <FileEditorGrid
        :images="images"
        :audio-files="audioFiles"
        :other-files="otherFiles"
        :is-processing-image="isProcessingImage"
        :is-ocr-processing="isOcrProcessing"
        :is-converting="isConverting"
        @remove-image="removeImage"
        @remove-audio="removeAudio"
        @remove-other="removeOtherFile"
        @ocr="handleImageOcr"
        @convert-audio="handleAudioConvertAction"
        @convert-file="handleFileConvertAction"
      />

      <textarea 
        ref="textareaRef"
        v-model="textInput"
        rows="1" 
        maxlength="1000000"
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
            @enter="(el: any) => { el.style.transition = 'none'; el.style.height = '0px'; el.offsetHeight; el.style.transition = 'height 0.25s cubic-bezier(0.4, 0, 0.2, 1)'; el.style.height = el.scrollHeight + 'px'; }"
            @after-enter="(el: any) => { el.style.transition = ''; el.style.height = 'auto'; }"
            @leave="(el: any) => { el.style.transition = 'none'; el.style.height = el.scrollHeight + 'px'; el.offsetHeight; el.style.transition = 'height 0.25s cubic-bezier(0.4, 0, 0.2, 1)'; el.style.height = '0px'; }"
            @after-leave="(el: any) => { el.style.transition = ''; }"
          >
            <!-- Default Options Popup -->
            <div 
              v-if="showOptions"
              class="absolute left-0 w-48 z-50 overflow-hidden shadow-xl rounded-lg"
              :class="[
                props.isChatStarted ? 'bottom-full mb-2 origin-bottom-left' : 'top-full mt-2 origin-top-left'
              ]"
            >
              <div class="bg-bg-main border border-border-main rounded-lg p-1">
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
          accept="image/*,.heic,.heif,.mp3,.wav,.ogg,.aac,.flac,.pdf,.docx,.xlsx,.pptx,.doc,.xls,.ppt,.txt,.md,.json,.xml,.yaml,.yml,.csv,.html,.rtf,.log,.ini,.cfg,.conf,.sh,.bat,.py,.js,.ts,.css,.vue,.tsx,.jsx,.go,.rs,.toml,.env,.gitignore" 
          @change="handleFileUpload"
        />
        <button 
          @click="fileInput?.click()"
          @mousedown.prevent
          class="text-text-placeholder hover:text-text-main w-8 h-8 flex items-center justify-center rounded-md transition-colors" 
          title="插入图片和文件"
        >
          <FontAwesomeIcon :icon="['far', 'folder']" class="text-lg" />
        </button>
        <button
          v-if="state.isMobile"
          @touchstart.prevent="startRecording"
          @touchend="stopRecording"
          @touchcancel="stopRecording"
          class="w-8 h-8 flex items-center justify-center rounded-md transition-colors"
          :class="isRecording ? 'bg-danger-main text-primary-text hover:opacity-80' : isRecognizing ? 'bg-text-placeholder text-primary-text cursor-not-allowed' : 'text-text-placeholder hover:text-text-main'"
          :disabled="isRecognizing"
        >
          <FontAwesomeIcon v-if="isRecognizing" :icon="['fas', 'spinner']" class="text-sm animate-spin" />
          <div v-else-if="isRecording" class="flex items-center gap-[2px] h-3">
            <span class="voice-bar w-[3px] h-full bg-primary-text rounded-full"></span>
            <span class="voice-bar w-[3px] h-full bg-primary-text rounded-full" style="animation-delay:0.15s"></span>
            <span class="voice-bar w-[3px] h-full bg-primary-text rounded-full" style="animation-delay:0.3s"></span>
            <span class="voice-bar w-[3px] h-full bg-primary-text rounded-full" style="animation-delay:0.45s"></span>
          </div>
          <FontAwesomeIcon v-else :icon="['fas', 'microphone']" class="text-lg" />
        </button>
        <button
          v-else
          @click="toggleRecording()"
          @mousedown.prevent
          class="w-8 h-8 flex items-center justify-center rounded-md transition-colors"
          :class="isRecording ? 'bg-danger-main text-primary-text hover:opacity-80' : isRecognizing ? 'bg-text-placeholder text-primary-text cursor-not-allowed' : 'text-text-placeholder hover:text-text-main'"
          :disabled="isRecognizing"
          :title="isRecording ? '停止录音' : isRecognizing ? '识别中...' : '语音输入'"
        >
          <FontAwesomeIcon v-if="isRecognizing" :icon="['fas', 'spinner']" class="text-sm animate-spin" />
          <div v-else-if="isRecording" class="flex items-center gap-[2px] h-3">
            <span class="voice-bar w-[3px] h-full bg-primary-text rounded-full"></span>
            <span class="voice-bar w-[3px] h-full bg-primary-text rounded-full" style="animation-delay:0.15s"></span>
            <span class="voice-bar w-[3px] h-full bg-primary-text rounded-full" style="animation-delay:0.3s"></span>
            <span class="voice-bar w-[3px] h-full bg-primary-text rounded-full" style="animation-delay:0.45s"></span>
          </div>
          <FontAwesomeIcon v-else :icon="['fas', 'microphone']" class="text-lg" />
        </button>
        <button 
          v-if="state.isStreaming"
          @click="handleStop"
          @mousedown.prevent
          class="bg-danger-main text-primary-text hover:opacity-80 w-8 h-8 flex items-center justify-center rounded-md transition-colors"
          title="停止生成"
        >
          <FontAwesomeIcon :icon="['fas', 'stop']" class="text-sm" />
        </button>
        <button 
          v-else
          @click="handleSend"
          @mousedown.prevent
          class="w-8 h-8 flex items-center justify-center rounded-md transition-colors"
          :class="(hasUnconvertedFiles || isRecording || isRecognizing) ? 'bg-text-placeholder text-primary-text cursor-not-allowed' : 'bg-primary-main text-primary-text hover:bg-primary-hover'"
          :disabled="hasUnconvertedFiles || isRecording || isRecognizing"
        >
          <FontAwesomeIcon :icon="['fas', 'paper-plane']" class="text-sm" />
        </button>
      </div>


    </div>
  </div>
</template>

<style scoped>
.layout-transition {
  transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes voice-bar {
  0%, 100% { transform: scaleY(0.3); }
  50% { transform: scaleY(1); }
}

.voice-bar {
  animation: voice-bar 0.6s ease-in-out infinite;
}
</style>
