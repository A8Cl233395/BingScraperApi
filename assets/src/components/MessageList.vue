<script setup lang="ts">
import { shallowRef, ref, watch, onMounted, onUnmounted, nextTick, reactive } from 'vue';
import { state } from '../store';
import MessageBubble from './MessageBubble.vue';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import api from '../utils/api';
import { getAuthHeaders } from '../utils/auth';
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
  streamConnected?: boolean;
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
    // 内容替换完成后播放入场动画（nextTick 注册晚于 buildMessageChain 内部的 scrollToBottom）
    nextTick(playChatEnterAnim);
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

/** 移除服务端已回滚的节点，并将发送游标恢复到有效节点。 */
const removeFailedNode = (targetMsg: ChatNode, fallbackParentId?: string | null) => {
  const nodeIds = [...new Set([targetMsg.id, targetMsg.clientId].filter(Boolean))];
  let parentId = fallbackParentId || null;

  for (const nodeId of nodeIds) {
    const treeNode = messageTree.value[nodeId];
    if (!treeNode) continue;

    parentId = treeNode.parent || parentId;
    delete messageTree.value[nodeId];

    const parentNode = parentId
      ? (parentId === 'root' ? messageTree.value.root : messageTree.value[parentId])
      : null;
    if (parentNode?.child) {
      parentNode.child = parentNode.child.filter((childId: string) => childId !== nodeId);
      if (parentNode.current === nodeId) {
        parentNode.current = parentNode.child[parentNode.child.length - 1] || null;
      }
    }
  }

  messages.value = messages.value.filter(
    message => !nodeIds.includes(message.id) && !nodeIds.includes(message.clientId)
  );

  targetMsg.isStreaming = false;
  if (messages.value.length > 0) {
    lastNodeId.value = messages.value[messages.value.length - 1].id;
  } else if (parentId && messageTree.value[parentId]) {
    lastNodeId.value = parentId;
  } else {
    lastNodeId.value = 'root';
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
    removeFailedNode(targetMsg, parentId);
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
  targetMsg.streamConnected = false;
  // Trigger reactivity for shallowRef
  messages.value = [...messages.value];

  const sseState = { signal: 'answering', toolCallId: '', toolEntry: null as AssistantMessage | null, assistantEntry: null as AssistantMessage | null };

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
        headers: getAuthHeaders(),
        signal: currentController.signal,
        openWhenHidden: true,
        async onopen(response) {
          if (response.status === 404) {
            await fetchChatDetails(chatId);
            throw new Error('404_NOT_FOUND');
          }
          // HTTP 流已建立：立即由连接动画（盲文点阵）切换为输出动画（光标），不等文字
          targetMsg.streamConnected = true;
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
          targetMsg.streamConnected = false;
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

  // 退出动画进行中发送消息：取消退出并让消息区重新展开
  cancelExitAnim();

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

  if (abortController.value) {
    abortController.value.abort();
  }
  const currentController = new AbortController();
  abortController.value = currentController;
  state.isStreaming = true;
  state.aiSignal = 'thinking';

  // Track whether we received a node_id (needed for disconnect reconnect)
  let receivedNodeId: string | null = null;
  const originalChatId = state.currentChatId;
  let receivedChatId: number | null = originalChatId;
  let disconnectedDuringStream = false;

  try {
    await fetchEventSource(`${import.meta.env.VITE_API_BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(body),
      signal: currentController.signal,
      openWhenHidden: true,
      async onopen(response) {
        // HTTP 流已建立：立即由连接动画（盲文点阵）切换为输出动画（光标），不等文字
        const contentType = response.headers.get('content-type');
        if (!contentType?.startsWith('text/event-stream')) {
          throw new Error(`Expected content-type to be text/event-stream, Actual: ${contentType}`);
        }
        userMsg.streamConnected = true;
      },
      onmessage(ev) {
        processSSEEvent(ev, userMsg, sseState, parentId);
        if (ev.event === 'id') {
          try { receivedChatId = parseInt(JSON.parse(ev.data)); } catch (_) { receivedChatId = parseInt(ev.data); }
        }
        if (ev.event === 'node_id') {
          try { receivedNodeId = JSON.parse(ev.data); } catch (_) { receivedNodeId = ev.data; }
        }
      },
      onerror(err) {
        if (currentController.signal.aborted) return;
        console.error('SSE Error', err);
        // Mark for reconnect instead of giving up
        if (receivedNodeId && receivedChatId) {
          disconnectedDuringStream = true;
        }
        throw err; // Stop the current fetchEventSource retry loop
      }
    });
  } catch (e: any) {
    if (e.name === 'AbortError' || currentController.signal.aborted) {
      console.log('Request aborted');
    } else if (disconnectedDuringStream) {
      // 保留已创建的节点，稍后通过 /api/reconnect 继续接收生成结果
      console.warn('SSE 连接中断，准备重连');
    } else {
      console.error('Failed to send message', e);
      showToast('发送消息失败', 'error');
      
      // 撤销发送的内容：从 messages 和 messageTree 中移除失败节点
      removeFailedNode(userMsg, parentId);
      
      // 新对话已创建（收到 id 事件）但未产生任何节点：移除侧边栏占位并回到新对话状态
      if (!receivedNodeId && originalChatId === null && receivedChatId !== null) {
        state.chats = state.chats.filter(c => c[0] !== receivedChatId);
        if (state.currentChatId === receivedChatId) {
          state.currentChatId = null;
        }
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
  if (disconnectedDuringStream && receivedNodeId && receivedChatId) {
    handleReconnect(receivedChatId, receivedNodeId);
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
const lastScrollTop = ref(0);
// scrollToBottom 主动设置的位置。浏览器派发程序化滚动的 scroll 事件时，内容可能已继续
// 增高，导致事件位置看似不在底部；据此识别并忽略这类“回声”事件，避免高速流式输出时
// 被误判为用户上滑而取消 autoScroll（慢速时增幅小于 15px 容差，故不易触发）。
let expectedScrollTop: number | null = null;

const handleScroll = (e: Event) => {
  const el = e.target as HTMLElement;
  const scrollTop = el.scrollTop;

  // 忽略自身触发的程序化滚动（2px 容差用于吸收设备像素取整误差）
  if (expectedScrollTop !== null && Math.abs(scrollTop - expectedScrollTop) <= 2) {
    expectedScrollTop = null;
    lastScrollTop.value = scrollTop;
    return;
  }
  expectedScrollTop = null;

  const isAtBottom = Math.abs(el.scrollHeight - scrollTop - el.clientHeight) <= 15;
  
  // 只有当位置真正上移（用户向上滚动）时才取消 autoScroll；
  // 位置不变或下移（键盘弹出、容器尺寸变化引起浏览器自动调整）不改动跟随状态。
  // 当滚动处于底部时，仅在用户向下滑动（scrollTop >= lastScrollTop）时重新激活 autoScroll，
  // 避免 DOM 元素塌陷/重绘导致 scrollTop 被浏览器强制归零或变小从而误触 autoScroll 的问题。
  if (isAtBottom) {
    if (scrollTop >= lastScrollTop.value) {
      if (!autoScroll.value && !isSelectionInteracting()) {
        // 用户重新滑回底部：立即贴底并恢复跟随，避免与输入框/键盘之间残留缝隙
        autoScroll.value = true;
        scrollToBottom();
      }
    }
  } else if (scrollTop < lastScrollTop.value) {
    autoScroll.value = false;
  }
  lastScrollTop.value = scrollTop;
};

// 用户正在按下鼠标或选择文本时禁止自动滚动，避免打断操作
const isSelectionInteracting = () => state.isMouseDown || state.isTextSelected;

const scrollToBottom = (force = false) => {
  if (!containerRef.value) return;

  // Don't auto-scroll if user is selecting text or mouse is down
  if (!force && isSelectionInteracting()) {
    return;
  }

  if (force) {
    autoScroll.value = true;
  }

  if (autoScroll.value) {
    containerRef.value.scrollTop = containerRef.value.scrollHeight;
    lastScrollTop.value = containerRef.value.scrollTop;
    expectedScrollTop = containerRef.value.scrollTop;
  }
};

// Use ResizeObserver to handle content size changes (e.g. during streaming)
let observer: ResizeObserver | null = null;
// 容器高度变化（键盘弹出/收起、窗口缩放、输入框换行撑高等）时重新贴底：
// 键盘弹出会让聊天区变矮，处于跟随状态时必须重新贴底，
// 否则最后一条消息会被输入框遮挡（浏览器自身不会调整滚动位置，也不会派发 scroll 事件）。
let containerObserver: ResizeObserver | null = null;
onMounted(() => {
  observer = new ResizeObserver(() => {
    if (autoScroll.value && state.isStreaming) {
      scrollToBottom();
    }
  });
  
  if (contentRef.value) {
    observer.observe(contentRef.value);
  }

  containerObserver = new ResizeObserver(() => {
    if (autoScroll.value) {
      scrollToBottom();
    }
  });
  if (containerRef.value) {
    containerObserver.observe(containerRef.value);
  }
});

onUnmounted(() => {
  if (observer) {
    observer.disconnect();
  }
  if (containerObserver) {
    containerObserver.disconnect();
  }
});

watch(() => state.currentChatId, (newId, oldId) => {
  // If the change was triggered by the same chat (e.g. stream setting the ID), ignore it
  if (newId === lastActiveChatId.value) return;

  // Reset highlight when switching chats
  activeNodeId.value = null;
  isNavExpanded.value = false;

  // If we are switching while streaming, abort the current stream
  if (state.isStreaming) {
    if (abortController.value) {
      abortController.value.abort();
    }
    state.isStreaming = false;
  }

  if (newId) {
    // 判定切换方向并先播离场动画；入场动画在新内容渲染完成后触发（fetchChatDetails）
    cancelExitAnim();
    pendingChatAnim.value = resolveChatAnimDirection(oldId, newId);
    startChatLeaveAnim();
    fetchChatDetails(newId);
  } else {
    // 退出到新对话：内容先向上滑出视口外（容器保持展开），动画结束后再清空；
    // 容器收起由 Chat.vue 的过渡处理
    pendingChatAnim.value = null;
    lastActiveChatId.value = null;
    exitToNewChat();
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

// ---------- 聊天切换动画 ----------
// 侧边栏列表最新对话在最上方：切换到更靠下（更旧）的聊天时整体表现为向下滚动，
// 切换到更靠上（更新）的聊天时表现为向上滚动。仅动画 transform/opacity（合成器渲染，
// 不触发重排），不做新旧两份 DOM 并存渲染；离场/入场共用同一组参数，仅方向镜像。
const CHAT_ANIM_DISTANCE = 24;
const CHAT_ANIM_LEAVE_MS = 180;
const CHAT_ANIM_ENTER_MS = 260;
const CHAT_ANIM_EASE_IN = 'cubic-bezier(0.4, 0, 1, 1)';
const CHAT_ANIM_EASE_OUT = 'cubic-bezier(0, 0, 0.2, 1)';

const pendingChatAnim = ref<'down' | 'up' | null>(null);
let chatAnimToken = 0;
let chatAnimCleanupTimer: ReturnType<typeof setTimeout> | null = null;
let exitAnimTimer: ReturnType<typeof setTimeout> | null = null;

const prefersReducedMotion = () =>
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** 目标对话在侧边栏中比当前更靠下（更旧）→ 'down'，否则（更新/新建/不在列表中）→ 'up'。null 视为列表最上方 */
const resolveChatAnimDirection = (oldId: number | null | undefined, newId: number | null | undefined): 'down' | 'up' => {
  const oldIdx = oldId == null ? -1 : state.chats.findIndex(c => c[0] === oldId);
  const newIdx = newId == null ? -1 : state.chats.findIndex(c => c[0] === newId);
  return newIdx > oldIdx ? 'down' : 'up';
};

/** 离场：旧内容沿切换方向滑出并淡出（无旧内容或偏好减少动效时跳过） */
const startChatLeaveAnim = () => {
  const dir = pendingChatAnim.value;
  const el = contentRef.value;
  if (!dir || !el || messages.value.length === 0 || prefersReducedMotion()) return;

  chatAnimToken++;
  el.style.willChange = 'transform, opacity';
  el.style.transition = `transform ${CHAT_ANIM_LEAVE_MS}ms ${CHAT_ANIM_EASE_IN}, opacity ${CHAT_ANIM_LEAVE_MS}ms ${CHAT_ANIM_EASE_IN}`;
  // 向下滚动：旧内容向上滑出；向上滚动：旧内容向下滑出
  el.style.transform = `translateY(${dir === 'down' ? -CHAT_ANIM_DISTANCE : CHAT_ANIM_DISTANCE}px)`;
  el.style.opacity = '0';
};

/** 入场：内容替换完成后从切换方向一侧滑入（向下滚动自下而上，向上滚动自上而下） */
const playChatEnterAnim = () => {
  const dir = pendingChatAnim.value;
  pendingChatAnim.value = null;
  const el = contentRef.value;
  if (!dir || !el || messages.value.length === 0 || prefersReducedMotion()) return;

  chatAnimToken++;
  const token = chatAnimToken;

  // 先无过渡跳到入场起点并强制回流提交起点状态，再过渡回原位
  el.style.transition = 'none';
  el.style.transform = `translateY(${dir === 'down' ? CHAT_ANIM_DISTANCE : -CHAT_ANIM_DISTANCE}px)`;
  el.style.opacity = '0';
  void el.offsetHeight;
  el.style.transition = `transform ${CHAT_ANIM_ENTER_MS}ms ${CHAT_ANIM_EASE_OUT}, opacity ${CHAT_ANIM_ENTER_MS}ms ${CHAT_ANIM_EASE_OUT}`;
  el.style.transform = '';
  el.style.opacity = '';

  if (chatAnimCleanupTimer) clearTimeout(chatAnimCleanupTimer);
  // 动画结束后移除 will-change，释放合成层；token 防止连续切换时旧定时器误清新动画的样式
  chatAnimCleanupTimer = setTimeout(() => {
    if (token !== chatAnimToken) return;
    el.style.willChange = '';
    chatAnimCleanupTimer = null;
  }, CHAT_ANIM_ENTER_MS + 80);
};

onUnmounted(() => {
  if (chatAnimCleanupTimer) clearTimeout(chatAnimCleanupTimer);
  if (exitAnimTimer) clearTimeout(exitAnimTimer);
});

/** 取消进行中的退出动画（用户在动画期间发送消息或进入其他对话） */
const cancelExitAnim = () => {
  if (exitAnimTimer) {
    clearTimeout(exitAnimTimer);
    exitAnimTimer = null;
  }
  state.isChatExiting = false;
};

/**
 * 退出到新对话：内容与输入框同时做进入动画的逆过程——
 * 容器（连同内容）向上滑出视口外并塌缩（由 Chat.vue 根据 isChatExiting 过渡），
 * 动画结束后再清空数据。
 */
const exitToNewChat = () => {
  cancelExitAnim();
  if (messages.value.length === 0 || prefersReducedMotion()) {
    clearChatData();
    return;
  }
  state.isChatExiting = true;
  exitAnimTimer = setTimeout(() => {
    exitAnimTimer = null;
    state.isChatExiting = false;
    // 等待期间用户可能已进入其他对话，此时数据由 enter 流程接管
    if (state.currentChatId == null) clearChatData();
  }, 520);
};

/** 清空对话数据；容器收起动画由 Chat.vue 处理 */
const clearChatData = () => {
  messages.value = [];
  lastNodeId.value = 'root';
  messageTree.value = { root: { child: [], current: null } };
  state.chatRequiresVision = false;
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

// ---------- 移动端 Message Navigator（右侧边缘左滑从视口外滑入） ----------
const MOBILE_NAV_EDGE = 60; // 右侧触发区宽度（扩大以避开安卓全面屏手势的边缘区域）

const handleNavItemClick = (nodeId: string) => {
  scrollToNode(nodeId);
  if (state.isMobile) isNavExpanded.value = false;
};

// 消息数不足时收起导航
watch(() => messages.value.length, (len) => {
  if (len <= 1) isNavExpanded.value = false;
});

// 边缘手势：从屏幕最右侧向左滑
let edgeTouchId: number | null = null;
let edgeStartX = 0;
let edgeStartY = 0;
let edgeDir: 'none' | 'h' = 'none';

const resetEdgeGesture = () => {
  edgeTouchId = null;
  edgeDir = 'none';
};

const handleEdgeTouchStart = (e: TouchEvent) => {
  if (!state.isMobile || e.touches.length > 1) return;
  if (state.isSidebarOpen || state.previewImageUrl || state.showSelectionOverlay) return;
  if (messages.value.length <= 1) return;

  // 已展开时：触摸导航外任意位置收起
  if (isNavExpanded.value) {
    const target = e.target as HTMLElement | null;
    if (!target?.closest?.('#message-navigator')) {
      isNavExpanded.value = false;
    }
    return;
  }

  const t = e.touches[0];
  if (t.clientX < window.innerWidth - MOBILE_NAV_EDGE) return;
  edgeTouchId = t.identifier;
  edgeStartX = t.clientX;
  edgeStartY = t.clientY;
  edgeDir = 'none';
};

const handleEdgeTouchMove = (e: TouchEvent) => {
  if (edgeTouchId === null) return;
  const t = Array.from(e.touches).find(item => item.identifier === edgeTouchId);
  if (!t) return;

  if (edgeDir === 'none') {
    const dx = t.clientX - edgeStartX;
    const dy = t.clientY - edgeStartY;
    if (Math.abs(dx) < 6 && Math.abs(dy) < 6) return;
    // 判定为向左的水平滑动才展开导航，否则视为纵向滚动（放宽角度阈值，斜向滑动也可触发）
    if (dx < 0 && Math.abs(dx) > Math.abs(dy) * 0.7) {
      edgeDir = 'h';
      isNavExpanded.value = true;
    } else {
      resetEdgeGesture();
      return;
    }
  }

  if (edgeDir === 'h') {
    e.preventDefault();
  }
};

const handleEdgeTouchEnd = () => {
  resetEdgeGesture();
};

onMounted(() => {
  window.addEventListener('touchstart', handleEdgeTouchStart, { passive: true });
  window.addEventListener('touchmove', handleEdgeTouchMove, { passive: false });
  window.addEventListener('touchend', handleEdgeTouchEnd);
  window.addEventListener('touchcancel', handleEdgeTouchEnd);
});

onUnmounted(() => {
  window.removeEventListener('touchstart', handleEdgeTouchStart);
  window.removeEventListener('touchmove', handleEdgeTouchMove);
  window.removeEventListener('touchend', handleEdgeTouchEnd);
  window.removeEventListener('touchcancel', handleEdgeTouchEnd);
});

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

// 仅在消息节点集合变化（增删或临时 id 转正）时重新挂载观察器；
// deep 监听会让流式期间的每个增量都触发全量遍历与重新 observe
watch(() => messages.value.map(node => node.id).join('\n'), () => {
  nextTick(() => {
    if (!activeObserver) return;
    activeObserver.disconnect();
    messages.value.forEach(node => {
      const el = document.getElementById(`msg-${node.id}`);
      if (el) activeObserver?.observe(el);
    });
  });
});

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

    <!-- Message Navigator（桌面悬停展开；移动端右侧边缘左滑从视口外滑入） -->
    <Teleport to="body">
      <Transition name="chat-nav">
        <div
          v-if="messages.length > 1 && !state.isChatExiting"
          id="message-navigator"
          class="fixed top-1/2 -translate-y-1/2 z-40 flex flex-col items-end group max-h-[80vh] right-6"
          :class="state.isMobile
            ? ['transition-[translate,visibility] duration-300 ease-[cubic-bezier(0.25,0.46,0.45,0.94)]', isNavExpanded ? 'translate-x-0 visible' : 'translate-x-[calc(100%_+_1.5rem)] invisible pointer-events-none']
            : ''"
          @mouseenter="!state.isMobile && (isNavExpanded = true)"
          @mouseleave="!state.isMobile && (isNavExpanded = false)"
        >
        <div
          class="flex flex-col gap-4 p-3 border border-transparent overflow-y-auto overflow-x-hidden no-scrollbar show-scrollbar-on-hover transition-transform duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)]"
          :class="[
            (state.isMobile || isNavExpanded) ? 'bg-bg-panel border-border-main shadow-2xl translate-x-0' : 'bg-transparent translate-x-1.5'
          ]"
        >
          <div 
            v-for="node in messages" 
            :key="node.id"
            class="flex items-center justify-end gap-3 cursor-pointer group/item py-0.5"
            @click="handleNavItemClick(node.id)"
          >
            <div
              class="text-xs text-text-muted overflow-hidden whitespace-nowrap text-right transition-[width] duration-300 ease-out"
              :class="(state.isMobile || isNavExpanded) ? 'w-[240px]' : 'w-0'"
            >
              <span class="group-hover/item:text-text-main transition-colors">{{ getMsgPreview(node) }}</span>
            </div>
            <div 
              class="h-1 rounded-full transition-[width,background-color,box-shadow] duration-200 ease-out shrink-0"
              :class="[
                (state.isMobile || isNavExpanded) ? 'w-4' : 'w-3',
                activeNodeId === node.id ? 'bg-primary-main' : 'bg-text-placeholder/40 group-hover/item:bg-text-muted'
              ]"
            ></div>
          </div>
        </div>
      </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
/* 消息跳转器随消息区进入/退出动画同步显隐（与 Chat.vue 容器相同的时长与缓动） */
.chat-nav-enter-active,
.chat-nav-leave-active {
  transition: transform 0.5s ease-in-out, opacity 0.5s ease-in-out;
}

.chat-nav-enter-from,
.chat-nav-leave-to {
  opacity: 0;
  transform: translateX(100vw);
}
</style>
