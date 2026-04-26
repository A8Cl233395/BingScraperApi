<script setup lang="ts">
import { shallowRef, ref, watch, onMounted, onUnmounted, nextTick, reactive } from 'vue';
import { state } from '../store';
import MessageBubble from './MessageBubble.vue';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import api from '../utils/api';

interface AssistantMessage {
  role: 'assistant' | 'tool';
  content?: string;
  reasoning_content?: string;
  tool_calls?: any[];
  tool_call_id?: string;
}

interface ChatNode {
  id: string;
  clientId: string;
  user: any;
  assistant: AssistantMessage[];
  thinking?: string;
  parent?: string;
  isStreaming?: boolean;
}

// Use shallowRef so that triggerRef() correctly forces re-render
// when we mutate the array contents or nested object properties.
const messages = shallowRef<ChatNode[]>([]);
const messageTree = ref<any>({});
const lastNodeId = ref<string | null>(null);
// Guard flag to prevent the currentChatId watch from firing during streaming
const isStreaming = ref(false);
const abortController = ref<AbortController | null>(null);

const fetchChatDetails = async (id: number) => {
  try {
    const res = await api.get(`/api/message?id=${id}`);
    messageTree.value = res.data;
    buildMessageChain(res.data.root.current);
  } catch (e) {
    console.error('Failed to fetch chat details', e);
  }
};

const buildMessageChain = (nodeId: string) => {
  const chain: ChatNode[] = [];
  let currId: string | null = nodeId;
  while (currId && currId !== 'root') {
    const targetNode: any = messageTree.value[currId];
    if (!targetNode) break;
    
    const node: ChatNode = { ...targetNode, id: currId, clientId: currId };

    chain.unshift(node);
    currId = targetNode.parent === 'root' ? null : targetNode.parent;
  }
  messages.value = chain;
  lastNodeId.value = nodeId;
  nextTick(() => {
    scrollToBottom(true);
  });
};

const getSiblingCount = (nodeId: string) => {
  const targetNode = messageTree.value[nodeId];
  if (!targetNode) return 0;
  const parentNode = targetNode.parent === 'root' ? messageTree.value.root : messageTree.value[targetNode.parent];
  return parentNode?.child?.length || 0;
};

const getSiblingIndex = (nodeId: string) => {
  const targetNode = messageTree.value[nodeId];
  if (!targetNode) return 0;
  const parentNode = targetNode.parent === 'root' ? messageTree.value.root : messageTree.value[targetNode.parent];
  return parentNode?.child?.indexOf(nodeId) || 0;
};

const navigateSiblings = (nodeId: string, direction: number) => {
  const node = messageTree.value[nodeId];
  const parentNode = node.parent === 'root' ? messageTree.value.root : messageTree.value[node.parent];
  const siblings = parentNode.child || [];
  const index = siblings.indexOf(nodeId);
  const nextIndex = index + direction;
  if (nextIndex >= 0 && nextIndex < siblings.length) {
    buildMessageChain(siblings[nextIndex]);
  }
};

const handleSend = async (content: any, parent?: string) => {
  const parentId = parent || lastNodeId.value;
  
  const tempId = 'temp-' + Date.now();
  const userMsg: ChatNode = reactive({
    user: content,
    assistant: [],
    id: tempId,
    clientId: tempId,
    isStreaming: true
  });
  // Push into a new array (shallowRef needs a new reference to auto-trigger,
  // but we also call triggerRef explicitly for in-place mutations)
  messages.value = [...messages.value, userMsg];
  nextTick(() => {
    scrollToBottom(true);
  });

  const body: any = {
    content,
    parent: parentId,
  };
  if (state.currentChatId) body.id = state.currentChatId;
  if (state.currentModel !== state.defaultSettings.model) body.model = state.currentModel;
  if (state.currentVModel !== state.defaultSettings.vmodel) body.vmodel = state.currentVModel;
  if (state.isThinking !== state.defaultSettings.thinking) body.thinking = state.isThinking;
  if (state.isEnableFunction !== state.defaultSettings.enable_function) body.enable_function = state.isEnableFunction;

  let currentSignal = 'answering';
  let currentToolCallId = '';
  let currentToolResponseEntry: AssistantMessage | null = null;
  let currentAssistantEntry: AssistantMessage | null = null;
  
  const token = localStorage.getItem('token');
  const uid = localStorage.getItem('uid');

  if (abortController.value) {
    abortController.value.abort();
  }
  const currentController = new AbortController();
  abortController.value = currentController;
  isStreaming.value = true;

  try {
    await fetchEventSource(`${import.meta.env.VITE_API_BASE}/api/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'token': token || '',
        'uid': uid || ''
      },
      body: JSON.stringify(body),
      signal: currentController.signal,
      openWhenHidden: true,
      onmessage(ev) {
        const eventType = ev.event;
        let data = ev.data;
        try {
          if (data) {
            data = JSON.parse(data);
          }
        } catch (e) {
          // ignore
        }

        if (eventType === 'id') {
          // Set currentChatId but the watch is guarded by isStreaming flag
          state.currentChatId = parseInt(data);
        } else if (eventType === 'title') {
          const chat = state.chats.find(c => c[0] === state.currentChatId);
          if (chat) chat[1] = data;
          else state.chats.unshift([state.currentChatId!, data]);
        } else if (eventType === 'signal') {
          currentSignal = data;
          if (currentSignal === 'tool_response') {
            currentToolResponseEntry = null;
            currentAssistantEntry = null; // next action needs a new assistant block
          }
        } else if (eventType === 'tool_name') {
          const callId = 'tc-' + Date.now();
          currentToolCallId = callId;
          if (!currentAssistantEntry) {
            currentAssistantEntry = reactive<AssistantMessage>({ role: 'assistant' });
            userMsg.assistant.push(currentAssistantEntry as AssistantMessage);
          }
          if (!currentAssistantEntry.tool_calls) {
            currentAssistantEntry.tool_calls = [];
          }
          currentAssistantEntry.tool_calls.push({
            type: 'function',
            id: callId,
            function: { name: data, arguments: '' }
          });
        } else if (eventType === 'node_id') {
          lastNodeId.value = data;
          userMsg.id = data;
          // Register the new node in the local tree to allow immediate editing/branching
          messageTree.value[data] = {
            user: userMsg.user,
            assistant: userMsg.assistant,
            parent: parentId || 'root',
            child: []
          };
          // Update parent's reference to this new child
          const pId = parentId || 'root';
          const parentNode = pId === 'root' ? messageTree.value.root : messageTree.value[pId];
          if (parentNode) {
            if (!parentNode.child) parentNode.child = [];
            if (!parentNode.child.includes(data)) {
              parentNode.child.push(data);
            }
            // Only the root node maintains a 'current' pointer in the backend schema
            if (pId === 'root') {
              parentNode.current = data;
            }
          }
        } else if (eventType === 'error') {
          alert('Error: ' + data);
        } else {
          // Default data — route based on current signal
          if (currentSignal === 'thinking') {
            if (!currentAssistantEntry) {
              currentAssistantEntry = reactive<AssistantMessage>({ role: 'assistant' });
              userMsg.assistant.push(currentAssistantEntry as AssistantMessage);
            }
            currentAssistantEntry.reasoning_content = (currentAssistantEntry.reasoning_content || '') + data;
          } else if (currentSignal === 'answering') {
            if (!currentAssistantEntry) {
              currentAssistantEntry = reactive<AssistantMessage>({ role: 'assistant' });
              userMsg.assistant.push(currentAssistantEntry as AssistantMessage);
            }
            currentAssistantEntry.content = (currentAssistantEntry.content || '') + data;
          } else if (currentSignal === 'tool_call') {
            if (currentAssistantEntry && currentAssistantEntry.tool_calls && currentAssistantEntry.tool_calls.length > 0) {
              const lastTool = currentAssistantEntry.tool_calls[currentAssistantEntry.tool_calls.length - 1];
              lastTool.function.arguments += data;
            }
          } else if (currentSignal === 'tool_response') {
            if (!currentToolResponseEntry) {
              currentToolResponseEntry = reactive<AssistantMessage>({
                role: 'tool',
                content: data,
                tool_call_id: currentToolCallId
              });
              userMsg.assistant.push(currentToolResponseEntry as AssistantMessage);
            } else {
              currentToolResponseEntry!.content = (currentToolResponseEntry!.content || '') + data;
            }
          }
        }
      },
      onerror(err) {
        if (currentController.signal.aborted) return;
        console.error('SSE Error', err);
        throw err; // Stop retrying
      }
    });
  } catch (e: any) {
    if (e.name === 'AbortError' || currentController.signal.aborted) {
      console.log('Request aborted');
    } else {
      console.error('Failed to send message', e);
    }
  } finally {
    if (abortController.value === currentController) {
      isStreaming.value = false;
      abortController.value = null;
    }
  }
};

const handleEdit = (nodeId: string, newText: string) => {
  const node = messageTree.value[nodeId];
  const idx = messages.value.findIndex(m => m.id === nodeId);
  if (idx >= 0) {
    // Truncate from the edited node onward so the new message replaces it
    messages.value = messages.value.slice(0, idx);
  }
  handleSend([{ type: 'text', text: newText }], node.parent);
};

const handleRegenerate = (nodeId: string) => {
  const node = messageTree.value[nodeId];
  const idx = messages.value.findIndex(m => m.id === nodeId);
  if (idx >= 0) {
    // Truncate from the node onward
    messages.value = messages.value.slice(0, idx);
  }
  handleSend(node.user, node.parent);
};

const containerRef = ref<HTMLElement | null>(null);
const contentRef = ref<HTMLElement | null>(null);
const autoScroll = ref(true);

const handleScroll = (e: Event) => {
  const el = e.target as HTMLElement;
  const isAtBottom = Math.abs(el.scrollHeight - el.scrollTop - el.clientHeight) <= 10;
  
  // If user scrolls up, disable auto-scroll
  // If user scrolls back to bottom, re-enable auto-scroll
  autoScroll.value = isAtBottom;
};

const scrollToBottom = (force = false) => {
  if (!containerRef.value) return;

  // Don't auto-scroll if user is selecting text or mouse is down
  if (!force && (state.isMouseDown || state.isTextSelected)) {
    return;
  }

  if (force) {
    autoScroll.value = true;
  }

  if (autoScroll.value) {
    containerRef.value.scrollTop = containerRef.value.scrollHeight;
  }
};

// Use ResizeObserver to handle content size changes (e.g. during streaming)
let observer: ResizeObserver | null = null;
onMounted(() => {
  observer = new ResizeObserver(() => {
    if (autoScroll.value) {
      scrollToBottom();
    }
  });
  
  if (contentRef.value) {
    observer.observe(contentRef.value);
  }
});

onUnmounted(() => {
  if (observer) {
    observer.disconnect();
  }
});

watch(() => state.currentChatId, (newId) => {
  // Skip if we're currently streaming — the SSE handler sets currentChatId
  // from the 'id' event, and we don't want to fetch/replace messages mid-stream
  if (isStreaming.value) return;

  if (newId) {
    fetchChatDetails(newId);
  } else {
    messages.value = [];
    lastNodeId.value = 'root';
    messageTree.value = { root: { child: [], current: null } };
  }
});

onMounted(() => {
  if (state.currentChatId) {
    fetchChatDetails(state.currentChatId);
  } else {
    lastNodeId.value = 'root';
    messageTree.value = { root: { child: [], current: null } };
  }
});

defineExpose({ handleSend, messages });
</script>

<template>
  <div 
    ref="containerRef"
    id="message-container" 
    class="overflow-y-auto p-4" 
    @scroll="handleScroll"
  >
    <div ref="contentRef" class="max-w-4xl mx-auto py-8">
      <template v-for="node in messages" :key="node.clientId">
        <!-- User part of the node -->
        <MessageBubble 
          :message="node.user" 
          :isUser="true" 
          :nodeId="node.id"
          :siblingCount="getSiblingCount(node.id)"
          :siblingIndex="getSiblingIndex(node.id)"
          @navigate="navigateSiblings"
          @edit="handleEdit"
        />
        <!-- Assistant part of the node -->
        <MessageBubble 
          v-if="node.assistant && (node.assistant.length > 0 || node.thinking)"
          :message="node" 
          :isUser="false" 
          :nodeId="node.id"
          @regenerate="handleRegenerate"
        />
      </template>
    </div>
  </div>
</template>
