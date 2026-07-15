<script lang="ts">
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import katex from 'katex';
import 'katex/dist/katex.min.css';
import hljs from 'highlight.js/lib/common';

let mermaidModule: any = null;
let mermaidModulePromise: Promise<any> | null = null;
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
      
      if (lang === 'mermaid') {
        const fenceMatch = token.raw.match(/^(?:```+|~~~+)/);
        const isComplete = fenceMatch && token.raw.trimEnd().endsWith(fenceMatch[0]);
        const completeClass = isComplete ? 'mermaid-complete' : 'mermaid-incomplete';

        const escapedCode = token.text
          .replace(/&/g, '&amp;')
          .replace(/"/g, '&quot;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;');
        const cachedSvg = typeof mermaidModule !== 'undefined' && mermaidModule ? mermaidModule.getCachedMermaidSvg(token.text) : undefined;
        const chartContent = cachedSvg || `<div class="mermaid-placeholder"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="14" height="14" fill="currentColor" class="mermaid-placeholder-icon"><path d="M222.7 32.1c5 16.9-4.6 34.8-21.5 39.8C164.9 86.6 128 137.3 128 197.4c0 5.6-.3 11.1-.8 16.6H384.8c-.5-5.5-.8-11.1-.8-16.6 0-60.1-36.9-110.8-72.2-125.5-16.9-5-26.5-22.9-21.5-39.8C297.9-2.2 320 12 320 32.1V48H192V32.1c0-20.1 22.1-34.3 30.7-0zM128 256H32v224c0 17.7 14.3 32 32 32H320V256H128zm352 224c17.7 0 32-14.3 32-32V256H384V480h96z"/></svg><span>图表生成中...</span></div>`;

        return `<div class="mermaid-block ${completeClass} my-4 border-[0.5px] border-border-main rounded-md overflow-hidden bg-code-bg">
  <div class="flex justify-between items-center bg-bg-panel px-3 py-1.5 border-b-[0.5px] border-border-main">
    <span class="text-[10px] font-medium text-text-placeholder uppercase tracking-wider">mermaid</span>
    <div class="flex items-center gap-2">
      <button class="mermaid-toggle-btn text-text-placeholder hover:text-text-main transition-colors flex items-center gap-1" title="切换显示">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 512" class="toggle-icon-svg" width="10" height="10" fill="currentColor"><path d="M392.8 1.2c-17-4.9-34.7 5-39.6 22l-128 448c-4.9 17 5 34.7 22 39.6s34.7-5 39.6-22l128-448c4.9-17-5-34.7-22-39.6zm80.6 120.1c-12.5 12.5-12.5 32.8 0 45.3L562.7 256l-89.4 89.4c-12.5 12.5-12.5 32.8 0 45.3s32.8 12.5 45.3 0l112-112c12.5-12.5 12.5-32.8 0-45.3l-112-112c-12.5-12.5-32.8-12.5-45.3 0zm-271 0c-12.5-12.5-32.8-12.5-45.3 0l-112 112c-12.5 12.5-12.5 32.8 0 45.3l112 112c12.5 12.5 32.8 12.5 45.3 0s12.5-32.8 0-45.3L77.3 256l89.4-89.4c12.5-12.5 12.5-32.8 0-45.3z"/></svg>
        <span class="toggle-text text-[10px]">文字</span>
      </button>
      <button class="copy-mermaid-btn text-text-placeholder hover:text-text-main transition-colors flex items-center gap-1" title="复制代码">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" class="copy-icon-svg" width="10" height="10" fill="currentColor"><path d="M64 464H288c8.8 0 16-7.2 16-16V384h48v64c0 35.3-28.7 64-64 64H64c-35.3 0-64-28.7-64-64V224c0-35.3 28.7-64 64-64h64v48H64c-8.8 0-16 7.2-16 16V448c0 8.8 7.2 16 16 16zM224 304H448c8.8 0 16-7.2 16-16V64c0-8.8-7.2-16-16-16H224c-8.8 0-16 7.2-16 16V288c0 8.8 7.2 16 16 16zm-64-16V64c0-35.3 28.7-64 64-64H448c35.3 0 64 28.7 64 64V288c0 35.3-28.7 64-64 64H224c-35.3 0-64-28.7-64-64z"/></svg>
        <span class="text-[10px]">复制</span>
      </button>
    </div>
  </div>
  <div class="mermaid-content">
    <div class="mermaid-chart">${chartContent}</div>
    <pre class="mermaid-source !m-0 !p-3 !bg-code-bg overflow-x-auto"><code class="hljs language-mermaid">${escapedCode}</code></pre>
  </div>
</div>`;
      }

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
import { ref, computed, watch, nextTick, reactive, onBeforeUpdate, onUpdated, onMounted, onBeforeUnmount } from 'vue';
import { state } from '../store';
import { useImageEditor } from '../composables/useImageEditor';
import { useLongPress } from '../composables/useLongPress';
import FileEditorGrid from './FileEditorGrid.vue';

const MERMAID_RE = /<div class="mermaid-placeholder" data-code="([^"]*)" style="min-height: 2rem;"><\/div>/g;
function protectMermaid(html: string): { html: string; restore: (h: string) => string } {
  const codes = new Map<string, string>();
  let idx = 0;
  const processed = html.replace(MERMAID_RE, (_, code) => { const k = `__MRM_${idx++}__`; codes.set(k, code); return k; });
  return { html: processed, restore: (h: string) => { for (const [k, c] of codes) h = h.replace(k, `<div class="mermaid-placeholder" data-code="${c}" style="min-height: 2rem;"></div>`); return h; } };
}


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
  // mermaid 代码块在 marked 解析器完成围栏闭合后才输出，流式期间也可安全渲染
  if (mermaidModule) {
    mermaidModule.renderMermaidPlaceholders();
  } else if (mermaidModulePromise) {
    mermaidModulePromise.then(m => m.renderMermaidPlaceholders());
  } else {
    if (!document.querySelector('.mermaid-block.mermaid-complete:not(.rendered)')) return;
    mermaidModulePromise = import('../utils/mermaid').then(m => {
      mermaidModule = m;
      return m;
    });
    mermaidModulePromise.then(m => m.renderMermaidPlaceholders());
  }
});

onMounted(() => {
  if (!mermaidModulePromise && document.querySelector('.mermaid-block.mermaid-complete:not(.rendered)')) {
    mermaidModulePromise = import('../utils/mermaid').then(m => {
      mermaidModule = m;
      return m;
    });
  }
  mermaidModulePromise?.then(m => m.renderMermaidPlaceholders());
});



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
  preScrollPositions.clear();
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
} = useLongPress({ menuWidth: 160, menuHeight: 200 });

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
    const hasThinkingText = thinkingContent.value || Object.values(segmentThinking).some(s => s && s.trim());
    if ((hasAssistantText || hasThinkingText) && target.closest('img')) return;
  }
  
  startLongPressBase(e);
};

const handleCopyAction = () => {
  if (props.isUser) handleCopy();
  else handleCopyAssistant();
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
        let r: string;
        if (raw.includes('mermaid-placeholder')) {
          const { html, restore } = protectMermaid(raw);
          r = restore(DOMPurify.sanitize(html));
        } else {
          r = DOMPurify.sanitize(raw);
        }
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
  
  // 处理mermaid切换按钮
  const toggleBtn = target.closest('.mermaid-toggle-btn');
  if (toggleBtn) {
    e.stopPropagation();
    const block = toggleBtn.closest('.mermaid-block');
    if (block) {
      const content = block.querySelector('.mermaid-content');
      const toggleText = toggleBtn.querySelector('.toggle-text');
      const toggleIcon = toggleBtn.querySelector('.toggle-icon-svg');
      if (content && toggleText && toggleIcon) {
        content.classList.toggle('show-source');
        const isSource = content.classList.contains('show-source');
        toggleText.textContent = isSource ? '图表' : '文字';
        // 切换图标：代码图标 <-> 图表图标
        if (isSource) {
          toggleIcon.innerHTML = '<path d="M32 32c17.7 0 32 14.3 32 32V400c0 8.8 7.2 16 16 16H480c17.7 0 32 14.3 32 32s-14.3 32-32 32H80c-35.3 0-64-28.7-64-64V64C16 46.3 30.3 32 48 32H32zm96 96c17.7 0 32 14.3 32 32V352c0 17.7-14.3 32-32 32s-32-14.3-32-32V160c0-17.7 14.3-32 32-32zm160 64c17.7 0 32 14.3 32 32V352c0 17.7-14.3 32-32 32s-32-14.3-32-32V224c0-17.7 14.3-32 32-32zm96 32c17.7 0 32 14.3 32 32V352c0 17.7-14.3 32-32 32s-32-14.3-32-32V256c0-17.7 14.3-32 32-32z"/>';
        } else {
          toggleIcon.innerHTML = '<path d="M392.8 1.2c-17-4.9-34.7 5-39.6 22l-128 448c-4.9 17 5 34.7 22 39.6s34.7-5 39.6-22l128-448c4.9-17-5-34.7-22-39.6zm80.6 120.1c-12.5 12.5-12.5 32.8 0 45.3L562.7 256l-89.4 89.4c-12.5 12.5-12.5 32.8 0 45.3s32.8 12.5 45.3 0l112-112c12.5-12.5 12.5-32.8 0-45.3l-112-112c-12.5-12.5-32.8-12.5-45.3 0zm-271 0c-12.5-12.5-32.8-12.5-45.3 0l-112 112c-12.5 12.5-12.5 32.8 0 45.3l112 112c12.5 12.5 32.8 12.5 45.3 0s12.5-32.8 0-45.3L77.3 256l89.4-89.4c12.5-12.5 12.5-32.8 0-45.3z"/>';
        }
      }
    }
    return;
  }
  
  // 处理mermaid复制按钮
  const copyMermaidBtn = target.closest('.copy-mermaid-btn');
  if (copyMermaidBtn) {
    e.stopPropagation();
    const block = copyMermaidBtn.closest('.mermaid-block');
    if (block) {
      const codeElement = block.querySelector('.mermaid-source code');
      if (codeElement) {
        const code = codeElement.textContent || '';
        navigator.clipboard.writeText(code).then(() => {
          const textEl = copyMermaidBtn.querySelector('span');
          if (textEl) {
            const original = textEl.textContent;
            textEl.textContent = '已复制';
            setTimeout(() => { textEl.textContent = original }, 2000);
          }
        });
      }
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
            @contextmenu="(state.isMobile && !userTextContent && !isEditing) ? $event.preventDefault() : null"
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
            @contextmenu="state.isMobile ? $event.preventDefault() : null"
          >
            <!-- Selected effect for text bubble -->
            <Transition name="fade">
              <div 
                v-if="isPressing"
                class="absolute inset-0 bg-white/20 z-20 pointer-events-none"
              ></div>
            </Transition>
            
            <div v-if="!isEditing" class="relative z-10 text-text-main wrap-anywhere whitespace-pre-wrap text-sm leading-relaxed" @click="handleCodeCopy">{{ userTextContent }}</div>
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
              <textarea ref="editTextareaRef" v-model="editText" maxlength="1000000" class="w-full bg-bg-main border border-border-input rounded-md p-2 text-sm focus:outline-none focus:border-text-muted resize-none no-scrollbar min-h-[38px]" rows="1" @keydown="handleKeydown"></textarea>
              <input type="file" ref="editFileInput" class="hidden" multiple accept="image/*,audio/*,.pdf,.docx,.xlsx,.pptx,.doc,.xls,.ppt,.txt,.md,.json,.xml,.yaml,.yml,.csv,.html,.rtf,.log,.ini,.cfg,.conf,.sh,.bat,.py,.js,.ts,.css,.vue,.tsx,.jsx,.go,.rs,.toml,.env,.gitignore" @change="handleEditFileUpload" />
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
              <button @click="editFileInput?.click()" class="text-text-placeholder hover:text-text-main transition-colors mr-auto h-8 w-8 flex items-center justify-center rounded-md hover:bg-bg-hover" title="上传文件"><FontAwesomeIcon :icon="['far', 'folder']" class="text-base" /></button>
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
            <div v-if="isThinkingExpanded" @dblclick="isThinkingExpanded = false" class="mt-2 px-3 py-2 pl-4 rounded-none text-xs text-text-muted border-l-[3px] border-text-placeholder leading-relaxed whitespace-pre-wrap" style="background-color: var(--bg-hover);">{{ thinkingContent }}</div>
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
            @contextmenu="state.isMobile ? $event.preventDefault() : null"
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
                  <FontAwesomeIcon :icon="['fas', 'chevron-right']" class="text-[10px] transition-transform duration-200" :class="isThinkingSegmentExpanded(idx) ? 'rotate-90' : ''" />
                </div>
                <div v-if="isThinkingSegmentExpanded(idx)" @dblclick="thinkingOverrides[idx] = false" class="mt-2 px-3 py-2 pl-4 rounded-none text-xs text-text-muted border-l-[3px] border-text-placeholder leading-relaxed whitespace-pre-wrap" style="background-color: var(--bg-hover);">{{ segmentThinking[idx] }}</div>
              </div>

              <!-- Text content -->
              <div v-if="item.role === 'assistant' && item.content && segmentHtml[idx]" class="relative z-10 prose prose-sm max-w-none text-text-main wrap-anywhere" v-html="segmentHtml[idx]" @click="handleContentClick"></div>

              <!-- Tool calls -->
              <template v-if="item.role === 'assistant' && item.tool_calls">
                <div v-for="call in item.tool_calls" :key="call.id" class="relative z-10 my-2 w-full">
                  <div @click="toggleTool(call.id)" class="flex items-center gap-2 text-xs text-text-placeholder cursor-pointer hover:text-text-muted transition-colors py-1">
                    <FontAwesomeIcon :icon="['fas', 'wrench']" class="text-[10px] w-3 text-center" />
                    <span>调用 {{ call.function.name }}</span>
                    <FontAwesomeIcon :icon="['fas', 'chevron-right']" class="text-[10px] transition-transform duration-200" :class="isToolExpanded(call.id) ? 'rotate-90' : ''" />
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
    <div v-if="showMobileMenu" class="fixed inset-0 z-1100" @click="closeMenu" @contextmenu.prevent>
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
