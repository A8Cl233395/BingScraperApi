<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed, watch, defineAsyncComponent } from 'vue';
import { state } from '../store';
import Sidebar from '../components/Sidebar.vue';
import ModelSelector from '../components/ModelSelector.vue';
import ChatInput from '../components/ChatInput.vue';
import MessageList from '../components/MessageList.vue';
import ImagePreview from '../components/ImagePreview.vue';
import TextSelectionOverlay from '../components/TextSelectionOverlay.vue';

const PetAvatar = defineAsyncComponent(() => import('../components/PetAvatar.vue'));

const messageListRef = ref<any>(null);
const chatInputRef = ref<any>(null);
const mobileKeyboardActive = ref(false);

const isChatStarted = computed(() => {
  return state.currentChatId !== null || (messageListRef.value?.messages?.length > 0);
});

// 退出到新对话时视为未开始：容器塌缩 + 上滑出视口（进入动画的逆过程），
// 数据在动画结束后才清空，期间 isChatStarted 仍为 true
const isChatActive = computed(() => isChatStarted.value && !state.isChatExiting);

const handleSend = (content: any) => {
  messageListRef.value?.handleSend(content);
};

const handleStop = async () => {
  const userContent = await messageListRef.value?.handleCancel();
  if (userContent) {
    chatInputRef.value?.restoreInput(userContent);
  }
};

const checkDevice = () => {
  state.isSidebarOpen = !state.isMobile;
};

const startNewChat = () => {
  state.currentChatId = null;
};

const handleHashChange = () => {
  const hash = window.location.hash;
  const match = hash.match(/^#\/(\d+)$/);
  if (match) {
    const parsedId = parseInt(match[1], 10);
    if (!isNaN(parsedId)) {
      state.currentChatId = parsedId;
    }
  } else {
    state.currentChatId = null;
  }
};

const handleHeaderDblClick = () => {
  messageListRef.value?.scrollToTop();
};

const handleMouseDown = () => { state.isMouseDown = true; };
const handleMouseUp = () => {
  state.isMouseDown = false;
  const sel = window.getSelection();
  state.isTextSelected = !!(sel && !sel.isCollapsed);
};
const handleTouchStart = () => { state.isMouseDown = true; };
const handleTouchEnd = () => {
  state.isMouseDown = false;
  const sel = window.getSelection();
  state.isTextSelected = !!(sel && !sel.isCollapsed);
};
const handleTouchCancel = () => { state.isMouseDown = false; };
const handleSelectionChange = () => {
  const sel = window.getSelection();
  state.isTextSelected = !!(sel && !sel.isCollapsed);
};

onMounted(() => {
  const hash = window.location.hash;
  const match = hash.match(/^#\/(\d+)$/);
  if (match) {
    const parsedId = parseInt(match[1], 10);
    if (!isNaN(parsedId)) {
      state.currentChatId = parsedId;
    }
  }

  checkDevice();
  window.addEventListener('hashchange', handleHashChange);
  window.addEventListener('mousedown', handleMouseDown);
  window.addEventListener('mouseup', handleMouseUp);
  window.addEventListener('touchstart', handleTouchStart, { passive: true });
  window.addEventListener('touchend', handleTouchEnd, { passive: true });
  window.addEventListener('touchcancel', handleTouchCancel, { passive: true });
  window.addEventListener('selectionchange', handleSelectionChange);
  state.fetchHome();
});

onUnmounted(() => {
  window.removeEventListener('hashchange', handleHashChange);
  window.removeEventListener('mousedown', handleMouseDown);
  window.removeEventListener('mouseup', handleMouseUp);
  window.removeEventListener('touchstart', handleTouchStart);
  window.removeEventListener('touchend', handleTouchEnd);
  window.removeEventListener('touchcancel', handleTouchCancel);
  window.removeEventListener('selectionchange', handleSelectionChange);
});

watch(() => state.currentChatId, (newId) => {
  const newHash = newId ? `#/${newId}` : '#/';
  if (window.location.hash !== newHash) {
    window.history.pushState({}, '', newHash);
  }
});

watch(
  [() => state.currentChatId, () => state.chats],
  () => {
    const chat = state.chats.find(c => c[0] === state.currentChatId);
    document.title = chat ? `${chat[1]} | AI Chat` : 'AI Chat';
  },
  { deep: true }
);
</script>

<template>
  <div class="h-screen w-screen overflow-hidden" :class="state.isMobile ? '' : 'flex'">
    <Sidebar />

    <main class="flex-1 flex flex-col h-full relative min-w-0 bg-bg-main w-full">
      <header
        @dblclick="handleHeaderDblClick"
        class="flex items-center px-4 justify-between shrink-0 z-30 w-full h-14 bg-bg-main border-b border-border-main cursor-pointer select-none transition-[translate,margin-bottom] duration-150 ease-[cubic-bezier(0.4,0,0.2,1)]"
        :class="!state.isMobile && state.isSidebarOpen ? 'translate-x-full -mb-14 pointer-events-none' : 'translate-x-0 mb-0'"
      >
        <div class="flex items-center gap-3">
          <button 
            @click="state.isSidebarOpen = !state.isSidebarOpen" 
            @dblclick.stop
            class="text-text-muted hover:text-text-main w-8 h-8 flex items-center justify-center hover:bg-bg-hover transition-colors"
          >
            <component :is="state.isSidebarOpen ? 'AlignLeft' : 'Menu'" />
          </button>
          <a 
            href="#/"
            @click.prevent="startNewChat" 
            @dblclick.stop
            class="text-text-muted hover:text-text-main w-8 h-8 flex items-center justify-center hover:bg-bg-hover transition-colors no-underline" 
            title="新对话"
          >
            <SquarePen />
          </a>
          
          <ModelSelector />
        </div>
      </header>

      <div class="flex-1 flex flex-col overflow-hidden relative transition-all duration-500 ease-in-out" :class="mobileKeyboardActive ? 'justify-start' : 'justify-center'">
        <MessageList 
          ref="messageListRef" 
          :class="[
            'transition-all duration-500 ease-in-out',
            isChatActive ? 'flex-1 opacity-100 translate-y-0' : 'h-0 opacity-0 pointer-events-none overflow-hidden -translate-y-[100vh]'
          ]"
        />

        <ChatInput ref="chatInputRef" :isChatStarted="isChatActive" @send="handleSend" @stop="handleStop" @mobile-focus="mobileKeyboardActive = true" @mobile-blur="mobileKeyboardActive = false" />
      </div>
    </main>
    
    <ImagePreview />
    <TextSelectionOverlay />
    <PetAvatar v-if="state.petEnabled" />
  </div>
</template>
