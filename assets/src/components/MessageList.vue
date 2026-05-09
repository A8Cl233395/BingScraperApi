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
// Tracks which chat's messages are currently being displayed
const lastActiveChatId = ref<number | null | 'new'>(null);
const abortController = ref<AbortController | null>(null);
const activeNodeId = ref<string | null>(null);

const fetchChatDetails = async (id: number) => {
  lastActiveChatId.value = id;
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
  
  // 1. Build UP to the root from the selected nodeId
  while (currId && currId !== 'root') {
    const targetNode: any = messageTree.value[currId];
    if (!targetNode) break;
    
    const node: ChatNode = { ...targetNode, id: currId, clientId: currId };
    chain.unshift(node);
    currId = targetNode.parent === 'root' ? null : targetNode.parent;
  }

  // 2. Build DOWN to the leaf following the 'current' path
  let downId = messageTree.value[nodeId]?.current;
  while (downId) {
    const targetNode = messageTree.value[downId];
    if (!targetNode) break;
    const node: ChatNode = { ...targetNode, id: downId, clientId: downId };
    chain.push(node);
    downId = targetNode.current;
  }

  messages.value = chain;
  
  // Update lastNodeId to the actual leaf of this branch
  if (chain.length > 0) {
    lastNodeId.value = chain[chain.length - 1].id;
  } else {
    lastNodeId.value = nodeId;
  }

  nextTick(() => {
    scrollToBottom(true);
  });

  // Auto-reconnect: leaf node has user content but no assistant response
  const lastNode = chain[chain.length - 1];
  if (lastNode && lastNode.user && (!lastNode.assistant || lastNode.assistant.length === 0)) {
    handleReconnect(state.currentChatId!, lastNode.id);
  }
};

/** Shared SSE event processor — mutates targetMsg in-place */
const processSSEEvent = (
  ev: { event: string; data: string },
  targetMsg: ChatNode,
  sseState: { signal: string; toolCallId: string; toolEntry: AssistantMessage | null; assistantEntry: AssistantMessage | null },
  parentId?: string | null
) => {
  const eventType = ev.event;
  let data: any = ev.data;
  try { if (data) data = JSON.parse(data); } catch (_) { /* ignore */ }

  if (eventType === 'id') {
    const chatId = parseInt(data);
    lastActiveChatId.value = chatId;
    state.currentChatId = chatId;
    // Add a placeholder for new chats in the sidebar
    if (!state.chats.some(c => c[0] === chatId)) {
      state.chats.unshift([chatId, '新对话']);
    }
  } else if (eventType === 'title') {
    const chat = state.chats.find(c => c[0] === state.currentChatId);
    if (chat) chat[1] = data;
    else state.chats.unshift([state.currentChatId!, data]);
  } else if (eventType === 'signal') {
    sseState.signal = data;
    if (sseState.signal === 'tool_response') {
      sseState.toolEntry = null;
      sseState.assistantEntry = null;
    }
  } else if (eventType === 'tool_name') {
    const callId = 'tc-' + Date.now();
    sseState.toolCallId = callId;
    if (!sseState.assistantEntry) {
      sseState.assistantEntry = reactive<AssistantMessage>({ role: 'assistant' });
      targetMsg.assistant.push(sseState.assistantEntry as AssistantMessage);
    }
    if (!sseState.assistantEntry.tool_calls) sseState.assistantEntry.tool_calls = [];
    sseState.assistantEntry.tool_calls.push({ type: 'function', id: callId, function: { name: data, arguments: '' } });
  } else if (eventType === 'node_id') {
    // Only update lastNodeId if we are still on this branch or it was a temporary node
    if (lastNodeId.value === targetMsg.clientId || lastNodeId.value === parentId) {
      lastNodeId.value = data;
    }
    
    targetMsg.id = data;
    const existingNode = messageTree.value[data];
    messageTree.value[data] = {
      user: targetMsg.user,
      assistant: targetMsg.assistant,
      parent: parentId || 'root',
      child: existingNode?.child || [],
      current: existingNode?.current
    };
    const pId = parentId || 'root';
    const parentNode = pId === 'root' ? messageTree.value.root : messageTree.value[pId];
    if (parentNode) {
      if (!parentNode.child) parentNode.child = [];
      if (!parentNode.child.includes(data)) parentNode.child.push(data);
      parentNode.current = data; // Update current pointer to this new node
    }
  } else if (eventType === 'error') {
    alert('Error: ' + data);
  } else {
    if (sseState.signal === 'thinking') {
      if (!sseState.assistantEntry) {
        sseState.assistantEntry = reactive<AssistantMessage>({ role: 'assistant' });
        targetMsg.assistant.push(sseState.assistantEntry as AssistantMessage);
      }
      sseState.assistantEntry.reasoning_content = (sseState.assistantEntry.reasoning_content || '') + data;
    } else if (sseState.signal === 'answering') {
      if (!sseState.assistantEntry) {
        sseState.assistantEntry = reactive<AssistantMessage>({ role: 'assistant' });
        targetMsg.assistant.push(sseState.assistantEntry as AssistantMessage);
      }
      sseState.assistantEntry.content = (sseState.assistantEntry.content || '') + data;
    } else if (sseState.signal === 'tool_call') {
      if (sseState.assistantEntry?.tool_calls?.length) {
        const lastTool = sseState.assistantEntry.tool_calls[sseState.assistantEntry.tool_calls.length - 1];
        lastTool.function.arguments += data;
      }
    } else if (sseState.signal === 'tool_response') {
      if (!sseState.toolEntry) {
        sseState.toolEntry = reactive<AssistantMessage>({ role: 'tool', content: data, tool_call_id: sseState.toolCallId });
        targetMsg.assistant.push(sseState.toolEntry as AssistantMessage);
      } else {
        sseState.toolEntry!.content = (sseState.toolEntry!.content || '') + data;
      }
    }
  }
};

/** Reconnect to a node's SSE stream (full replay). Handles both initial-load and mid-stream disconnect. */
const handleReconnect = async (chatId: number, nodeId: string) => {
  const targetMsg = messages.value.find(m => m.id === nodeId);
  if (!targetMsg) return;

  const parentId = messageTree.value[nodeId]?.parent || null;

  // Reset assistant content — reconnect returns full payload, not incremental
  targetMsg.assistant.splice(0, targetMsg.assistant.length);
  targetMsg.isStreaming = true;
  // Trigger reactivity for shallowRef
  messages.value = [...messages.value];

  const sseState = { signal: 'answering', toolCallId: '', toolEntry: null as AssistantMessage | null, assistantEntry: null as AssistantMessage | null };
  const token = localStorage.getItem('token');
  const uid = localStorage.getItem('uid');

  if (abortController.value) abortController.value.abort();
  const currentController = new AbortController();
  abortController.value = currentController;
  state.isStreaming = true;

  try {
    await fetchEventSource(
      `${import.meta.env.VITE_API_BASE}/api/reconnect?id=${chatId}&node_id=${nodeId}`,
      {
        method: 'GET',
        headers: { 'token': token || '', 'uid': uid || '' },
        signal: currentController.signal,
        openWhenHidden: true,
        async onopen(response) {
          if (response.status === 404) {
            await fetchChatDetails(chatId);
            throw new Error('404_NOT_FOUND');
          }
        },
        onmessage(ev) {
          processSSEEvent(ev, targetMsg, sseState, parentId);
        },
        onerror(err) {
          if (currentController.signal.aborted || err.message === '404_NOT_FOUND') {
            throw err; // Stop retrying
          }
          console.error('Reconnect SSE Error', err);
          throw err;
        }
      }
    );
  } catch (e: any) {
    if (e.name !== 'AbortError' && !currentController.signal.aborted && e.message !== '404_NOT_FOUND') {
      console.error('Reconnect failed', e);
    }
  } finally {
    if (abortController.value === currentController) {
      state.isStreaming = false;
      targetMsg.isStreaming = false;
      abortController.value = null;
    }
  }
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
  const pId = node.parent || 'root';
  const parentNode = pId === 'root' ? messageTree.value.root : messageTree.value[pId];
  const siblings = parentNode.child || [];
  const index = siblings.indexOf(nodeId);
  const nextIndex = index + direction;
  if (nextIndex >= 0 && nextIndex < siblings.length) {
    const nextNodeId = siblings[nextIndex];
    // Update the parent's current pointer to the selected sibling
    parentNode.current = nextNodeId;
    buildMessageChain(nextNodeId);
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
  lastNodeId.value = tempId;
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

  const sseState = { signal: 'answering', toolCallId: '', toolEntry: null as AssistantMessage | null, assistantEntry: null as AssistantMessage | null };
  const token = localStorage.getItem('token');
  const uid = localStorage.getItem('uid');

  if (abortController.value) {
    abortController.value.abort();
  }
  const currentController = new AbortController();
  abortController.value = currentController;
  state.isStreaming = true;

  // Track whether we received a node_id (needed for disconnect reconnect)
  let receivedNodeId: string | null = null;
  let disconnectedDuringStream = false;

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
        processSSEEvent(ev, userMsg, sseState, parentId);
        if (ev.event === 'node_id') {
          try { receivedNodeId = JSON.parse(ev.data); } catch (_) { receivedNodeId = ev.data; }
        }
      },
      onerror(err) {
        if (currentController.signal.aborted) return;
        console.error('SSE Error', err);
        // Mark for reconnect instead of giving up
        if (receivedNodeId && state.currentChatId) {
          disconnectedDuringStream = true;
        }
        throw err; // Stop the current fetchEventSource retry loop
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
      state.isStreaming = false;
      userMsg.isStreaming = false;
      abortController.value = null;
    }
  }

  // If the SSE stream disconnected mid-generation, attempt reconnect
  if (disconnectedDuringStream && receivedNodeId && state.currentChatId) {
    handleReconnect(state.currentChatId, receivedNodeId);
  }
};

const handleEdit = (nodeId: string, newContent: any) => {
  const node = messageTree.value[nodeId];
  const idx = messages.value.findIndex(m => m.id === nodeId);
  if (idx >= 0) {
    // Truncate from the edited node onward so the new message replaces it
    messages.value = messages.value.slice(0, idx);
  }
  handleSend(newContent, node.parent);
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
  // If the change was triggered by the same chat (e.g. stream setting the ID), ignore it
  if (newId === lastActiveChatId.value) return;

  // Reset highlight when switching chats
  activeNodeId.value = null;

  // If we are switching while streaming, abort the current stream
  if (state.isStreaming) {
    if (abortController.value) {
      abortController.value.abort();
    }
    state.isStreaming = false;
  }

  if (newId) {
    fetchChatDetails(newId);
  } else {
    lastActiveChatId.value = null;
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

const scrollToTop = () => {
  if (containerRef.value) {
    containerRef.value.scrollTo({ top: 0, behavior: 'smooth' });
    autoScroll.value = false;
  }
};

const isNavExpanded = ref(false);

const scrollToNode = (nodeId: string) => {
  activeNodeId.value = nodeId;
  const el = document.getElementById(`msg-${nodeId}`);
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    autoScroll.value = false;
  }
};

let activeObserver: IntersectionObserver | null = null;
onMounted(() => {
  activeObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        activeNodeId.value = entry.target.id.replace('msg-', '');
      }
    });
  }, {
    root: containerRef.value,
    threshold: 0.5
  });

  // Observe existing nodes
  messages.value.forEach(node => {
    const el = document.getElementById(`msg-${node.id}`);
    if (el) activeObserver?.observe(el);
  });
});

onUnmounted(() => {
  if (activeObserver) activeObserver.disconnect();
});

watch(messages, (newMsgs) => {
  nextTick(() => {
    if (activeObserver) {
      activeObserver.disconnect();
      newMsgs.forEach(node => {
        const el = document.getElementById(`msg-${node.id}`);
        if (el) activeObserver?.observe(el);
      });
    }
  });
}, { deep: true });

const getMsgPreview = (node: ChatNode) => {
  const text = node.user.find((c: any) => c.type === 'text')?.text;
  if (text) return text;
  if (node.user.some((c: any) => c.type === 'image_url')) return '[图片]';
  return '空消息';
};

defineExpose({ handleSend, messages, scrollToTop });
</script>

<template>
  <div class="flex flex-col min-h-0 relative">
    <div 
      ref="containerRef"
      id="message-container" 
      class="flex-1 overflow-y-auto p-4" 
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
            v-if="(node.assistant && (node.assistant.length > 0 || node.thinking)) || node.isStreaming"
            :message="node" 
            :isUser="false" 
            :nodeId="node.id"
            @regenerate="handleRegenerate"
          />
        </template>
      </div>
    </div>

    <!-- Desktop Message Navigator -->
    <Teleport to="body" v-if="!state.isMobile && messages.length > 1">
      <div 
        class="fixed right-6 top-1/2 -translate-y-1/2 z-40 flex flex-col items-end transition-all duration-300 ease-in-out group max-h-[80vh]"
        @mouseenter="isNavExpanded = true"
        @mouseleave="isNavExpanded = false"
      >
        <div 
          class="flex flex-col gap-4 p-3 rounded-lg transition-all duration-300 ease-in-out border border-transparent overflow-y-auto overflow-x-hidden no-scrollbar show-scrollbar-on-hover"
          :class="[
            isNavExpanded ? 'bg-bg-panel border-border-main shadow-2xl scale-100' : 'bg-transparent scale-95'
          ]"
        >
          <div 
            v-for="node in messages" 
            :key="node.id"
            class="flex items-center justify-end gap-3 cursor-pointer group/item py-0.5"
            @click="scrollToNode(node.id)"
          >
            <div 
              class="text-xs text-text-muted transition-all duration-300 origin-right whitespace-nowrap max-w-0 overflow-hidden opacity-0"
              :class="isNavExpanded ? 'max-w-[240px] opacity-100' : ''"
            >
              <span class="group-hover/item:text-text-main transition-colors">{{ getMsgPreview(node) }}</span>
            </div>
            <div 
              class="h-1 rounded-full transition-all duration-300 shrink-0"
              :class="[
                isNavExpanded ? 'w-4' : 'w-3',
                activeNodeId === node.id ? 'bg-primary-main shadow-[0_0_8px_rgba(var(--primary-rgb),0.5)]' : 'bg-text-placeholder/40 group-hover/item:bg-text-muted'
              ]"
            ></div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
