<script lang="ts">
import { marked } from 'marked';
import katex from 'katex';
import 'katex/dist/katex.min.css';
import hljs from 'highlight.js/lib/common';
import '../hljs-theme.css';

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
<div class="code-block-wrapper my-4 border-[0.5px] border-border-main rounded-md overflow-hidden bg-bg-main" style="touch-action: pan-x pan-y;">
  <div class="flex justify-between items-center bg-bg-panel px-3 py-1.5 border-b-[0.5px] border-border-main">
    <span class="text-[10px] font-medium text-text-placeholder uppercase tracking-wider">${lang}</span>
    <button class="copy-code-btn text-text-placeholder hover:text-text-main transition-colors flex items-center gap-1" title="复制代码">
      <i class="far fa-copy text-[10px]"></i>
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
import { processImage } from '../utils/image';

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
  if (!state.isMobile) return;
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
  if (!state.isMobile) return;
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
const editImages = ref<string[]>([]);
const editFileInput = ref<HTMLInputElement | null>(null);

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
    }, 600);
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
  return props.message.find((c: any) => c.type === 'text')?.text || '';
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
    Object.assign(segmentHtml, pendingUpdate);
    pendingUpdate = null;
  }
  if (pendingThinkingSegmentsUpdate) {
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
        const r = marked.parse(item.content) as string;
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
  
  if (hasChanges) {
    if (state.isTextSelected || state.isMouseDown) {
      pendingUpdate = map;
    } else {
      Object.assign(segmentHtml, map);
      pendingUpdate = null;
    }
  }
  if (hasThinkingChanges) {
    if (state.isTextSelected || state.isMouseDown) {
      pendingThinkingSegmentsUpdate = thinkingMap;
    } else {
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
  if (!props.isUser) return [];
  return props.message.filter((c: any) => c.type === 'image_url').map((c: any) => c.image_url.url);
});

const getToolResponses = (callId: string) => {
  if (props.isUser) return [];
  return props.message.assistant.filter((m: any) => m.role === 'tool' && m.tool_call_id === callId);
};

const handleCopy = () => { navigator.clipboard.writeText(userTextContent.value); };
const handleCopyAssistant = () => {
  if (props.isUser || !props.message?.assistant) return;
  const text = props.message.assistant
    .filter((m: any) => m.role === 'assistant' && m.content)
    .map((m: any) => m.content.trim())
    .filter((c: string) => c.length > 0)
    .join('\n\n');
  navigator.clipboard.writeText(text);
};
const handleEdit = () => { 
  isEditing.value = true; 
  editText.value = userTextContent.value; 
  editImages.value = [...images.value];
  nextTick(adjustEditHeight); 
};

const addEditFiles = async (files: File[]) => {
  for (const file of files) {
    if (editImages.value.length >= 10) break;
    if (file.type.startsWith('image/')) {
      const base64 = await processImage(file);
      editImages.value.push(base64);
    }
  }
};

const handleEditFileUpload = async (e: Event) => {
  const files = (e.target as HTMLInputElement).files;
  if (files) {
    await addEditFiles(Array.from(files));
  }
};

const handleEditPaste = async (e: ClipboardEvent) => {
  const items = e.clipboardData?.items;
  if (items) {
    const files = [];
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.indexOf('image') !== -1) {
        const file = items[i].getAsFile();
        if (file) files.push(file);
      }
    }
    await addEditFiles(files);
  }
};

const handleEditDrop = async (e: DragEvent) => {
  e.preventDefault();
  const files = e.dataTransfer?.files;
  if (files) {
    await addEditFiles(Array.from(files));
  }
};

const removeEditImage = (index: number) => {
  editImages.value.splice(index, 1);
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

const handleCodeCopy = (e: MouseEvent) => {
  const target = e.target as HTMLElement;
  const btn = target.closest('.copy-code-btn');
  if (!btn) return;
  
  const wrapper = btn.closest('.code-block-wrapper');
  const codeElement = wrapper?.querySelector('code');
  if (codeElement) {
    const code = codeElement.textContent || '';
    navigator.clipboard.writeText(code).then(() => {
      const icon = btn.querySelector('i');
      const text = btn.querySelector('span');
      if (icon && text) {
        const originalIconClass = icon.className;
        const originalText = text.textContent;
        icon.className = 'fas fa-check text-[10px] text-green-500';
        text.textContent = '已复制';
        setTimeout(() => {
          icon.className = originalIconClass;
          text.textContent = originalText;
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
  <div class="flex flex-col mb-6" :class="isUser ? 'items-end' : 'items-start'">
    <div class="flex flex-col min-w-0" :class="isUser ? (isEditing ? 'w-full items-start' : 'w-fit max-w-[85%] md:max-w-[75%] items-end self-end') : 'w-full items-start'">

      <template v-if="isUser">
        <div class="group flex flex-col min-w-0" :class="isEditing ? 'w-full items-start' : 'max-w-full items-end'">
          
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
                class="absolute inset-0 bg-white/20 z-0"
              ></div>
            </Transition>
            <img v-for="(url, idx) in images" :key="idx" :src="url" @click="state.previewImageUrl = url" class="relative z-10 max-w-[200px] max-h-[200px] rounded-md border border-border-main cursor-pointer" />
          </div>

          <!-- Text Bubble Section -->
          <div 
            v-if="userTextContent || isEditing"
            class="relative p-4 rounded-lg shadow-sm bg-bg-panel rounded-tr-none transition-all duration-200 overflow-hidden" 
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
                class="absolute inset-0 bg-white/20 z-0"
              ></div>
            </Transition>
            
            <div v-if="!isEditing" class="relative z-10 text-text-main break-all whitespace-pre-wrap text-sm leading-relaxed" @click="handleCodeCopy">{{ userTextContent }}</div>
            <div v-else class="w-full" @paste="handleEditPaste" @drop="handleEditDrop" @dragover.prevent>
              <!-- Edit Image Previews -->
              <div v-if="editImages.length > 0" class="flex flex-wrap gap-2 mb-3">
                <div v-for="(img, index) in editImages" :key="index" class="relative group w-16 h-16 rounded-md overflow-hidden border border-border-main">
                  <img :src="img" class="w-full h-full object-cover" />
                  <button 
                    @click="removeEditImage(index)"
                    class="absolute top-0 right-0 bg-black/50 text-white w-5 h-5 flex items-center justify-center rounded-bl-md opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    <i class="fas fa-times text-[10px]"></i>
                  </button>
                </div>
              </div>
              <textarea ref="editTextareaRef" v-model="editText" class="w-full bg-bg-main border border-border-input rounded-md p-2 text-sm focus:outline-none focus:border-text-muted resize-none no-scrollbar min-h-[38px]" rows="1" @keydown="handleKeydown"></textarea>
              <input type="file" ref="editFileInput" class="hidden" multiple accept="image/*" @change="handleEditFileUpload" />
            </div>
          </div>
          <div class="mt-2 flex items-center justify-end gap-3 transition-opacity w-full" :class="[isEditing ? 'opacity-100' : (state.isMobile ? (siblingCount && siblingCount > 1 ? 'opacity-100' : 'opacity-0 h-0 overflow-hidden') : 'opacity-0 group-hover:opacity-100')]">
            <!-- Sibling Navigation -->
            <div v-if="siblingCount && siblingCount > 1" class="flex items-center gap-2 text-[10px] text-text-placeholder select-none">
              <button @click="emit('navigate', nodeId, -1)" :disabled="siblingIndex === 0" class="hover:text-text-main disabled:opacity-30 p-1"><i class="fas fa-chevron-left"></i></button>
              <span>{{ (siblingIndex || 0) + 1 }} / {{ siblingCount }}</span>
              <button @click="emit('navigate', nodeId, 1)" :disabled="siblingIndex === siblingCount! - 1" class="hover:text-text-main disabled:opacity-30 p-1"><i class="fas fa-chevron-right"></i></button>
            </div>
            <template v-if="!isEditing && !state.isMobile">
              <button @click="handleEdit" class="text-text-placeholder hover:text-text-main transition-colors text-xs flex items-center gap-1" title="编辑"><i class="far fa-edit"></i></button>
              <button @click="handleCopy" class="text-text-placeholder hover:text-text-main transition-colors text-xs flex items-center gap-1" title="复制"><i class="far fa-copy"></i></button>
            </template>
            <template v-else-if="isEditing">
              <button @click="editFileInput?.click()" class="text-text-placeholder hover:text-text-main transition-colors mr-auto h-8 w-8 flex items-center justify-center rounded-md hover:bg-bg-hover" title="上传图片"><i class="far fa-image text-base"></i></button>
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
              <i class="fas fa-brain text-[10px] w-3 text-center"></i><span>思考过程</span>
              <i class="fas fa-chevron-right text-[10px] transition-transform duration-200" :class="isThinkingExpanded ? 'rotate-90' : ''"></i>
            </div>
            <div v-if="isThinkingExpanded" class="mt-2 p-4 bg-bg-panel rounded-lg text-xs text-text-muted border-l-2 border-border-main leading-relaxed italic whitespace-pre-wrap shadow-sm">{{ thinkingContent }}</div>
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
                class="absolute inset-0 bg-white/20 z-0"
              ></div>
            </Transition>
            <template v-for="(item, idx) in message.assistant" :key="idx">
              <!-- Reasoning content (per-segment) -->
              <div v-if="item.role === 'assistant' && segmentThinking[idx]" class="relative z-10 my-2 w-full">
                <div @click="toggleThinkingSegment(idx)" class="flex items-center gap-2 text-xs text-text-placeholder cursor-pointer hover:text-text-muted transition-colors py-1">
                  <i class="fas fa-brain text-[10px] w-3 text-center"></i><span>思考过程</span>
                  <i class="fas fa-chevron-right text-[10px] transition-transform duration-200" :class="expandedThinkingSegments[idx] ? 'rotate-90' : ''"></i>
                </div>
                <div v-if="expandedThinkingSegments[idx]" class="mt-2 p-4 bg-bg-panel rounded-lg text-xs text-text-muted border-l-2 border-border-main leading-relaxed italic whitespace-pre-wrap shadow-sm">{{ segmentThinking[idx] }}</div>
              </div>

              <!-- Text content -->
              <div v-if="item.role === 'assistant' && item.content && segmentHtml[idx]" class="relative z-10 prose prose-sm max-w-none text-text-main break-all" v-html="segmentHtml[idx]" @click="handleContentClick"></div>

              <!-- Tool calls -->
              <template v-if="item.role === 'assistant' && item.tool_calls">
                <div v-for="call in item.tool_calls" :key="call.id" class="relative z-10 my-2 w-full">
                  <div @click="toggleTool(call.id)" class="flex items-center gap-2 text-xs text-text-placeholder cursor-pointer hover:text-text-muted transition-colors py-1">
                    <i class="fas fa-wrench text-[10px] w-3 text-center"></i>
                    <span>调用 {{ call.function.name }}</span>
                    <i class="fas fa-chevron-right text-[10px] transition-transform duration-200" :class="expandedTools[call.id] ? 'rotate-90' : ''"></i>
                  </div>
                  <div v-if="expandedTools[call.id]" class="pl-5 pb-1 mt-1">
                    <div class="text-[11px] font-mono text-text-placeholder break-all whitespace-pre-wrap bg-bg-panel p-2 rounded">{{ call.function.arguments }}</div>
                    <div v-for="resp in getToolResponses(call.id)" :key="resp.tool_call_id" class="mt-1 text-[11px] text-text-placeholder whitespace-pre-wrap break-all bg-bg-panel p-2 rounded">
                      <span class="text-text-muted font-medium">返回：</span>{{ resp.content }}
                    </div>
                  </div>
                </div>
              </template>
            </template>
          </div>
          
          <!-- Assistant Actions -->
          <div class="mt-2 flex items-center gap-3 transition-opacity" :class="state.isMobile ? 'opacity-0 h-0 overflow-hidden' : 'opacity-0 group-hover:opacity-100'">
            <button @click="handleCopyAssistant" class="text-text-placeholder hover:text-text-main transition-colors text-xs flex items-center gap-1" title="复制"><i class="far fa-copy"></i></button>
          </div>
        </div>
      </template>

    </div>

    <!-- Mobile Context Menu -->
    <div v-if="showMobileMenu" class="fixed inset-0 z-[1100]" @click="showMobileMenu = false" @contextmenu.prevent>
      <div class="fixed inset-0 bg-black/5"></div>
      <div 
        class="absolute bg-bg-panel border border-border-main rounded-lg shadow-xl overflow-hidden animate-in fade-in zoom-in duration-150 py-1" 
        :style="menuStyle"
        @click.stop
      >
        <button @click="handleCopyAction" class="w-full flex items-center gap-3 px-3 py-2 hover:bg-bg-hover transition-colors text-text-main text-sm">
          <i class="far fa-copy w-4 text-center text-text-muted"></i>
          <span>复制</span>
        </button>
        <button @click="handleSelectTextAction" class="w-full flex items-center gap-3 px-3 py-2 hover:bg-bg-hover transition-colors text-text-main text-sm">
          <i class="fas fa-i-cursor w-4 text-center text-text-muted"></i>
          <span>选择文本</span>
        </button>
        <button v-if="isUser" @click="handleEditAction" class="w-full flex items-center gap-3 px-3 py-2 hover:bg-bg-hover transition-colors text-text-main text-sm">
          <i class="far fa-edit w-4 text-center text-text-muted"></i>
          <span>修改</span>
        </button>
        <button v-else @click="handleRegenerateAction" class="w-full flex items-center gap-3 px-3 py-2 hover:bg-bg-hover transition-colors text-text-main text-sm">
          <i class="fas fa-rotate-right w-4 text-center text-text-muted"></i>
          <span>重新生成</span>
        </button>
      </div>
    </div>
  </div>
</template>

<style>
@reference "tailwindcss";

.math-block {
  width: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 0.5rem 0;
  margin: 0.5rem 0;
}

.math-block .katex-display {
  margin: 0;
  text-align: center;
  min-width: 100%;
}

.prose pre { @apply bg-transparent p-0 m-0 border-none rounded-none overflow-x-auto; }
.prose code { @apply text-[0.85em] font-mono; }
.prose :not(pre) > code {
  background-color: var(--bg-panel);
  color: var(--text-main);
  border: 1px solid var(--border-color);
  @apply px-1.5 py-0.5 rounded mx-0.5;
}
.prose p { @apply mb-3 last:mb-0 leading-relaxed; }
.prose ul, .prose ol { @apply ml-6 mb-4 mt-2 list-outside; }
.prose ul { @apply list-disc; }
.prose ol { @apply list-decimal; }
.prose li { @apply mb-1.5; }
.prose li > p { @apply mb-1; }
.prose li > ul, .prose li > ol { @apply mt-1 mb-2; }

.prose h1, .prose h2, .prose h3, .prose h4, .prose h5, .prose h6 {
  color: var(--text-main);
  @apply font-bold mt-6 mb-3 leading-tight;
}
.prose h1 { 
  @apply text-xl pb-2; 
  border-bottom: 1px solid var(--border-color);
}
.prose h2 { 
  @apply text-lg pb-1; 
  border-bottom: 1px solid var(--border-color);
}
.prose h3 { @apply text-base; }

.prose blockquote {
  border-left: 4px solid var(--border-color);
  background-color: var(--bg-panel);
  color: var(--text-muted);
  @apply pl-4 py-1 my-4 rounded-r-sm;
}

.table-wrapper {
  @apply my-4 border rounded-md overflow-x-auto w-full;
  border-color: var(--border-color);
  touch-action: pan-x pan-y;
}

.prose table {
  @apply w-full border-collapse text-sm table;
  min-width: max-content;
}
.prose thead {
  background-color: var(--bg-panel);
  @apply text-left;
}
.prose th {
  @apply px-4 py-2 font-semibold;
  border-bottom: 1px solid var(--border-color);
}
.prose td {
  @apply px-4 py-2;
  border-bottom: 1px solid var(--border-color);
}
.prose tr:last-child td {
  @apply border-b-0;
}
.prose tr:nth-child(even) {
  background-color: rgba(0, 0, 0, 0.02);
}
@media (prefers-color-scheme: dark) {
  .prose tr:nth-child(even) {
    background-color: rgba(255, 255, 255, 0.02);
  }
}

.prose a {
  color: var(--primary);
  @apply hover:underline decoration-1 underline-offset-4;
}

.prose hr {
  @apply my-6;
  border-top: 1px solid var(--border-color);
}

.prose strong {
  @apply font-semibold;
  color: var(--text-main);
}

.prose em {
  @apply italic;
}

.prose img {
  @apply cursor-pointer rounded-md;
}

/* Code block wrapper adjustments */
.code-block-wrapper pre code.hljs {
  @apply bg-transparent p-0;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
