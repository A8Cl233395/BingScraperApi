<script lang="ts">
import { marked } from 'marked';
import markedKatex from 'marked-katex-extension';
marked.use(markedKatex({ throwOnError: false }));

marked.use({
  breaks: true,
  gfm: true,
  renderer: {
    code(token) {
      const lang = token.lang || 'text';
      const escapedCode = token.text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
      return `
<div class="code-block-wrapper my-4 border-[0.5px] border-border-main rounded-md overflow-hidden bg-bg-main">
  <div class="flex justify-between items-center bg-bg-panel px-3 py-1.5 border-b-[0.5px] border-border-main">
    <span class="text-[10px] font-medium text-text-placeholder uppercase tracking-wider">${lang}</span>
    <button class="copy-code-btn text-text-placeholder hover:text-text-main transition-colors flex items-center gap-1" title="复制代码">
      <i class="far fa-copy text-[10px]"></i>
      <span class="text-[10px]">复制</span>
    </button>
  </div>
  <pre class="!m-0 !p-3 !bg-code-bg overflow-x-auto"><code class="hljs language-${lang}">${escapedCode}</code></pre>
</div>`;
    }
  }
});
</script>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick, onUnmounted } from 'vue';
import hljs from 'highlight.js/lib/common';
import 'highlight.js/styles/github.css';
import 'katex/dist/katex.min.css';
import { isMobileDevice } from '../utils/device';


const props = defineProps<{
  message: any;
  nodeId: string;
  isUser: boolean;
  siblingCount?: number;
  siblingIndex?: number;
}>();

const emit = defineEmits(['navigate', 'edit']);

const isThinkingExpanded = ref(false);
const expandedTools = ref<Record<string, boolean>>({});
const toggleTool = (id: string) => {
  expandedTools.value[id] = !expandedTools.value[id];
};
const isEditing = ref(false);
const editText = ref('');

// === USER message rendering ===
const userRenderedHtml = ref('');
const userTextContent = computed(() => {
  if (!props.isUser) return '';
  return props.message.find((c: any) => c.type === 'text')?.text || '';
});

watch(userTextContent, async (val) => {
  if (!val) { userRenderedHtml.value = ''; return; }
  try {
    const r = marked.parse(val);
    userRenderedHtml.value = r instanceof Promise ? await r : r;
  } catch { userRenderedHtml.value = val; }
  nextTick(() => highlightAndMath());
}, { immediate: true });

// === ASSISTANT message rendering (per-segment) ===
const segmentHtml = ref<Record<number | string, string>>({});
const thinkingContent = ref('');

let pendingUpdate: Record<number, string> | null = null;
let pendingThinkingUpdate: string | null = null;

const handleSelectionChange = () => {
  const selection = window.getSelection();
  const hasSelection = selection && !selection.isCollapsed;
  if (!hasSelection) {
    let changed = false;
    if (pendingUpdate) {
      segmentHtml.value = pendingUpdate;
      pendingUpdate = null;
      changed = true;
    }
    if (pendingThinkingUpdate !== null) {
      thinkingContent.value = pendingThinkingUpdate;
      pendingThinkingUpdate = null;
      changed = true;
    }
    if (changed) {
      nextTick(() => highlightAndMath());
    }
  }
};

watch(() => props.isUser ? null : props.message?.assistant, async (arr) => {
  if (props.isUser || !arr) return;
  const map: Record<number, string> = {};
  for (let i = 0; i < arr.length; i++) {
    const item = arr[i];
    if (item.role === 'assistant' && item.content) {
      try {
        const r = marked.parse(item.content);
        map[i] = r instanceof Promise ? await r : r;
      } catch { map[i] = item.content; }
    }
  }
  
  const selection = window.getSelection();
  const hasSelection = selection && !selection.isCollapsed;
  
  if (hasSelection) {
    pendingUpdate = map;
  } else {
    segmentHtml.value = map;
    pendingUpdate = null;
    nextTick(() => highlightAndMath());
  }
}, { deep: true, immediate: true });

watch(() => props.isUser ? null : props.message?.thinking, (val) => {
  if (props.isUser) return;
  const content = val || '';
  const selection = window.getSelection();
  const hasSelection = selection && !selection.isCollapsed;
  
  if (hasSelection) {
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
    .map((m: any) => m.content)
    .join('');
  navigator.clipboard.writeText(text);
};
const handleEdit = () => { isEditing.value = true; editText.value = userTextContent.value; nextTick(adjustEditHeight); };
const submitEdit = () => { emit('edit', props.nodeId, editText.value); isEditing.value = false; };
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

const highlightAndMath = () => {
  const container = document.getElementById(`bubble-${props.nodeId}-${props.isUser ? 'user' : 'assistant'}`);
  if (!container) return;
  container.querySelectorAll('pre code').forEach((block) => {
    hljs.highlightElement(block as HTMLElement);
  });
};

onMounted(() => {
  document.addEventListener('selectionchange', handleSelectionChange);
  nextTick(() => highlightAndMath());
});

onUnmounted(() => {
  document.removeEventListener('selectionchange', handleSelectionChange);
});
</script>

<template>
  <div class="flex flex-col mb-6" :class="isUser ? 'items-end' : 'items-start'">
    <div class="flex flex-col transition-all duration-300" :class="isUser ? (isEditing ? 'w-full items-start' : 'max-w-[85%] md:max-w-[75%] items-end self-end') : 'w-full items-start'">

      <!-- ====== USER MESSAGE ====== -->
      <template v-if="isUser">
        <div class="group flex flex-col w-full" :class="isEditing ? 'items-start' : 'items-end'">
          <div class="relative p-4 rounded-lg shadow-sm bg-bg-panel rounded-tr-none transition-all duration-200" :class="isEditing ? 'w-full' : ''">
            <div v-if="images.length > 0" class="flex flex-wrap gap-2 mb-3">
              <img v-for="(url, idx) in images" :key="idx" :src="url" class="max-w-[200px] max-h-[200px] rounded-md border border-border-main" />
            </div>
            <div v-if="!isEditing" :id="`bubble-${nodeId}-user`" class="prose prose-sm max-w-none text-text-main break-words" v-html="userRenderedHtml" @click="handleCodeCopy"></div>
            <div v-else class="w-full">
              <textarea ref="editTextareaRef" v-model="editText" class="w-full bg-bg-main border border-border-input rounded-md p-2 text-sm focus:outline-none focus:border-text-muted resize-none no-scrollbar min-h-[38px]" rows="1" @keydown="handleKeydown"></textarea>
            </div>
          </div>
          <div class="mt-2 flex items-center justify-end gap-3 transition-opacity w-full" :class="isEditing ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'">
            <template v-if="!isEditing">
              <button @click="handleEdit" class="text-text-placeholder hover:text-text-main transition-colors text-xs flex items-center gap-1" title="编辑"><i class="far fa-edit"></i></button>
              <button @click="handleCopy" class="text-text-placeholder hover:text-text-main transition-colors text-xs flex items-center gap-1" title="复制"><i class="far fa-copy"></i></button>
            </template>
            <template v-else>
              <button @click="isEditing = false" class="text-xs text-text-muted hover:text-text-main">取消</button>
              <button @click="submitEdit" class="text-xs bg-primary-main text-primary-text px-2 py-1 rounded hover:bg-primary-hover">确认</button>
            </template>
          </div>
        </div>
        <!-- Sibling Navigation -->
        <div v-if="siblingCount && siblingCount > 1" class="mt-2 flex items-center gap-2 text-[10px] text-text-placeholder select-none">
          <button @click="emit('navigate', nodeId, -1)" :disabled="siblingIndex === 0" class="hover:text-text-main disabled:opacity-30"><i class="fas fa-chevron-left"></i></button>
          <span>{{ (siblingIndex || 0) + 1 }} / {{ siblingCount }}</span>
          <button @click="emit('navigate', nodeId, 1)" :disabled="siblingIndex === siblingCount! - 1" class="hover:text-text-main disabled:opacity-30"><i class="fas fa-chevron-right"></i></button>
        </div>
      </template>

      <!-- ====== ASSISTANT MESSAGE ====== -->
      <template v-else>
        <div class="group flex flex-col items-start w-full">
          <!-- Thinking -->
          <div v-if="thinkingContent" class="mb-4 w-full">
            <div @click="isThinkingExpanded = !isThinkingExpanded" class="flex items-center gap-2 text-xs text-text-placeholder cursor-pointer hover:text-text-muted transition-colors mb-2">
              <i class="fas fa-brain"></i><span>思考过程</span>
              <i class="fas fa-chevron-down transition-transform" :class="isThinkingExpanded ? 'rotate-180' : ''"></i>
            </div>
            <div v-if="isThinkingExpanded" class="p-4 bg-bg-panel rounded-lg text-xs text-text-muted border-l-2 border-border-main leading-relaxed italic whitespace-pre-wrap shadow-sm">{{ thinkingContent }}</div>
          </div>

          <!-- Assistant content -->
          <div :id="`bubble-${nodeId}-assistant`" class="w-full">
            <template v-for="(item, idx) in message.assistant" :key="idx">
              <!-- Text content -->
              <div v-if="item.role === 'assistant' && item.content && segmentHtml[idx]" class="prose prose-sm max-w-none text-text-main break-words" v-html="segmentHtml[idx]" @click="handleCodeCopy"></div>

              <!-- Tool calls -->
              <template v-if="item.role === 'assistant' && item.tool_calls">
                <div v-for="call in item.tool_calls" :key="call.id" class="my-2">
                  <div @click="toggleTool(call.id)" class="flex items-center gap-2 text-xs text-text-placeholder cursor-pointer hover:text-text-muted transition-colors py-1">
                    <i class="fas fa-wrench text-[10px]"></i>
                    <span>调用 {{ call.function.name }}</span>
                    <i class="fas fa-chevron-right text-[10px] transition-transform duration-200" :class="expandedTools[call.id] ? 'rotate-90' : ''"></i>
                  </div>
                  <div v-if="expandedTools[call.id]" class="pl-5 pb-1">
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
          <div class="mt-2 flex items-center gap-3 opacity-0 group-hover:opacity-100 transition-opacity">
            <button @click="handleCopyAssistant" class="text-text-placeholder hover:text-text-main transition-colors text-xs flex items-center gap-1" title="复制"><i class="far fa-copy"></i></button>
          </div>
        </div>
      </template>

    </div>
  </div>
</template>

<style>
@reference "tailwindcss";

.prose pre { @apply bg-transparent p-0 m-0 border-none rounded-none overflow-visible; }
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
  @apply pl-4 py-1 my-4 italic rounded-r-sm;
}

.prose table {
  @apply w-full border-collapse my-4 text-sm overflow-hidden rounded-md block md:table overflow-x-auto;
  border: 1px solid var(--border-color);
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

/* Code block wrapper adjustments */
.code-block-wrapper pre code.hljs {
  @apply bg-transparent p-0;
}
</style>
