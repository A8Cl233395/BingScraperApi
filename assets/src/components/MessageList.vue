<script setup lang="ts">
import { shallowRef, ref, watch, onMounted, nextTick, reactive } from 'vue';
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
  user: any;
  assistant: AssistantMessage[];
  thinking?: string;
  parent?: string;
}

// Use shallowRef so that triggerRef() correctly forces re-render
// when we mutate the array contents or nested object properties.
const messages = shallowRef<ChatNode[]>([]);
const messageTree = ref<any>({});
const lastNodeId = ref<string | null>(null);
// Guard flag to prevent the currentChatId watch from firing during streaming
const isStreaming = ref(false);

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
    
    const node: ChatNode = { ...targetNode, id: currId };
    // Map reasoning_content to thinking property if missing (common in historical messages)
    if (!node.thinking && node.assistant) {
      const assistantMsg = node.assistant.find((m: any) => m.reasoning_content);
      if (assistantMsg) {
        node.thinking = assistantMsg.reasoning_content;
      }
    }

    chain.unshift(node);
    currId = targetNode.parent === 'root' ? null : targetNode.parent;
  }
  messages.value = chain;
  lastNodeId.value = nodeId;
  scrollToBottom(true);
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
  
  const userMsg: ChatNode = reactive({
    user: content,
    assistant: [],
    id: 'temp-' + Date.now(),
    isStreaming: true
  });
  // Push into a new array (shallowRef needs a new reference to auto-trigger,
  // but we also call triggerRef explicitly for in-place mutations)
  messages.value = [...messages.value, userMsg];
  scrollToBottom(true);

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
  let currentAnsweringEntry: AssistantMessage | null = null;
  
  const token = localStorage.getItem('token');
  const uid = localStorage.getItem('uid');

  // Set streaming flag BEFORE starting, so the watch on currentChatId is suppressed
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
          if (currentSignal === 'answering') {
            currentAnsweringEntry = null;
          } else if (currentSignal === 'tool_call') {
            currentToolResponseEntry = null;
          } else if (currentSignal === 'tool_response') {
            currentToolResponseEntry = null;
          }
        } else if (eventType === 'tool_name') {
          const callId = 'tc-' + Date.now();
          currentToolCallId = callId;
          userMsg.assistant.push(reactive<AssistantMessage>({
            role: 'assistant',
            tool_calls: [{
              type: 'function',
              id: callId,
              function: { name: data, arguments: '' }
            }]
          }) as AssistantMessage);
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
            userMsg.thinking = (userMsg.thinking || '') + data;
          } else if (currentSignal === 'answering') {
            if (!currentAnsweringEntry) {
              currentAnsweringEntry = reactive<AssistantMessage>({ role: 'assistant', content: '' });
              userMsg.assistant.push(currentAnsweringEntry as AssistantMessage);
            }
            currentAnsweringEntry!.content = (currentAnsweringEntry!.content || '') + data;
          } else if (currentSignal === 'tool_call') {
            const lastPart = userMsg.assistant[userMsg.assistant.length - 1];
            if (lastPart && lastPart.tool_calls && lastPart.tool_calls.length > 0) {
              lastPart.tool_calls[0].function.arguments += data;
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
        scrollToBottom();
      },
      onerror(err) {
        console.error('SSE Error', err);
        throw err; // Stop retrying
      }
    });
  } catch (e) {
    console.error('Failed to send message', e);
  } finally {
    // Clear streaming flag so the watch works normally again
    isStreaming.value = false;
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

const autoScroll = ref(true);

const handleWheel = (e: WheelEvent) => {
  if (e.deltaY < 0) {
    // User scrolled up via mouse wheel
    autoScroll.value = false;
  }
};

const handleScroll = (e: Event) => {
  const el = e.target as HTMLElement;
  // If user scrolls to the absolute bottom (with 2px tolerance for fractional pixels), enable auto scroll
  // If they scroll up at all, this becomes false, disabling auto scroll.
  autoScroll.value = Math.abs(el.scrollHeight - el.scrollTop - el.clientHeight) <= 2;
};

const scrollToBottom = (force = false) => {
  nextTick(() => {
    const el = document.getElementById('message-container');
    if (!el) return;

    // Don't auto-scroll if user is selecting text or mouse is down
    if (!force && (state.isMouseDown || state.isTextSelected)) {
      return;
    }

    if (force || autoScroll.value) {
      el.scrollTop = el.scrollHeight;
    }
  });
};

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
  <div id="message-container" class="overflow-y-auto p-4 no-scrollbar layout-transition scroll-smooth" @wheel="handleWheel" @scroll="handleScroll">
    <div class="max-w-4xl mx-auto py-8">
      <template v-for="node in messages" :key="node.id">
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
        />
      </template>
    </div>
  </div>
</template>
