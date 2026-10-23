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

  // 助手消息内容在影子树内：e.target 会被重定向到宿主，真实目标取 composedPath 首位
  const target = (e.composedPath()[0] as HTMLElement) ?? (e.target as HTMLElement);
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

// 首个可见输出（思考 / 正文 / 工具）出现前：连接指示器与等待转轮的窗口
const waitingForOutput = computed(() =>
  !props.isUser &&
  !!props.message?.isStreaming &&
  (!props.message.assistant || props.message.assistant.length === 0) &&
  !thinkingContent.value
);

// 最新一段仍在输出的思考：折叠时用 THINKING 点阵补上「还在动」的反馈。
// 首个正文 token 到达（last.content）或工具调用开始（tool_calls）后立即让位，
// 但思考结束、正文未到的空档仍保持动画，避免看起来卡死。
const liveThinkingIdx = computed(() => {
  // HTTP 未连通（握手 / 重连）时不显示，避免把断线等待误当成仍在输出
  if (props.isUser || !props.message?.isStreaming || props.message.streamConnected === false) return -1;
  const arr = props.message.assistant;
  if (!Array.isArray(arr) || arr.length === 0) return -1;

  const last = arr[arr.length - 1];
  if (last?.role !== 'assistant') return -1;
  if (!last.reasoning_content || last.content || last.tool_calls?.length) return -1;
  return arr.length - 1;
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
              <textarea ref="editTextareaRef" v-model="editText" maxlength="1000000" class="edge-control w-full bg-bg-main border border-border-input p-2 text-sm resize-none no-scrollbar min-h-[38px]" rows="1" @keydown="handleKeydown"></textarea>
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
              <button @click="handleEdit" class="text-text-placeholder hover:text-text-main px-1 transition-colors text-xs flex items-center gap-1" title="编辑"><SquarePen /></button>
              <button @click="handleCopy" class="transition-colors text-xs flex items-center gap-1 h-[18px] px-1" :class="copied ? 'text-success-main' : 'text-text-placeholder hover:text-text-main'" :title="copied ? '已复制' : '复制'">
                <component :is="copied ? 'Check' : 'Copy'" class="text-[11px] min-w-3 text-center" />
                <Transition name="fade"><span v-if="copied" class="text-[10px]">已复制</span></Transition>
              </button>
            </template>
            <template v-else-if="isEditing">
              <button @click="editFileInput?.click()" class="text-text-placeholder hover:text-text-main transition-colors mr-auto h-8 w-8 flex items-center justify-center" title="上传文件"><Folder class="text-base" /></button>
              <button @click="isEditing = false" class="text-xs text-text-muted hover:text-text-main px-1">取消</button>
              <button @click="submitEdit" class="text-xs bg-primary-main text-primary-text px-2 py-1">确认</button>
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
            class="self-stretch relative overflow-hidden p-1 -m-1 min-w-0"
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

            <!-- 等待指示分两段：HTTP 握手（CONNECTING，方括号逐格）→ SSE 已开、首 token 未到（WAITING，终端转轮）。
                 首个可见输出（思考 / 正文 / 工具）出现即让位；CONNECTING 延迟 220ms 出现，避免快连接闪一下 -->
            <div v-if="waitingForOutput" class="stream-status" role="status" aria-live="polite">
              <span v-if="!message.streamConnected" class="status-branch link-wait" title="正在建立连接">
                <span class="status-icon" aria-hidden="true">
                  <span class="link-meter">
                    <span class="meter-frame">[&nbsp;&nbsp;&nbsp;]</span>
                    <span class="meter-frame">[·&nbsp;&nbsp;]</span>
                    <span class="meter-frame">[··&nbsp;]</span>
                    <span class="meter-frame">[···]</span>
                  </span>
                </span>
                <span class="status-label" data-text="CONNECTING" aria-hidden="true">CONNECTING</span>
                <span class="sr-only">正在建立连接</span>
              </span>
              <span v-else class="status-branch wait-wait" title="已连接，等待模型响应">
                <span class="status-icon" aria-hidden="true">
                  <span class="stream-spin">
                    <span class="spin-frame">|</span>
                    <span class="spin-frame">/</span>
                    <span class="spin-frame">-</span>
                    <span class="spin-frame">\</span>
                  </span>
                </span>
                <span class="status-label" data-text="WAITING" aria-hidden="true">WAITING</span>
                <span class="sr-only">已连接，等待模型响应</span>
              </span>
            </div>
            <template v-for="(item, idx) in message.assistant" :key="idx">
              <!-- Reasoning content (per-segment)。思考过程经插值原地更新 text node、不重建节点，流式期间不会摧毁选区，无需冻结 -->
              <div v-if="item.role === 'assistant' && item.reasoning_content" class="relative z-10 my-2 w-full">
                <div @click="toggleThinkingSegment(idx)" class="flex items-center gap-2 text-xs text-text-placeholder cursor-pointer hover:text-text-muted transition-colors py-1">
                  <Brain class="text-[10px] min-w-3 text-center" /><span>思考过程</span>
                  <ChevronRight class="text-[10px] transition-transform duration-200" :class="isThinkingSegmentExpanded(idx) ? 'rotate-90' : ''" />
                  <!-- 折叠时的输出活性：只挂最新一段仍在输出的思考，正文/工具一出现立即让位 -->
                  <span v-if="liveThinkingIdx === idx && !isThinkingSegmentExpanded(idx)" class="think-live" title="正在输出">
                    <span class="think-live-label" data-text="THINKING" aria-hidden="true">THINKING</span>
                    <span class="think-dots" aria-hidden="true">
                      <span class="think-frame">·&nbsp;&nbsp;</span>
                      <span class="think-frame">··&nbsp;</span>
                      <span class="think-frame">···</span>
                      <span class="think-frame"></span>
                    </span>
                    <span class="sr-only">正在输出</span>
                  </span>
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
          </div>

          <!-- Assistant Actions -->
          <div class="mt-2 flex items-center gap-3 transition-opacity" :class="state.isMobile ? 'opacity-0 h-0 overflow-hidden' : 'opacity-0 group-hover:opacity-100'">
            <button @click="handleCopyAssistant" class="transition-colors text-xs flex items-center gap-1 h-[18px] px-1" :class="copied ? 'text-success-main' : 'text-text-placeholder hover:text-text-main'" :title="copied ? '已复制' : '复制'">
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
          <button @click="handleCopyAction" class="w-full flex items-center gap-3 px-3 py-2 transition-colors text-text-main text-sm">
            <Copy class="min-w-4 text-center text-text-muted" />
            <span>复制</span>
          </button>
          <button @click="handleSelectTextAction" class="w-full flex items-center gap-3 px-3 py-2 transition-colors text-text-main text-sm">
            <TextCursor class="min-w-4 text-center text-text-muted" />
            <span>选择文本</span>
          </button>
          <button v-if="isUser" @click="handleEditAction" class="w-full flex items-center gap-3 px-3 py-2 transition-colors text-text-main text-sm">
            <SquarePen class="min-w-4 text-center text-text-muted" />
            <span>修改</span>
          </button>
          <button v-else @click="handleRegenerateAction" class="w-full flex items-center gap-3 px-3 py-2 transition-colors text-text-main text-sm">
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

/* 等待指示：HTTP 握手阶段用方括号逐格填充，SSE 已开后换成终端转轮 | / - \。
   CONNECTING 分支延迟 220ms 出现，快连接时不会闪一下 */
.stream-status {
  position: relative;
  z-index: 10;
  display: flex;
  align-items: center;
  width: 100%;
  min-height: 32px;
  padding: 0 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.status-branch {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 1.2em;
  flex: none;
}

.status-icon {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 5ch;
  height: 1.2em;
  flex: none;
}

.status-label {
  min-width: 4ch;
  font-size: 0.75rem;
  line-height: 1;
  letter-spacing: 0.12em;
  white-space: nowrap;
  color: var(--text-placeholder);
}

.link-wait {
  animation: status-in 1ms steps(1, end) 0.22s both;
}

@keyframes status-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

/* 方括号链路表：四帧硬切，[   ] → [·  ] → [·· ] → [···] 后清空重启 */
.link-meter {
  position: relative;
  display: inline-block;
  width: 5ch;
  height: 1.2em;
  font-size: 0.8rem;
  line-height: 1.2;
  color: var(--primary);
}

.link-meter .meter-frame {
  position: absolute;
  left: 0;
  top: 0;
  white-space: pre;
  opacity: 0;
  animation: meter-step 0.8s steps(1, end) infinite;
}

.link-meter .meter-frame:nth-child(1) { animation-delay: 0s; color: var(--text-placeholder); }
.link-meter .meter-frame:nth-child(2) { animation-delay: 0.2s; }
.link-meter .meter-frame:nth-child(3) { animation-delay: 0.4s; }
.link-meter .meter-frame:nth-child(4) { animation-delay: 0.6s; }

@keyframes meter-step {
  0% { opacity: 1; }
  25%, 100% { opacity: 0; }
}

/* 等待首 token：终端转轮 | / - \（经典 CLI spinner，比盲文点阵更贴合方正工具感）。
   四帧每 0.15s 前移一格、一圈 0.6s；整组偶尔做一次 1px RGB 分离 */
.stream-spin {
  position: relative;
  width: 1ch;
  height: 1.2em;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: inherit; /* 跟正文同字号（曾写死 14px，比 .prose 正文小一号，转轮和正文切换时会跳字号） */
  line-height: 1.2;
  color: var(--primary);
}

.stream-spin .spin-frame {
  position: absolute;
  left: 0;
  top: 0;
  opacity: 0;
  animation: spin-step 0.6s steps(1, end) infinite;
}

.stream-spin .spin-frame:nth-child(1) { animation-delay: 0s; }
.stream-spin .spin-frame:nth-child(2) { animation-delay: 0.15s; }
.stream-spin .spin-frame:nth-child(3) { animation-delay: 0.3s; }
.stream-spin .spin-frame:nth-child(4) { animation-delay: 0.45s; }

@keyframes spin-step {
  0% { opacity: 1; }
  25%, 100% { opacity: 0; }
}

/* 折叠思考的 THINKING 活性点阵：跟在展开箭头后面，展开/收起只增减后缀，不推动标题。
   四帧硬切，· → ·· → ··· → 空，1.2s 一圈 */
.think-live {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex: none;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  line-height: 1;
}

.think-live-label {
  font-size: 0.75rem;
  letter-spacing: 0.12em;
  white-space: nowrap;
  color: var(--text-placeholder);
}

.think-dots {
  position: relative;
  display: inline-block;
  width: 3ch;
  height: 1em;
  font-size: 0.9rem;
  line-height: 1;
  color: var(--primary);
}

.think-dots .think-frame {
  position: absolute;
  left: 0;
  top: 0;
  white-space: pre;
  opacity: 0;
  animation: think-step 1.2s steps(1, end) infinite;
}

.think-dots .think-frame:nth-child(1) { animation-delay: 0s; }
.think-dots .think-frame:nth-child(2) { animation-delay: 0.3s; }
.think-dots .think-frame:nth-child(3) { animation-delay: 0.6s; }
.think-dots .think-frame:nth-child(4) { animation-delay: 0.9s; }

@keyframes think-step {
  0% { opacity: 1; }
  25%, 100% { opacity: 0; }
}

/* 低频 glitch 点缀：标签的青/品红副本短暂切片撕裂，字形做 1px RGB 分离。
   三层周期互相错开（4.6s / 5.9s / 5.3s），刚出现时先抖一次，之后偶尔失步 */
.status-label,
.think-live-label {
  position: relative;
  display: inline-block;
}

.status-label::before,
.status-label::after,
.think-live-label::before,
.think-live-label::after {
  content: attr(data-text);
  position: absolute;
  left: 0;
  top: 0;
  width: 100%;
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
}

.status-label::before,
.think-live-label::before {
  color: var(--glitch-cyan);
  animation: status-label-tear-a 4.6s steps(1, end) infinite;
}

.status-label::after,
.think-live-label::after {
  color: var(--glitch-magenta);
  animation: status-label-tear-b 5.9s steps(1, end) 40ms infinite;
}

/* CONNECTING 分支整体延迟 220ms 出现，撕裂同步对齐到出现时刻 */
.link-wait .status-label::before { animation-delay: 220ms; }
.link-wait .status-label::after { animation-delay: 260ms; }
.link-wait .link-meter { animation-delay: 220ms; }

@keyframes status-label-tear-a {
  0% { opacity: 0.85; clip-path: inset(16% 0 58% 0); transform: translate(-1px, 0); }
  1.4% { opacity: 0.9; clip-path: inset(62% 0 14% 0); transform: translate(1px, 0); }
  2.8% { opacity: 0.6; clip-path: inset(38% 0 42% 0); transform: translate(-0.5px, 0); }
  4.2%, 100% { opacity: 0; clip-path: inset(0 0 100% 0); transform: none; }
}

@keyframes status-label-tear-b {
  0% { opacity: 0.75; clip-path: inset(58% 0 18% 0); transform: translate(1px, 0); }
  1.6% { opacity: 0.85; clip-path: inset(10% 0 68% 0); transform: translate(-1px, 0); }
  3.2%, 100% { opacity: 0; clip-path: inset(0 0 100% 0); transform: none; }
}

/* 括号表 / 转轮 / 点阵：整组做一次横向 1px 的 RGB 分离，随后回到干净字形 */
.link-meter,
.stream-spin,
.think-dots {
  animation: status-icon-tear 5.3s steps(1, end) infinite;
}

@keyframes status-icon-tear {
  0% { filter: drop-shadow(1px 0 var(--glitch-cyan)) drop-shadow(-1px 0 var(--glitch-magenta)); transform: translateX(-1px); }
  1.5% { filter: drop-shadow(-1px 0 var(--glitch-cyan)) drop-shadow(1px 0 var(--glitch-magenta)); transform: translateX(1px); }
  3%, 100% { filter: none; transform: none; }
}

/* 减弱动态效果：转轮静止在首帧 |，链路表静止在一格，思考点阵静止在 ··· */
@media (prefers-reduced-motion: reduce) {
  .link-wait {
    animation: none;
  }

  .link-meter .meter-frame {
    animation: none;
  }

  .link-meter .meter-frame:nth-child(2) {
    opacity: 1;
  }

  .stream-spin .spin-frame {
    animation: none;
  }

  .stream-spin .spin-frame:nth-child(1) {
    opacity: 1;
  }

  .think-dots .think-frame {
    animation: none;
  }

  .think-dots .think-frame:nth-child(3) {
    opacity: 1;
  }

  .status-label::before,
  .status-label::after,
  .think-live-label::before,
  .think-live-label::after,
  .link-meter,
  .stream-spin,
  .think-dots {
    animation: none;
  }

  .status-label::before,
  .status-label::after,
  .think-live-label::before,
  .think-live-label::after {
    opacity: 0;
  }

  .link-meter,
  .stream-spin,
  .think-dots {
    filter: none;
    transform: none;
  }
}


</style>
