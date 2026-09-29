<script setup lang="ts">
import { ref, computed, watch, nextTick, reactive, onBeforeUnmount } from 'vue';
import { state } from '../store';
import { useImageEditor } from '../composables/useImageEditor';
import { useLongPress } from '../composables/useLongPress';
import { useToast } from '../composables/useToast';
import FileEditorGrid from './FileEditorGrid.vue';
import MarkdownView from './MarkdownView.vue';

const props = defineProps<{
  message: any;
  nodeId: string;
  isUser: boolean;
  siblingCount?: number;
  siblingIndex?: number;
}>();

const emit = defineEmits(['navigate', 'edit', 'regenerate']);
const { showToast } = useToast();

const isThinkingExpanded = ref(state.defaultExpandThinking);
const thinkingOverrides = reactive<Record<number | string, boolean>>({});
const toolOverrides = reactive<Record<string, boolean>>({});

const isThinkingSegmentExpanded = (idx: number | string) => {
  return idx in thinkingOverrides ? thinkingOverrides[idx] : state.defaultExpandThinking;
};
const isToolExpanded = (id: string) => {
  return id in toolOverrides ? toolOverrides[id] : state.defaultExpandTools;
};

const toggleThinkingSegment = (idx: number | string) => {
  thinkingOverrides[idx] = !isThinkingSegmentExpanded(idx);
};
const toggleTool = (id: string) => {
  toolOverrides[id] = !isToolExpanded(id);
};
const isEditing = ref(false);
const editText = ref('');

// 编辑模式图片处理（使用 composable）
const {
  images: editImages,
  audioFiles: editAudioFiles,
  otherFiles: editOtherFiles,
  isProcessingImage: isProcessingEditImage,
  isOcrProcessing: isEditOcrProcessing,
  isConverting: isEditConverting,
  fileInputRef: editFileInput,
  handleFileUpload: handleEditFileUpload,
  handlePaste: handleEditPaste,
  handleDrop: handleEditDrop,
  removeImage: removeEditImage,
  removeAudio: removeEditAudio,
  removeOtherFile: removeEditOtherFile,
  handleOcr: editHandleOcrRaw,
  handleAudioConvert: editHandleAudioConvertRaw,
  handleFileConvert: editHandleFileConvertRaw,
} = useImageEditor();

const handleEditImageOcr = (index: number) => {
  editHandleOcrRaw(index, editText);
};

const handleEditAudioConvert = (index: number) => {
  editHandleAudioConvertRaw(index, editText);
};

const handleEditFileConvert = (index: number) => {
  editHandleFileConvertRaw(index, editText);
};
const copied = ref(false);
let copiedTimer: ReturnType<typeof setTimeout> | null = null;

onBeforeUnmount(() => {
  if (copiedTimer) clearTimeout(copiedTimer);
});

watch(() => props.nodeId, () => {
  isThinkingExpanded.value = state.defaultExpandThinking;
  for (const key of Object.keys(thinkingOverrides)) delete thinkingOverrides[key];
  for (const key of Object.keys(toolOverrides)) delete toolOverrides[key];
  isEditing.value = false;
});

// === MOBILE LONG PRESS & MENU ===
const {
  showMenu: showMobileMenu,
  isPressing,
  menuStyle,
  startLongPress: startLongPressBase,
  cancelLongPress,
  closeMenu,
} = useLongPress({ menuWidth: 160, menuHeight: 130 });

const startLongPress = (e: TouchEvent) => {
  if (!state.isMobile || isEditing.value) return;

  if (props.isUser) {
    // 用户消息无需额外检查
  } else {
    if (props.message.isStreaming) return;
  }

  const target = e.target as HTMLElement;
  if (props.isUser) {
    if (userTextContent.value && target.closest('img')) return;
  } else {
    const hasAssistantText = props.message.assistant?.some((m: any) => m.content && m.content.trim());
    const hasThinkingText = !!thinkingContent.value || !!props.message.assistant?.some((m: any) => m.reasoning_content && m.reasoning_content.trim());
    if ((hasAssistantText || hasThinkingText) && target.closest('img')) return;
  }

  // 长按菜单触发时清除可能已建立的原生选区（Chromium/WebView 长按选择），
  // 同时让 isTextSelected 复位，避免流式更新与自动滚动被误禁用
  startLongPressBase(e, () => window.getSelection()?.removeAllRanges());
};

const handleCopyAction = () => {
  if (props.isUser) handleCopy();
  else handleCopyAssistant();
  // 移动端操作栏隐藏，copied 反馈不可见，用 toast 提示
  showToast('已复制到剪贴板', 'success');
  closeMenu();
};

const handleSelectTextAction = () => {
  let text = '';
  if (props.isUser) {
    text = userTextContent.value;
  } else {
    text = props.message.assistant
      .filter((m: any) => m.role === 'assistant' && m.content)
      .map((m: any) => m.content.trim())
      .filter((c: string) => c.length > 0)
      .join('\n\n');
  }
  state.selectionText = text;
  state.showSelectionOverlay = true;
  closeMenu();
};

const handleEditAction = () => {
  handleEdit();
  closeMenu();
};

const handleRegenerateAction = () => {
  emit('regenerate', props.nodeId);
  closeMenu();
};

// === USER message rendering ===
const userTextContent = computed(() => {
  if (!props.isUser) return '';
  if (typeof props.message === 'string') return props.message;
  if (Array.isArray(props.message)) {
    return props.message.find((c: any) => c.type === 'text')?.text || '';
  }
  return '';
});

// === ASSISTANT message rendering (per-segment) ===
// Markdown 正文由 MarkdownView 按段渲染：props 不变的段会被 Vue 整体跳过，
// 不重新解析也不重写 DOM，已完成段落的选区与代码块滚动位置因此天然保留
const thinkingContent = computed(() => (props.isUser ? '' : props.message?.thinking || ''));

// 流式拖尾作用于增长段 = 流式期间最后一个有正文的 assistant 条目
// （工具调用前后的文本段都要覆盖，不能简单取数组末位）
const tailSegmentIdx = computed(() => {
  if (props.isUser || !props.message?.isStreaming) return -1;
  const arr = props.message.assistant;
  if (!Array.isArray(arr)) return -1;
  for (let i = arr.length - 1; i >= 0; i--) {
    if (arr[i]?.content) return i;
  }
  return -1;
});

const images = computed(() => {
  if (!props.isUser || !Array.isArray(props.message)) return [];
  return props.message.filter((c: any) => c.type === 'image_url').map((c: any) => c.image_url.url);
});

const getToolResponses = (callId: string) => {
  if (props.isUser) return [];
  return props.message.assistant.filter((m: any) => m.role === 'tool' && m.tool_call_id === callId);
};

const showCopyFeedback = () => {
  if (copiedTimer) clearTimeout(copiedTimer);
  copied.value = true;
  copiedTimer = setTimeout(() => { copied.value = false; }, 2000);
};

const handleCopy = () => { navigator.clipboard.writeText(userTextContent.value); showCopyFeedback(); };
const handleCopyAssistant = () => {
  if (props.isUser || !props.message?.assistant) return;
  const text = props.message.assistant
    .filter((m: any) => m.role === 'assistant' && m.content)
    .map((m: any) => m.content.trim())
    .filter((c: string) => c.length > 0)
    .join('\n\n');
  navigator.clipboard.writeText(text);
  showCopyFeedback();
};
const handleEdit = () => {
  isEditing.value = true;
  editText.value = userTextContent.value;
  editImages.value = [...images.value];
  nextTick(() => {
    adjustEditHeight();
    setTimeout(() => {
      if (editTextareaRef.value) {
        editTextareaRef.value.scrollIntoView({ behavior: 'smooth', block: 'center' });
        editTextareaRef.value.focus();
      }
    }, 100);
  });
};

const submitEdit = () => {
  if (editAudioFiles.value.length > 0 || editOtherFiles.value.length > 0) return;

  // 只有文本没有图片时，直接以字符串形式传输（与 ChatInput 保持一致）
  if (editImages.value.length === 0 && editText.value.trim()) {
    emit('edit', props.nodeId, editText.value.trim());
  } else {
    const content: any[] = [];
    editImages.value.forEach(url => {
      content.push({ type: 'image_url', image_url: { url } });
    });
    if (editText.value.trim()) {
      content.push({ type: 'text', text: editText.value.trim() });
    }
    emit('edit', props.nodeId, content);
  }

  isEditing.value = false;
};
const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Enter') {
    if (!state.isMobile && !e.ctrlKey && !e.shiftKey) {
      e.preventDefault();
      submitEdit();
    } else if (e.ctrlKey) {
      e.preventDefault();
      const start = editTextareaRef.value!.selectionStart;
      const end = editTextareaRef.value!.selectionEnd;
      editText.value = editText.value.substring(0, start) + '\n' + editText.value.substring(end);
      nextTick(() => {
        editTextareaRef.value!.selectionStart = editTextareaRef.value!.selectionEnd = start + 1;
        adjustEditHeight();
      });
    }
  }
};

const editTextareaRef = ref<HTMLTextAreaElement | null>(null);
const adjustEditHeight = () => {
  if (editTextareaRef.value) {
    editTextareaRef.value.style.height = 'auto';
    editTextareaRef.value.style.height = Math.min(editTextareaRef.value.scrollHeight, 200) + 'px';
  }
};
watch(editText, () => {
  nextTick(adjustEditHeight);
});

</script>

<template>
  <div :id="'msg-' + nodeId" class="flex flex-col mb-6" :class="isUser ? 'items-end' : 'items-start'">
    <div class="flex flex-col min-w-0" :class="isUser ? (isEditing ? 'w-full items-start' : 'w-fit max-w-[85%] md:max-w-[75%] items-end self-end') : 'w-full items-start'">

      <template v-if="isUser">
        <div class="group flex flex-col min-w-0 max-w-full" :class="isEditing ? 'w-full items-start' : 'items-end'">

          <!-- Image Content (Outside bubble if there is text) -->
          <div
            v-if="images.length > 0 && !isEditing"
            class="relative flex flex-wrap gap-2"
            :class="[
              userTextContent || isEditing ? 'mb-3' : 'p-1 overflow-hidden',
              !userTextContent && !isEditing && state.isMobile ? 'user-select-none' : ''
            ]"
            @touchstart="(!userTextContent && !isEditing) ? startLongPress($event) : null"
            @touchend="(!userTextContent && !isEditing) ? cancelLongPress() : null"
            @touchmove="(!userTextContent && !isEditing) ? cancelLongPress() : null"
            @touchcancel="(!userTextContent && !isEditing) ? cancelLongPress() : null"
            @contextmenu="(state.isMobile && !userTextContent && !isEditing) ? $event.preventDefault() : null"
          >
            <!-- Selected effect for image-only messages -->
            <Transition name="fade">
              <div
                v-if="!userTextContent && !isEditing && isPressing"
                class="absolute inset-0 bg-white/20 z-20 pointer-events-none"
              ></div>
            </Transition>
            <img v-for="(url, idx) in images" :key="idx" :src="url" @click="state.previewImageUrl = url" class="relative z-10 max-w-[200px] max-h-[200px] border border-border-main cursor-pointer" />
          </div>

          <!-- Text Bubble Section -->
          <div
            v-if="userTextContent || isEditing"
            class="relative p-4 shadow-sm bg-bg-panel transition-all duration-200 overflow-hidden min-w-0"
            :class="[isEditing ? 'w-full' : '', state.isMobile ? 'user-select-none' : '']"
            @touchstart="startLongPress"
            @touchend="cancelLongPress"
            @touchmove="cancelLongPress"
            @touchcancel="cancelLongPress"
            @contextmenu="state.isMobile ? $event.preventDefault() : null"
          >
            <!-- Selected effect for text bubble -->
            <Transition name="fade">
              <div
                v-if="isPressing"
                class="absolute inset-0 bg-white/20 z-20 pointer-events-none"
              ></div>
            </Transition>

            <div v-if="!isEditing" class="relative z-10 text-text-main wrap-anywhere whitespace-pre-wrap text-sm leading-relaxed">{{ userTextContent }}</div>
            <div v-else class="w-full" @paste="handleEditPaste" @drop="handleEditDrop" @dragover.prevent>
              <!-- Edit Image Previews -->
              <FileEditorGrid
                :images="editImages"
                :audio-files="editAudioFiles"
                :other-files="editOtherFiles"
                :is-processing-image="isProcessingEditImage"
                :is-ocr-processing="isEditOcrProcessing"
                :is-converting="isEditConverting"
                @remove-image="removeEditImage"
                @remove-audio="removeEditAudio"
                @remove-other="removeEditOtherFile"
                @ocr="handleEditImageOcr"
                @convert-audio="handleEditAudioConvert"
                @convert-file="handleEditFileConvert"
              />
              <textarea ref="editTextareaRef" v-model="editText" maxlength="1000000" class="w-full bg-bg-main border border-border-input p-2 text-sm focus:outline-none focus:border-text-muted resize-none no-scrollbar min-h-[38px]" rows="1" @keydown="handleKeydown"></textarea>
              <input type="file" ref="editFileInput" class="hidden" multiple accept="*/*" @change="handleEditFileUpload" />
            </div>
          </div>
          <div class="mt-2 flex items-center justify-end gap-3 transition-opacity w-full" :class="[isEditing ? 'opacity-100' : (state.isMobile ? (siblingCount && siblingCount > 1 ? 'opacity-100' : 'opacity-0 h-0 overflow-hidden') : 'opacity-0 group-hover:opacity-100')]">
            <!-- Sibling Navigation -->
            <div v-if="siblingCount && siblingCount > 1" class="flex items-center gap-2 text-[10px] text-text-placeholder select-none">
                <button @click="emit('navigate', nodeId, -1)" :disabled="siblingIndex === 0" class="hover:text-text-main disabled:opacity-30 p-1"><ChevronLeft /></button>
                <span>{{ (siblingIndex || 0) + 1 }} / {{ siblingCount }}</span>
                <button @click="emit('navigate', nodeId, 1)" :disabled="siblingIndex === siblingCount! - 1" class="hover:text-text-main disabled:opacity-30 p-1"><ChevronRight /></button>
            </div>
            <template v-if="!isEditing && !state.isMobile">
              <button @click="handleEdit" class="text-text-placeholder hover:text-text-main transition-colors text-xs flex items-center gap-1" title="编辑"><SquarePen /></button>
              <button @click="handleCopy" class="transition-colors text-xs flex items-center gap-1 h-[18px]" :class="copied ? 'text-success-main' : 'text-text-placeholder hover:text-text-main'" :title="copied ? '已复制' : '复制'">
                <component :is="copied ? 'Check' : 'Copy'" class="text-[11px] min-w-3 text-center" />
                <Transition name="fade"><span v-if="copied" class="text-[10px]">已复制</span></Transition>
              </button>
            </template>
            <template v-else-if="isEditing">
              <button @click="editFileInput?.click()" class="text-text-placeholder hover:text-text-main transition-colors mr-auto h-8 w-8 flex items-center justify-center hover:bg-bg-hover" title="上传文件"><Folder class="text-base" /></button>
              <button @click="isEditing = false" class="text-xs text-text-muted hover:text-text-main">取消</button>
              <button @click="submitEdit" class="text-xs bg-primary-main text-primary-text px-2 py-1 hover:bg-primary-hover">确认</button>
            </template>
          </div>
        </div>
      </template>

      <!-- ====== ASSISTANT MESSAGE ====== -->
      <template v-else>
        <div class="group flex flex-col items-start w-full">
          <!-- Thinking -->
          <div v-if="thinkingContent" class="my-2 w-full">
            <div @click="isThinkingExpanded = !isThinkingExpanded" class="flex items-center gap-2 text-xs text-text-placeholder cursor-pointer hover:text-text-muted transition-colors py-1">
              <Brain class="text-[10px] min-w-3 text-center" /><span>思考过程</span>
              <ChevronRight class="text-[10px] transition-transform duration-200" :class="isThinkingExpanded ? 'rotate-90' : ''" />
            </div>
            <div v-if="isThinkingExpanded" @dblclick="isThinkingExpanded = false" class="mt-2 px-3 py-2 pl-4 rounded-none text-xs text-text-muted border-l-[3px] border-text-placeholder leading-relaxed whitespace-pre-wrap" style="background-color: var(--bg-hover);">{{ thinkingContent }}</div>
          </div>

          <!-- Assistant content -->
          <div
            :id="`bubble-${nodeId}-assistant`"
            class="w-full relative overflow-hidden p-1 -m-1 min-w-0"
            :class="state.isMobile ? 'user-select-none' : ''"
            style="touch-action: pan-y;"
            @touchstart="startLongPress"
            @touchend="cancelLongPress"
            @touchmove="cancelLongPress"
            @touchcancel="cancelLongPress"
            @contextmenu="state.isMobile ? $event.preventDefault() : null"
          >
            <!-- Selected effect -->
            <Transition name="fade">
              <div
                v-if="isPressing"
                class="absolute inset-0 bg-white/20 z-20 pointer-events-none"
              ></div>
            </Transition>

            <!-- Waiting for stream (Animation 1: 盲文点阵) -->
            <div v-if="message.isStreaming && !message.streamConnected && (!message.assistant || message.assistant.length === 0) && !thinkingContent" class="relative z-10 w-full flex items-center min-h-[32px] px-1">
              <div class="stream-braille">
                <span class="braille-dot"></span>
                <span class="braille-dot"></span>
                <span class="braille-dot"></span>
                <span class="braille-dot"></span>
                <span class="braille-dot"></span>
                <span class="braille-dot"></span>
              </div>
            </div>
            <template v-for="(item, idx) in message.assistant" :key="idx">
              <!-- Reasoning content (per-segment)。思考过程经插值原地更新 text node、不重建节点，流式期间不会摧毁选区，无需冻结 -->
              <div v-if="item.role === 'assistant' && item.reasoning_content" class="relative z-10 my-2 w-full">
                <div @click="toggleThinkingSegment(idx)" class="flex items-center gap-2 text-xs text-text-placeholder cursor-pointer hover:text-text-muted transition-colors py-1">
                  <Brain class="text-[10px] min-w-3 text-center" /><span>思考过程</span>
                  <ChevronRight class="text-[10px] transition-transform duration-200" :class="isThinkingSegmentExpanded(idx) ? 'rotate-90' : ''" />
                </div>
                <div v-if="isThinkingSegmentExpanded(idx)" @dblclick="thinkingOverrides[idx] = false" class="mt-2 px-3 py-2 pl-4 rounded-none text-xs text-text-muted border-l-[3px] border-text-placeholder leading-relaxed whitespace-pre-wrap" style="background-color: var(--bg-hover);">{{ item.reasoning_content }}</div>
              </div>

              <!-- Text content -->
              <MarkdownView v-if="item.role === 'assistant' && item.content" :content="item.content" :streaming="idx === tailSegmentIdx" />

              <!-- Tool calls -->
              <template v-if="item.role === 'assistant' && item.tool_calls">
                <div v-for="call in item.tool_calls" :key="call.id" class="relative z-10 my-2 w-full">
                  <div @click="toggleTool(call.id)" class="flex items-center gap-2 text-xs text-text-placeholder cursor-pointer hover:text-text-muted transition-colors py-1">
                    <Wrench class="text-[10px] min-w-3 text-center" />
                    <span>调用 {{ call.function.name }}</span>
                    <ChevronRight class="text-[10px] transition-transform duration-200 shrink-0" :class="isToolExpanded(call.id) ? 'rotate-90' : ''" />
                    <span v-if="!isToolExpanded(call.id)" class="inline-block max-w-[50%] min-w-0 font-mono text-[10px] text-text-muted truncate align-middle" :title="call.function.arguments">{{ call.function.arguments }}</span>
                  </div>
                  <div v-if="isToolExpanded(call.id)" class="mt-1">
                    <div @dblclick="toolOverrides[call.id] = false" class="text-[11px] font-mono text-text-placeholder break-all whitespace-pre-wrap px-3 py-2 pl-4 rounded-none border-l-[3px] border-text-placeholder" style="background-color: var(--bg-hover);">{{ call.function.arguments }}</div>
                    <div v-for="resp in getToolResponses(call.id)" :key="resp.tool_call_id" @dblclick="toolOverrides[call.id] = false" class="mt-1 text-[11px] text-text-placeholder whitespace-pre-wrap break-all px-3 py-2 pl-4 rounded-none border-l-[3px] border-text-placeholder" style="background-color: var(--bg-hover);">
                      <span class="text-text-muted font-medium">返回：</span>{{ resp.content }}
                    </div>
                  </div>
                </div>
              </template>
            </template>

            <!-- Streaming active cursor (Animation 2): HTTP 流一连上即显示，不等文字 -->
            <div v-if="message.isStreaming && (message.streamConnected || message.assistant?.length > 0 || thinkingContent)" class="relative z-10 flex items-center mt-2 mb-1 px-1 opacity-80 h-4">
              <span class="stream-cursor"></span>
            </div>
          </div>

          <!-- Assistant Actions -->
          <div class="mt-2 flex items-center gap-3 transition-opacity" :class="state.isMobile ? 'opacity-0 h-0 overflow-hidden' : 'opacity-0 group-hover:opacity-100'">
            <button @click="handleCopyAssistant" class="transition-colors text-xs flex items-center gap-1 h-[18px]" :class="copied ? 'text-success-main' : 'text-text-placeholder hover:text-text-main'" :title="copied ? '已复制' : '复制'">
              <component :is="copied ? 'Check' : 'Copy'" class="text-[11px] min-w-3 text-center" />
              <Transition name="fade"><span v-if="copied" class="text-[10px]">已复制</span></Transition>
            </button>
          </div>
        </div>
      </template>

    </div>

    <!-- Mobile Context Menu：Teleport 到 body，避免被 MessageList 上的 translate 属性困在消息区域内（会绘制到输入框之下） -->
    <Teleport to="body">
      <div v-if="showMobileMenu" class="fixed inset-0 z-1100" @click="closeMenu" @contextmenu.prevent>
        <div class="fixed inset-0 bg-black/5"></div>
        <div
          class="absolute bg-bg-panel border border-border-main shadow-xl overflow-hidden animate-in fade-in zoom-in duration-150 py-1"
          :style="menuStyle"
          @click.stop
        >
          <button @click="handleCopyAction" class="w-full flex items-center gap-3 px-3 py-2 hover:bg-bg-hover transition-colors text-text-main text-sm">
            <Copy class="min-w-4 text-center text-text-muted" />
            <span>复制</span>
          </button>
          <button @click="handleSelectTextAction" class="w-full flex items-center gap-3 px-3 py-2 hover:bg-bg-hover transition-colors text-text-main text-sm">
            <TextCursor class="min-w-4 text-center text-text-muted" />
            <span>选择文本</span>
          </button>
          <button v-if="isUser" @click="handleEditAction" class="w-full flex items-center gap-3 px-3 py-2 hover:bg-bg-hover transition-colors text-text-main text-sm">
            <SquarePen class="min-w-4 text-center text-text-muted" />
            <span>修改</span>
          </button>
          <button v-else @click="handleRegenerateAction" class="w-full flex items-center gap-3 px-3 py-2 hover:bg-bg-hover transition-colors text-text-main text-sm">
            <RotateCw class="min-w-4 text-center text-text-muted" />
            <span>重新生成</span>
          </button>
        </div>
      </div>
    </Teleport>


  </div>
</template>

<style scoped>
/* 移动端长按区域禁用原生文本选择（Chromium/WebView 需保留 -webkit- 前缀） */
.user-select-none {
  -webkit-user-select: none !important;
  user-select: none !important;
}

/* 连接动画：盲文点阵（2×3 方格，3 个亮块绕环旋转，等价经典 ⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏ 序列） */
.stream-braille {
  display: grid;
  grid-template-columns: repeat(2, 4px);
  grid-template-rows: repeat(3, 4px);
  gap: 3px 6px;
  padding: 7px 4px;
}
.stream-braille .braille-dot {
  width: 4px;
  height: 4px;
  background-color: var(--primary);
  opacity: 0.15;
  animation: braille-spin 0.9s step-end infinite;
}
/* 亮块窗口沿环 [左上,左中,左下,右下,右中,右上] 每 0.15s 前移一格 */
.stream-braille .braille-dot:nth-child(1) { animation-delay: -0.6s; }
.stream-braille .braille-dot:nth-child(2) { animation-delay: -0.45s; }
.stream-braille .braille-dot:nth-child(3) { animation-delay: -0.75s; }
.stream-braille .braille-dot:nth-child(4) { animation-delay: -0.3s; }
.stream-braille .braille-dot:nth-child(5) { animation-delay: 0s; }
.stream-braille .braille-dot:nth-child(6) { animation-delay: -0.15s; }

@keyframes braille-spin {
  0% { opacity: 1; }
  50%, 100% { opacity: 0.15; }
}

.stream-cursor {
  display: inline-block;
  width: 6px;
  height: 14px;
  background-color: var(--primary);
  border-radius: 0;
  animation: blink 1s step-end infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
</style>
