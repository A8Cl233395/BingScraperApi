<script lang="ts">
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import katex from 'katex';
import 'katex/dist/katex.min.css';
import hljs from 'highlight.js/lib/common';

marked.use({
  breaks: true,
  gfm: true,
  hooks: {
    postprocess(html) {
      // Wrap tables with a scrollable div for mobile compatibility
      return html.replace(/<table/g, '<div class="table-wrapper"><table')
                 .replace(/<\/table>/g, '</table></div>');
    }
  },
  renderer: {
    code(token) {
      const lang = token.lang || 'text';
      let highlightedCode;
      try {
        if (lang && hljs.getLanguage(lang)) {
          highlightedCode = hljs.highlight(token.text, { language: lang }).value;
        } else {
          highlightedCode = hljs.highlightAuto(token.text).value;
        }
      } catch (e) {
        highlightedCode = token.text;
      }
      
      return `
<div class="code-block-wrapper my-4 border-[0.5px] border-border-main rounded-md overflow-hidden bg-code-bg" style="touch-action: pan-x pan-y;">
  <div class="flex justify-between items-center bg-bg-panel px-3 py-1.5 border-b-[0.5px] border-border-main">
    <span class="text-[10px] font-medium text-text-placeholder uppercase tracking-wider">${lang}</span>
    <button class="copy-code-btn text-text-placeholder hover:text-text-main transition-colors flex items-center gap-1" title="复制代码">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" class="copy-icon-svg" width="10" height="10" fill="currentColor"><path d="M64 464H288c8.8 0 16-7.2 16-16V384h48v64c0 35.3-28.7 64-64 64H64c-35.3 0-64-28.7-64-64V224c0-35.3 28.7-64 64-64h64v48H64c-8.8 0-16 7.2-16 16V448c0 8.8 7.2 16 16 16zM224 304H448c8.8 0 16-7.2 16-16V64c0-8.8-7.2-16-16-16H224c-8.8 0-16 7.2-16 16V288c0 8.8 7.2 16 16 16zm-64-16V64c0-35.3 28.7-64 64-64H448c35.3 0 64 28.7 64 64V288c0 35.3-28.7 64-64 64H224c-35.3 0-64-28.7-64-64z"/></svg>
      <span class="text-[10px]">复制</span>
    </button>
  </div>
  <pre class="!m-0 !p-3 !bg-code-bg overflow-x-auto" style="touch-action: pan-x pan-y;"><code class="hljs language-${lang}">${highlightedCode}</code></pre>
</div>`;
    }
  }
});

// Add a custom extension to protect LaTeX from being mangled by marked
marked.use({
  extensions: [
    {
      name: 'strong',
      level: 'inline',
      start(src) { return src.indexOf('**'); },
      tokenizer(src) {
        const match = src.match(/^\*\*([^\s\*](?:[\s\S]*?[^\s\*])??)\*\*(?!\*)/);
        if (match) {
          return {
            type: 'strong',
            raw: match[0],
            text: match[1],
            tokens: this.lexer.inlineTokens(match[1])
          };
        }
      }
    },
    {
      name: 'em',
      level: 'inline',
      start(src) { return src.indexOf('*'); },
      tokenizer(src) {
        const match = src.match(/^\*([^\s\*](?:[\s\S]*?[^\s\*])??)\*(?!\*)/);
        if (match) {
          return {
            type: 'em',
            raw: match[0],
            text: match[1],
            tokens: this.lexer.inlineTokens(match[1])
          };
        }
      }
    },
    {
      name: 'inlineMath',
      level: 'inline',
      start(src) { return src.indexOf('$'); },
      tokenizer(src) {
        const match = src.match(/^\$((?:[^\$]|\\\$)+)\$/);
        if (match) return { type: 'inlineMath', raw: match[0], text: match[1] };
      },
      renderer(token) {
        try {
          return katex.renderToString(token.text, { displayMode: false, throwOnError: false });
        } catch (e) { return token.raw; }
      }
    },
    {
      name: 'blockMath',
      level: 'block',
      start(src) { return src.indexOf('$$'); },
      tokenizer(src) {
        const match = src.match(/^\$\$([\s\S]*?)\$\$/);
        if (match) return { type: 'blockMath', raw: match[0], text: match[1] };
      },
      renderer(token) {
        try {
          return `<div class="math-block">${katex.renderToString(token.text, { displayMode: true, throwOnError: false })}</div>`;
        } catch (e) { return token.raw; }
      }
    },
    {
      name: 'latexInline',
      level: 'inline',
      start(src) { return src.indexOf('\\('); },
      tokenizer(src) {
        const match = src.match(/^\\\(([\s\S]*?)\\\)/);
        if (match) return { type: 'latexInline', raw: match[0], text: match[1] };
        },
      renderer(token) {
        try {
          return katex.renderToString(token.text, { displayMode: false, throwOnError: false });
        } catch (e) { return token.raw; }
      }
    },
    {
      name: 'latexBlock',
      level: 'block',
      start(src) { return src.indexOf('\\['); },
      tokenizer(src) {
        const match = src.match(/^\\\[([\s\S]*?)\\\]/);
        if (match) return { type: 'latexBlock', raw: match[0], text: match[1] };
      },
      renderer(token) {
        try {
          return `<div class="math-block">${katex.renderToString(token.text, { displayMode: true, throwOnError: false })}</div>`;
        } catch (e) { return token.raw; }
      }
    }
  ]
});
</script>

<script setup lang="ts">
import { ref, computed, watch, nextTick, reactive, onBeforeUnmount, onBeforeUpdate, onUpdated } from 'vue';
import { state } from '../store';
import { isMobileDevice } from '../utils/device';
import { useImageEditor } from '../composables/useImageEditor';
import ImageEditorGrid from './ImageEditorGrid.vue';

const props = defineProps<{
  message: any;
  nodeId: string;
  isUser: boolean;
  siblingCount?: number;
  siblingIndex?: number;
}>();

const emit = defineEmits(['navigate', 'edit', 'regenerate']);

const preScrollPositions = new Map<number, number[]>();

onBeforeUpdate(() => {
  const container = document.getElementById(`bubble-${props.nodeId}-assistant`);
  if (container) {
    const segments = container.querySelectorAll('.prose');
    segments.forEach((seg, sIdx) => {
      const pres = seg.querySelectorAll('pre');
      const wrappers = seg.querySelectorAll('.table-wrapper');
      const positions: number[] = [];
      pres.forEach(pre => positions.push(pre.scrollLeft));
      wrappers.forEach(w => positions.push(w.scrollLeft));
      preScrollPositions.set(sIdx, positions);
    });
  }
});

onUpdated(() => {
  const container = document.getElementById(`bubble-${props.nodeId}-assistant`);
  if (container) {
    const segments = container.querySelectorAll('.prose');
    segments.forEach((seg, sIdx) => {
      if (preScrollPositions.has(sIdx)) {
        const positions = preScrollPositions.get(sIdx)!;
        const pres = seg.querySelectorAll('pre');
        const preCount = pres.length;
        pres.forEach((pre, pIdx) => {
          if (positions[pIdx] !== undefined) {
            pre.scrollLeft = positions[pIdx];
          }
        });
        const wrappers = seg.querySelectorAll('.table-wrapper');
        wrappers.forEach((w, wIdx) => {
          const idx = preCount + wIdx;
          if (positions[idx] !== undefined) {
            w.scrollLeft = positions[idx];
          }
        });
      }
    });
  }
});

const isThinkingExpanded = ref(false);
const expandedThinkingSegments = ref<Record<number | string, boolean>>({});
const expandedTools = ref<Record<string, boolean>>({});
const toggleThinkingSegment = (idx: number | string) => {
  expandedThinkingSegments.value[idx] = !expandedThinkingSegments.value[idx];
};
const toggleTool = (id: string) => {
  expandedTools.value[id] = !expandedTools.value[id];
};
const isEditing = ref(false);
const editText = ref('');

// 编辑模式图片处理（使用 composable）
const {
  images: editImages,
  isProcessingImage: isProcessingEditImage,
  isOcrProcessing: isEditOcrProcessing,
  fileInputRef: editFileInput,
  handleFileUpload: handleEditFileUpload,
  handlePaste: handleEditPaste,
  handleDrop: handleEditDrop,
  removeImage: removeEditImage,
  handleOcr: editHandleOcrRaw,
} = useImageEditor();

const handleEditImageOcr = (index: number) => {
  editHandleOcrRaw(index, editText);
};
const copied = ref(false);
let copiedTimer: ReturnType<typeof setTimeout> | null = null;

watch(() => props.nodeId, () => {
  isThinkingExpanded.value = false;
  expandedThinkingSegments.value = {};
  expandedTools.value = {};
  isEditing.value = false;
});

// === MOBILE LONG PRESS & MENU ===
const showMobileMenu = ref(false);
const longPressTimer = ref<number | null>(null);
const preLongPressTimer = ref<number | null>(null);
const isPressing = ref(false);

const menuPosition = ref({ x: 0, y: 0 });

const startLongPress = (e: TouchEvent) => {
  if (!state.isMobile || isEditing.value) return;
  
  // Disable long press while streaming to avoid issues with DOM updates and auto-scrolling
  if (props.isUser) {
    // For user messages, we don't have an easy isStreaming prop here 
    // but usually they don't change. However, if we want to be safe:
    // if (props.message.isStreaming) return; 
  } else {
    if (props.message.isStreaming) return;
  }
  
  const target = e.target as HTMLElement;
  // If both text and image exist, long press on image has no effect
  if (props.isUser) {
    if (userTextContent.value && target.closest('img')) return;
  } else {
    const hasAssistantText = props.message.assistant?.some((m: any) => m.content && m.content.trim());
    const hasThinkingText = thinkingContent.value || Object.values(segmentThinking).some(s => s && s.trim());
    if ((hasAssistantText || hasThinkingText) && target.closest('img')) return;
  }
  
  const touch = e.touches[0];
  // Capture coordinates for menu positioning
  menuPosition.value = { x: touch.clientX, y: touch.clientY };
  
  cancelLongPress();
  preLongPressTimer.value = window.setTimeout(() => {
    isPressing.value = true;
    longPressTimer.value = window.setTimeout(() => {
      showMobileMenu.value = true;
      isPressing.value = false;
    }, 400);
  }, 150);
};

const cancelLongPress = () => {
  if (preLongPressTimer.value) {
    clearTimeout(preLongPressTimer.value);
    preLongPressTimer.value = null;
  }
  if (longPressTimer.value) {
    clearTimeout(longPressTimer.value);
    longPressTimer.value = null;
  }
  isPressing.value = false;
};

onBeforeUnmount(() => {
  cancelLongPress();
  preScrollPositions.clear();
  if (copiedTimer) clearTimeout(copiedTimer);
});

const handleCopyAction = () => {
  if (props.isUser) handleCopy();
  else handleCopyAssistant();
  showMobileMenu.value = false;
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
  showMobileMenu.value = false;
};

const handleEditAction = () => {
  handleEdit();
  showMobileMenu.value = false;
};

const handleRegenerateAction = () => {
  emit('regenerate', props.nodeId);
  showMobileMenu.value = false;
};

const menuStyle = computed(() => {
  if (!showMobileMenu.value) return {};
  
  const x = menuPosition.value.x;
  const y = menuPosition.value.y;
  const screenWidth = window.innerWidth;
  const screenHeight = window.innerHeight;
  
  const menuWidth = 160; 
  const menuHeight = 200; 
  
  let left = x - 20;
  let top = y - 20;
  
  // Keep on screen
  if (left + menuWidth > screenWidth - 10) left = screenWidth - menuWidth - 10;
  if (left < 10) left = 10;
  if (top + menuHeight > screenHeight - 10) top = screenHeight - menuHeight - 10;
  if (top < 10) top = 10;
  
  return {
    left: `${left}px`,
    top: `${top}px`,
    width: `${menuWidth}px`
  };
});

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
const segmentHtml = reactive<Record<number | string, string>>({});
const segmentThinking = reactive<Record<number | string, string>>({});
const thinkingContent = ref('');

let pendingUpdate: Record<number, string> | null = null;
let pendingThinkingSegmentsUpdate: Record<number, string> | null = null;
let pendingThinkingUpdate: string | null = null;

let resumeTimeout: any = null;
const applyPendingUpdates = () => {
  if (pendingUpdate) {
    for (const key in segmentHtml) delete segmentHtml[key];
    Object.assign(segmentHtml, pendingUpdate);
    pendingUpdate = null;
  }
  if (pendingThinkingSegmentsUpdate) {
    for (const key in segmentThinking) delete segmentThinking[key];
    Object.assign(segmentThinking, pendingThinkingSegmentsUpdate);
    pendingThinkingSegmentsUpdate = null;
  }
  if (pendingThinkingUpdate !== null) {
    thinkingContent.value = pendingThinkingUpdate;
    pendingThinkingUpdate = null;
  }
};

watch([() => state.isMouseDown, () => state.isTextSelected], ([mouseDown, textSelected]) => {
  if (resumeTimeout) clearTimeout(resumeTimeout);

  if (!mouseDown && !textSelected) {
    // Give some buffer time for selection state to stabilize after mouseup
    resumeTimeout = setTimeout(() => {
      if (!state.isMouseDown && !state.isTextSelected) {
        applyPendingUpdates();
      }
    }, 300);
  }
});

watch(() => props.isUser ? null : props.message?.assistant, (arr) => {
  if (props.isUser || !arr) return;
  
  const map: Record<number, string> = {};
  const thinkingMap: Record<number, string> = {};
  let hasChanges = false;
  let hasThinkingChanges = false;

  for (let i = 0; i < arr.length; i++) {
    const item = arr[i];
    if (item.role === 'assistant' && item.content) {
      try {
        const raw = marked.parse(item.content) as string;
        const r = DOMPurify.sanitize(raw);
        map[i] = r;
        if (segmentHtml[i] !== r) {
          hasChanges = true;
        }
      } catch { 
        map[i] = item.content; 
        if (segmentHtml[i] !== item.content) hasChanges = true;
      }
    }
    if (item.role === 'assistant' && item.reasoning_content) {
      thinkingMap[i] = item.reasoning_content;
      if (segmentThinking[i] !== item.reasoning_content) {
        hasThinkingChanges = true;
      }
    }
  }

  for (const key in segmentHtml) {
    if (!(key in map)) hasChanges = true;
  }
  for (const key in segmentThinking) {
    if (!(key in thinkingMap)) hasThinkingChanges = true;
  }
  
  if (hasChanges) {
    if (state.isTextSelected || state.isMouseDown) {
      pendingUpdate = map;
    } else {
      for (const key in segmentHtml) delete segmentHtml[key];
      Object.assign(segmentHtml, map);
      pendingUpdate = null;
    }
  }
  if (hasThinkingChanges) {
    if (state.isTextSelected || state.isMouseDown) {
      pendingThinkingSegmentsUpdate = thinkingMap;
    } else {
      for (const key in segmentThinking) delete segmentThinking[key];
      Object.assign(segmentThinking, thinkingMap);
      pendingThinkingSegmentsUpdate = null;
    }
  }
}, { deep: true, immediate: true });

watch(() => props.isUser ? null : props.message?.thinking, (val) => {
  if (props.isUser) return;
  const content = val || '';
  
  if (state.isTextSelected || state.isMouseDown) {
    pendingThinkingUpdate = content;
  } else {
    thinkingContent.value = content;
    pendingThinkingUpdate = null;
  }
}, { immediate: true });

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
  const content = [];
  editImages.value.forEach(url => {
    content.push({ type: 'image_url', image_url: { url } });
  });
  if (editText.value.trim()) {
    content.push({ type: 'text', text: editText.value.trim() });
  }
  emit('edit', props.nodeId, content); 
  isEditing.value = false; 
};
const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Enter') {
    if (!isMobileDevice() && !e.ctrlKey && !e.shiftKey) {
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

const checkIconPath = 'M256 48a208 208 0 1 1 0 416 208 208 0 1 1 0-416zm0 464A256 256 0 1 0 256 0a256 256 0 1 0 0 512zM369 209c9.4-9.4 9.4-24.6 0-33.9s-24.6-9.4-33.9 0l-111 111-47-47c-9.4-9.4-24.6-9.4-33.9 0s-9.4 24.6 0 33.9l64 64c9.4 9.4 24.6 9.4 33.9 0L369 209z';

const handleCodeCopy = (e: MouseEvent) => {
  const target = e.target as HTMLElement;
  const btn = target.closest('.copy-code-btn');
  if (!btn) return;
  
  const wrapper = btn.closest('.code-block-wrapper');
  const codeElement = wrapper?.querySelector('code');
  if (codeElement) {
    const code = codeElement.textContent || '';
    navigator.clipboard.writeText(code).then(() => {
      const copySvg = btn.querySelector('.copy-icon-svg');
      const text = btn.querySelector('span');
      if (copySvg && text) {
        const path = copySvg.querySelector('path');
        const originalPath = path!.getAttribute('d')!;
        path!.setAttribute('d', checkIconPath);
        copySvg.classList.add('text-green-500');
        text.textContent = '已复制';
        setTimeout(() => {
          path!.setAttribute('d', originalPath);
          copySvg.classList.remove('text-green-500');
          text.textContent = '复制';
        }, 2000);
      }
    });
  }
};

const handleContentClick = (e: MouseEvent) => {
  const target = e.target as HTMLElement;
  if (target.tagName === 'IMG') {
    const src = (target as HTMLImageElement).src;
    if (src) {
      state.previewImageUrl = src;
    }
    return;
  }
  handleCodeCopy(e);
};

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
              userTextContent || isEditing ? 'mb-3' : 'p-1 rounded-lg overflow-hidden',
              !userTextContent && !isEditing && state.isMobile ? '' : ''
            ]"
            @touchstart="(!userTextContent && !isEditing) ? startLongPress($event) : null"
            @touchend="(!userTextContent && !isEditing) ? cancelLongPress() : null"
            @touchmove="(!userTextContent && !isEditing) ? cancelLongPress() : null"
            @touchcancel="(!userTextContent && !isEditing) ? cancelLongPress() : null"
            @contextmenu="(!userTextContent && !isEditing) ? $event.preventDefault() : null"
          >
            <!-- Selected effect for image-only messages -->
            <Transition name="fade">
              <div 
                v-if="!userTextContent && !isEditing && isPressing"
                class="absolute inset-0 bg-white/20 z-20 pointer-events-none"
              ></div>
            </Transition>
            <img v-for="(url, idx) in images" :key="idx" :src="url" @click="state.previewImageUrl = url" class="relative z-10 max-w-[200px] max-h-[200px] rounded-md border border-border-main cursor-pointer" />
          </div>

          <!-- Text Bubble Section -->
          <div 
            v-if="userTextContent || isEditing"
            class="relative p-4 rounded-lg shadow-sm bg-bg-panel rounded-tr-none transition-all duration-200 overflow-hidden min-w-0" 
            :class="[isEditing ? 'w-full' : '', state.isMobile ? '' : '']"
            @touchstart="startLongPress"
            @touchend="cancelLongPress"
            @touchmove="cancelLongPress"
            @touchcancel="cancelLongPress"
            @contextmenu.prevent
          >
            <!-- Selected effect for text bubble -->
            <Transition name="fade">
              <div 
                v-if="isPressing"
                class="absolute inset-0 bg-white/20 z-20 pointer-events-none"
              ></div>
            </Transition>
            
            <div v-if="!isEditing" class="relative z-10 text-text-main break-all whitespace-pre-wrap text-sm leading-relaxed" @click="handleCodeCopy">{{ userTextContent }}</div>
            <div v-else class="w-full" @paste="handleEditPaste" @drop="handleEditDrop" @dragover.prevent>
              <!-- Edit Image Previews -->
              <ImageEditorGrid
                :images="editImages"
                :is-processing-image="isProcessingEditImage"
                :is-ocr-processing="isEditOcrProcessing"
                @remove="removeEditImage"
                @ocr="handleEditImageOcr"
              />
              <textarea ref="editTextareaRef" v-model="editText" class="w-full bg-bg-main border border-border-input rounded-md p-2 text-sm focus:outline-none focus:border-text-muted resize-none no-scrollbar min-h-[38px]" rows="1" @keydown="handleKeydown"></textarea>
              <input type="file" ref="editFileInput" class="hidden" multiple accept="image/*" @change="handleEditFileUpload" />
            </div>
          </div>
          <div class="mt-2 flex items-center justify-end gap-3 transition-opacity w-full" :class="[isEditing ? 'opacity-100' : (state.isMobile ? (siblingCount && siblingCount > 1 ? 'opacity-100' : 'opacity-0 h-0 overflow-hidden') : 'opacity-0 group-hover:opacity-100')]">
            <!-- Sibling Navigation -->
            <div v-if="siblingCount && siblingCount > 1" class="flex items-center gap-2 text-[10px] text-text-placeholder select-none">
                <button @click="emit('navigate', nodeId, -1)" :disabled="siblingIndex === 0" class="hover:text-text-main disabled:opacity-30 p-1"><FontAwesomeIcon :icon="['fas', 'chevron-left']" /></button>
                <span>{{ (siblingIndex || 0) + 1 }} / {{ siblingCount }}</span>
                <button @click="emit('navigate', nodeId, 1)" :disabled="siblingIndex === siblingCount! - 1" class="hover:text-text-main disabled:opacity-30 p-1"><FontAwesomeIcon :icon="['fas', 'chevron-right']" /></button>
            </div>
            <template v-if="!isEditing && !state.isMobile">
              <button @click="handleEdit" class="text-text-placeholder hover:text-text-main transition-colors text-xs flex items-center gap-1" title="编辑"><FontAwesomeIcon :icon="['far', 'pen-to-square']" /></button>
              <button @click="handleCopy" class="transition-colors text-xs flex items-center gap-1 h-[18px]" :class="copied ? 'text-success-main' : 'text-text-placeholder hover:text-text-main'" :title="copied ? '已复制' : '复制'">
                <FontAwesomeIcon :icon="copied ? ['fas', 'check'] : ['far', 'copy']" class="text-[11px] w-3 text-center" />
                <Transition name="fade"><span v-if="copied" class="text-[10px]">已复制</span></Transition>
              </button>
            </template>
            <template v-else-if="isEditing">
              <button @click="editFileInput?.click()" class="text-text-placeholder hover:text-text-main transition-colors mr-auto h-8 w-8 flex items-center justify-center rounded-md hover:bg-bg-hover" title="上传图片"><FontAwesomeIcon :icon="['far', 'image']" class="text-base" /></button>
              <button @click="isEditing = false" class="text-xs text-text-muted hover:text-text-main">取消</button>
              <button @click="submitEdit" class="text-xs bg-primary-main text-primary-text px-2 py-1 rounded hover:bg-primary-hover">确认</button>
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
              <FontAwesomeIcon :icon="['fas', 'brain']" class="text-[10px] w-3 text-center" /><span>思考过程</span>
              <FontAwesomeIcon :icon="['fas', 'chevron-right']" class="text-[10px] transition-transform duration-200" :class="isThinkingExpanded ? 'rotate-90' : ''" />
            </div>
            <div v-if="isThinkingExpanded" class="mt-2 px-3 py-2 pl-4 rounded-none text-xs text-text-muted border-l-[3px] border-text-placeholder leading-relaxed whitespace-pre-wrap" style="background-color: var(--bg-hover);">{{ thinkingContent }}</div>
          </div>

          <!-- Assistant content -->
          <div 
            :id="`bubble-${nodeId}-assistant`" 
            class="w-full relative overflow-hidden p-1 -m-1 rounded-lg min-w-0"
            style="touch-action: pan-y;"
            @touchstart="startLongPress"
            @touchend="cancelLongPress"
            @touchmove="cancelLongPress"
            @touchcancel="cancelLongPress"
            @contextmenu.prevent
          >
            <!-- Selected effect -->
            <Transition name="fade">
              <div 
                v-if="isPressing"
                class="absolute inset-0 bg-white/20 z-20 pointer-events-none"
              ></div>
            </Transition>
            
            <!-- Waiting for stream (Animation 1) -->
            <div v-if="message.isStreaming && (!message.assistant || message.assistant.length === 0) && !thinkingContent" class="relative z-10 w-full flex items-center min-h-[32px] px-1">
              <div class="stream-waiting">
                <div class="dot"></div>
                <div class="dot"></div>
                <div class="dot"></div>
              </div>
            </div>
            <template v-for="(item, idx) in message.assistant" :key="idx">
              <!-- Reasoning content (per-segment) -->
              <div v-if="item.role === 'assistant' && segmentThinking[idx]" class="relative z-10 my-2 w-full">
                <div @click="toggleThinkingSegment(idx)" class="flex items-center gap-2 text-xs text-text-placeholder cursor-pointer hover:text-text-muted transition-colors py-1">
                  <FontAwesomeIcon :icon="['fas', 'brain']" class="text-[10px] w-3 text-center" /><span>思考过程</span>
                  <FontAwesomeIcon :icon="['fas', 'chevron-right']" class="text-[10px] transition-transform duration-200" :class="expandedThinkingSegments[idx] ? 'rotate-90' : ''" />
                </div>
                <div v-if="expandedThinkingSegments[idx]" class="mt-2 px-3 py-2 pl-4 rounded-none text-xs text-text-muted border-l-[3px] border-text-placeholder leading-relaxed whitespace-pre-wrap" style="background-color: var(--bg-hover);">{{ segmentThinking[idx] }}</div>
              </div>

              <!-- Text content -->
              <div v-if="item.role === 'assistant' && item.content && segmentHtml[idx]" class="relative z-10 prose prose-sm max-w-none text-text-main break-all" v-html="segmentHtml[idx]" @click="handleContentClick"></div>

              <!-- Tool calls -->
              <template v-if="item.role === 'assistant' && item.tool_calls">
                <div v-for="call in item.tool_calls" :key="call.id" class="relative z-10 my-2 w-full">
                  <div @click="toggleTool(call.id)" class="flex items-center gap-2 text-xs text-text-placeholder cursor-pointer hover:text-text-muted transition-colors py-1">
                    <FontAwesomeIcon :icon="['fas', 'wrench']" class="text-[10px] w-3 text-center" />
                    <span>调用 {{ call.function.name }}</span>
                    <FontAwesomeIcon :icon="['fas', 'chevron-right']" class="text-[10px] transition-transform duration-200" :class="expandedTools[call.id] ? 'rotate-90' : ''" />
                  </div>
                  <div v-if="expandedTools[call.id]" class="mt-1">
                    <div class="text-[11px] font-mono text-text-placeholder break-all whitespace-pre-wrap px-3 py-2 pl-4 rounded-none border-l-[3px] border-text-placeholder" style="background-color: var(--bg-hover);">{{ call.function.arguments }}</div>
                    <div v-for="resp in getToolResponses(call.id)" :key="resp.tool_call_id" class="mt-1 text-[11px] text-text-placeholder whitespace-pre-wrap break-all px-3 py-2 pl-4 rounded-none border-l-[3px] border-text-placeholder" style="background-color: var(--bg-hover);">
                      <span class="text-text-muted font-medium">返回：</span>{{ resp.content }}
                    </div>
                  </div>
                </div>
              </template>
            </template>
            
            <!-- Streaming active cursor (Animation 2) -->
            <div v-if="message.isStreaming && (message.assistant?.length > 0 || thinkingContent)" class="relative z-10 flex items-center mt-2 mb-1 px-1 opacity-80 h-4">
              <span class="stream-cursor"></span>
            </div>
          </div>
          
          <!-- Assistant Actions -->
          <div class="mt-2 flex items-center gap-3 transition-opacity" :class="state.isMobile ? 'opacity-0 h-0 overflow-hidden' : 'opacity-0 group-hover:opacity-100'">
            <button @click="handleCopyAssistant" class="transition-colors text-xs flex items-center gap-1 h-[18px]" :class="copied ? 'text-success-main' : 'text-text-placeholder hover:text-text-main'" :title="copied ? '已复制' : '复制'">
              <FontAwesomeIcon :icon="copied ? ['fas', 'check'] : ['far', 'copy']" class="text-[11px] w-3 text-center" />
              <Transition name="fade"><span v-if="copied" class="text-[10px]">已复制</span></Transition>
            </button>
          </div>
        </div>
      </template>

    </div>

    <!-- Mobile Context Menu -->
    <div v-if="showMobileMenu" class="fixed inset-0 z-1100" @click="showMobileMenu = false" @contextmenu.prevent>
      <div class="fixed inset-0 bg-black/5"></div>
      <div 
        class="absolute bg-bg-panel border border-border-main rounded-lg shadow-xl overflow-hidden animate-in fade-in zoom-in duration-150 py-1" 
        :style="menuStyle"
        @click.stop
      >
        <button @click="handleCopyAction" class="w-full flex items-center gap-3 px-3 py-2 hover:bg-bg-hover transition-colors text-text-main text-sm">
          <FontAwesomeIcon :icon="['far', 'copy']" class="w-4 text-center text-text-muted" />
          <span>复制</span>
        </button>
        <button @click="handleSelectTextAction" class="w-full flex items-center gap-3 px-3 py-2 hover:bg-bg-hover transition-colors text-text-main text-sm">
          <FontAwesomeIcon :icon="['fas', 'i-cursor']" class="w-4 text-center text-text-muted" />
          <span>选择文本</span>
        </button>
        <button v-if="isUser" @click="handleEditAction" class="w-full flex items-center gap-3 px-3 py-2 hover:bg-bg-hover transition-colors text-text-main text-sm">
          <FontAwesomeIcon :icon="['far', 'pen-to-square']" class="w-4 text-center text-text-muted" />
          <span>修改</span>
        </button>
        <button v-else @click="handleRegenerateAction" class="w-full flex items-center gap-3 px-3 py-2 hover:bg-bg-hover transition-colors text-text-main text-sm">
          <FontAwesomeIcon :icon="['fas', 'rotate-right']" class="w-4 text-center text-text-muted" />
          <span>重新生成</span>
        </button>
      </div>
    </div>


  </div>
</template>

<style scoped>
.stream-waiting {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 4px;
}
.stream-waiting .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: var(--primary);
  animation: pulse-dot 1.4s infinite ease-in-out both;
}
.stream-waiting .dot:nth-child(1) { animation-delay: -0.32s; }
.stream-waiting .dot:nth-child(2) { animation-delay: -0.16s; }
.stream-waiting .dot:nth-child(3) { animation-delay: 0s; }

@keyframes pulse-dot {
  0%, 80%, 100% { transform: scale(0); opacity: 0.3; }
  40% { transform: scale(1); opacity: 1; }
}

.stream-cursor {
  display: inline-block;
  width: 6px;
  height: 14px;
  background-color: var(--primary);
  border-radius: 1px;
  animation: blink 1s step-end infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
</style>
