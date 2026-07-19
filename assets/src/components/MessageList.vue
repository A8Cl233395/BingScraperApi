<script setup lang="ts">
import { shallowRef, ref, watch, onMounted, onUnmounted, nextTick, reactive } from 'vue';
import { state } from '../store';
import MessageBubble from './MessageBubble.vue';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import api from '../utils/api';
import { useToast } from '../composables/useToast';

const { showToast } = useToast();

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
const activeStreamingNodeId = ref<string | null>(null);

const fetchChatDetails = async (id: number) => {
  lastActiveChatId.value = id;
  try {
    const res = await api.get(`/api/message?id=${id}`);
    messageTree.value = res.data;
    state.chatRequiresVision = !!res.data.root?.vision;
    buildMessageChain(res.data.root.current);
  } catch (e: any) {
    if (e.response?.status === 404) {
      showToast('聊天已被删除', 'info');
      state.chats = state.chats.filter(c => c[0] !== id);
      if (state.currentChatId === id) {
        state.currentChatId = null;
      }
    } else {
      console.error('Failed to fetch chat details', e);
      showToast('加载聊天失败', 'error');
      state.currentChatId = null;
      window.location.href = '/webchat';
    }
  }
};

const buildMessageChain = (nodeId: string, scrollToBottomFlag = true) => {
  const chain: ChatNode[] = [];
  let currId: string | null = nodeId;
  
  // 1. Build UP to the root from the selected nodeId
  while (currId && currId !== 'root') {
    const targetNode: any = messageTree.value[currId];
    if (!targetNode) break;
    
    const node: ChatNode = reactive({ ...targetNode, id: currId, clientId: currId });
    chain.unshift(node);
    currId = targetNode.parent === 'root' ? null : targetNode.parent;
  }

  // 2. Build DOWN to the leaf following the 'current' path
  // 如果节点没有 current 字段（非 root 节点），则使用最后一个子节点作为默认值
  const getNextDownId = (id: string): string | undefined => {
    const node = messageTree.value[id];
    if (!node) return undefined;
    // 优先使用 current 字段（排除自引用，防止无限循环）
    if (node.current && node.current !== id) return node.current;
    // 如果没有 current 字段，使用最后一个子节点
    const children = node.child;
    if (children && children.length > 0) {
      return children[children.length - 1];
    }
    return undefined;
  };

  let downId = getNextDownId(nodeId);
  while (downId) {
    const targetNode = messageTree.value[downId];
    if (!targetNode) break;
    const node: ChatNode = reactive({ ...targetNode, id: downId, clientId: downId });
    chain.push(node);
    downId = getNextDownId(downId);
  }

  messages.value = chain;
  
  // Update lastNodeId to the actual leaf of this branch
  if (chain.length > 0) {
    lastNodeId.value = chain[chain.length - 1].id;
  } else {
    lastNodeId.value = nodeId;
  }

  nextTick(() => {
    if (scrollToBottomFlag) {
      scrollToBottom(true);
    }
  });

  // Auto-reconnect: leaf node has user content but no assistant response or was interrupted
  const lastNode = chain[chain.length - 1];
  if (lastNode && lastNode.user && (!lastNode.assistant || lastNode.assistant.length === 0 || lastNode.isStreaming)) {
    if (state.isStreaming && activeStreamingNodeId.value === lastNode.id) {
      // Do nothing, it's already the active stream
    } else {
      handleReconnect(state.currentChatId!, lastNode.id);
    }
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
    if (sseState.signal === 'thinking') state.aiSignal = 'thinking';
    else if (sseState.signal === 'answering') state.aiSignal = 'answering';
    else if (sseState.signal === 'tool_call') state.aiSignal = 'tool_calling';
    else state.aiSignal = 'idle';
  } else if (eventType === 'tool_name') {
    const callId = 'tc-' + Date.now() + '-' + Math.random().toString(36).substring(2, 8);
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
    if (activeStreamingNodeId.value === targetMsg.clientId) {
      activeStreamingNodeId.value = data;
    }
    
    // Cleanup temp node from tree if we had one
    if (targetMsg.clientId.startsWith('temp-') && messageTree.value[targetMsg.clientId]) {
      delete messageTree.value[targetMsg.clientId];
    }
    
    targetMsg.id = data;
    const existingNode = messageTree.value[data];
    messageTree.value[data] = {
      user: targetMsg.user,
      assistant: targetMsg.assistant,
      parent: parentId || 'root',
      child: existingNode?.child || [],
      current: existingNode?.current,
      isStreaming: true
    };
    const pId = parentId || 'root';
    const parentNode = pId === 'root' ? messageTree.value.root : messageTree.value[pId];
    if (parentNode) {
      if (!parentNode.child) parentNode.child = [];
      if (!parentNode.child.includes(data)) parentNode.child.push(data);
      parentNode.current = data; // Update current pointer to this new node
    }
  } else if (eventType === 'error') {
    showToast('Error: ' + data, 'error');
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
  state.aiSignal = 'thinking';
  activeStreamingNodeId.value = nodeId;

  if (messageTree.value[nodeId]) {
    messageTree.value[nodeId].isStreaming = true;
  }

  let reconnectRetries = 0;
  const MAX_RECONNECT_RETRIES = 5;

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
        onclose() {
          // Prevent auto-retry on clean close (since this is a GET request, fetchEventSource auto-retries by default)
          if (!currentController.signal.aborted) {
            currentController.abort();
          }
        },
        onmessage(ev) {
          processSSEEvent(ev, targetMsg, sseState, parentId);
        },
        onerror(err) {
          if (currentController.signal.aborted || err.message === '404_NOT_FOUND') {
            throw err;
          }
          reconnectRetries++;
          if (reconnectRetries > MAX_RECONNECT_RETRIES) {
            throw err;
          }
          // 重置状态，因为重试时后端会从头重放所有数据
          targetMsg.assistant.splice(0, targetMsg.assistant.length);
          sseState.signal = 'answering';
          sseState.toolCallId = '';
          sseState.toolEntry = null;
          sseState.assistantEntry = null;
          messages.value = [...messages.value];
          showToast(`正在重连（${reconnectRetries}/${MAX_RECONNECT_RETRIES}）`, 'info');
          return reconnectRetries * 1000;
        }
      }
    );
  } catch (e: any) {
    if (e.name !== 'AbortError' && !currentController.signal.aborted && e.message !== '404_NOT_FOUND') {
      showToast('重连失败', 'error');
    }
  } finally {
    if (abortController.value === currentController) {
      state.isStreaming = false;
      state.aiSignal = 'idle';
      targetMsg.isStreaming = false;
      if (messageTree.value[nodeId]) {
        messageTree.value[nodeId].isStreaming = false;
      }
      activeStreamingNodeId.value = null;
      abortController.value = null;
      messages.value = [...messages.value];
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
    buildMessageChain(nextNodeId, false);
    
    // 滚动到切换按钮所在的位置（父节点），保持按钮位置不变
    nextTick(() => {
      const el = document.getElementById(`msg-${nodeId}`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    });
  }
};

const handleSend = async (content: any, parent?: string) => {
  const parentId = parent || lastNodeId.value;

  // 如果发送内容包含图片，立即标记会话需要视觉模型，
  // 防止 clearImages 清空草稿图片后 isVisionMode 短暂变为 false
  if (Array.isArray(content) && content.some((c: any) => c.type === 'image_url')) {
    state.chatRequiresVision = true;
  }
  
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
  activeStreamingNodeId.value = tempId;
  
  // Create an initial entry in messageTree to track isStreaming correctly
  messageTree.value[tempId] = {
    user: content,
    assistant: [],
    parent: parentId || 'root',
    child: [],
    current: null,
    isStreaming: true
  };
  
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
  state.aiSignal = 'thinking';

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
      showToast('发送消息失败', 'error');
      
      // 撤销发送的内容：从 messages 和 messageTree 中移除临时节点
      const msgIdx = messages.value.findIndex(m => m.clientId === tempId);
      if (msgIdx >= 0) {
        messages.value = messages.value.slice(0, msgIdx);
      }
      
      // 清理 messageTree 中的临时节点
      if (messageTree.value[tempId]) {
        const parentId = messageTree.value[tempId].parent;
        delete messageTree.value[tempId];
        // 从父节点的 child 数组中移除
        if (parentId && messageTree.value[parentId]) {
          const children = messageTree.value[parentId].child;
          if (children) {
            const childIdx = children.indexOf(tempId);
            if (childIdx >= 0) children.splice(childIdx, 1);
          }
        }
      }
      
      // 如果收到过真实节点ID，也需要清理
      if (receivedNodeId && messageTree.value[receivedNodeId]) {
        const parentId = messageTree.value[receivedNodeId].parent;
        delete messageTree.value[receivedNodeId];
        if (parentId && messageTree.value[parentId]) {
          const children = messageTree.value[parentId].child;
          if (children) {
            const childIdx = children.indexOf(receivedNodeId);
            if (childIdx >= 0) children.splice(childIdx, 1);
          }
        }
      }
      
      // 恢复 lastNodeId
      if (messages.value.length > 0) {
        lastNodeId.value = messages.value[messages.value.length - 1].id;
      } else {
        lastNodeId.value = parentId || 'root';
      }
      
      // 如果是新对话（没有 receivedNodeId），重置 currentChatId
      if (!receivedNodeId && !state.currentChatId) {
        // 从侧边栏移除新对话占位
        state.chats = state.chats.filter(c => c[0] !== null);
      }
    }
  } finally {
    if (abortController.value === currentController) {
      state.isStreaming = false;
      state.aiSignal = 'idle';
      userMsg.isStreaming = false;
      if (receivedNodeId && messageTree.value[receivedNodeId]) {
        messageTree.value[receivedNodeId].isStreaming = false;
      } else if (!receivedNodeId && messageTree.value[tempId]) {
        messageTree.value[tempId].isStreaming = false;
      }

      // 更新当前显示的消息对象（buildMessageChain 可能已创建新对象）
      const nodeIdToFind = receivedNodeId || tempId;
      const currentDisplayMsg = messages.value.find(m => m.id === nodeIdToFind);
      if (currentDisplayMsg) {
        currentDisplayMsg.isStreaming = false;
      }

      activeStreamingNodeId.value = null;
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
    state.chatRequiresVision = false;
  }
});

onMounted(() => {
  if (state.currentChatId) {
    fetchChatDetails(state.currentChatId);
  } else {
    lastNodeId.value = 'root';
    messageTree.value = { root: { child: [], current: null } };
    state.chatRequiresVision = false;
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
  if (typeof node.user === 'string') return node.user;
  if (Array.isArray(node.user)) {
    const text = node.user.find((c: any) => c.type === 'text')?.text;
    if (text) return text;
    if (node.user.some((c: any) => c.type === 'image_url')) return '[图片]';
  }
  return '空消息';
};

/** 取消正在进行的 AI 生成，回滚节点，返回用户输入内容 */
const handleCancel = async () => {
  const chatId = state.currentChatId;
  const nodeId = activeStreamingNodeId.value;

  if (!nodeId) return null;

  // 获取用户输入内容，用于恢复到输入框
  const targetMsg = messages.value.find(m => m.id === nodeId || m.clientId === nodeId);
  const userContent = targetMsg?.user ?? null;

  // 先将 abortController 置空，防止 handleSend/handleReconnect 的 finally 重复清理
  const controller = abortController.value;
  abortController.value = null;
  if (controller) {
    controller.abort();
  }
  state.isStreaming = false;
  activeStreamingNodeId.value = null;

  // 调用后端取消 API（幂等，不会报错）
  if (chatId && nodeId && !nodeId.startsWith('temp-')) {
    try {
      await api.get('/api/cancel', { params: { id: chatId, node_id: nodeId } });
    } catch (e) {
      console.error('取消请求失败', e);
      showToast('取消请求失败', 'error');
    }
  }

  // 回滚前端节点
  const realNodeId = targetMsg?.id || nodeId;
  const clientId = targetMsg?.clientId || nodeId;

  // 从 messages 中移除
  const idx = messages.value.findIndex(m => m.id === realNodeId || m.clientId === clientId);
  if (idx >= 0) {
    messages.value = messages.value.slice(0, idx);
  }

  // 从 messageTree 中移除（真实 ID 和临时 ID 都要清理）
  for (const id of [realNodeId, clientId]) {
    if (id && messageTree.value[id]) {
      const parentId = messageTree.value[id].parent;
      delete messageTree.value[id];
      if (parentId && messageTree.value[parentId]) {
        const children = messageTree.value[parentId].child;
        if (children) {
          const childIdx = children.indexOf(id);
          if (childIdx >= 0) children.splice(childIdx, 1);
        }
      }
    }
  }

  // 更新 lastNodeId
  if (messages.value.length > 0) {
    lastNodeId.value = messages.value[messages.value.length - 1].id;
  } else {
    lastNodeId.value = 'root';
  }

  return userContent;
};

defineExpose({ handleSend, handleCancel, messages, scrollToTop });
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
