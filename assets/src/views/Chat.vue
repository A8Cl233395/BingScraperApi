<script setup lang="ts">
import { onMounted, ref, computed, watch } from 'vue';
import { state } from '../store';
import { isMobileDevice } from '../utils/device';
import Sidebar from '../components/Sidebar.vue';
import ModelSelector from '../components/ModelSelector.vue';
import ChatInput from '../components/ChatInput.vue';
import MessageList from '../components/MessageList.vue';
import ImagePreview from '../components/ImagePreview.vue';
import TextSelectionOverlay from '../components/TextSelectionOverlay.vue';

const messageListRef = ref<any>(null);
const mobileKeyboardActive = ref(false);

const isChatStarted = computed(() => {
  return state.currentChatId !== null || (messageListRef.value?.messages?.length > 0);
});

const handleSend = (content: any) => {
  messageListRef.value?.handleSend(content);
};

const checkDevice = () => {
  state.isMobile = isMobileDevice();
  state.isSidebarOpen = !state.isMobile;
};

const startNewChat = () => {
  state.currentChatId = null;
};

const handlePopState = () => {
  const urlParams = new URLSearchParams(window.location.search);
  const idFromUrl = urlParams.get('id');
  if (idFromUrl) {
    const parsedId = parseInt(idFromUrl, 10);
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

onMounted(() => {
  const urlParams = new URLSearchParams(window.location.search);
  const idFromUrl = urlParams.get('id');
  if (idFromUrl) {
    const parsedId = parseInt(idFromUrl, 10);
    if (!isNaN(parsedId)) {
      state.currentChatId = parsedId;
    }
  }

  checkDevice();
  window.addEventListener('resize', checkDevice);
  window.addEventListener('popstate', handlePopState);
  window.addEventListener('mousedown', () => state.isMouseDown = true);
  window.addEventListener('mouseup', () => {
    state.isMouseDown = false;
    // Immediate check after mouseup to catch the selection state
    const sel = window.getSelection();
    state.isTextSelected = !!(sel && !sel.isCollapsed);
  });
  window.addEventListener('touchstart', () => { state.isMouseDown = true; }, { passive: true });
  window.addEventListener('touchend', () => { 
    state.isMouseDown = false; 
    const sel = window.getSelection();
    state.isTextSelected = !!(sel && !sel.isCollapsed);
  }, { passive: true });
  window.addEventListener('touchcancel', () => { state.isMouseDown = false; }, { passive: true });
  window.addEventListener('selectionchange', () => {
    const sel = window.getSelection();
    state.isTextSelected = !!(sel && !sel.isCollapsed);
  });
  state.fetchHome();
});

watch(() => state.currentChatId, (newId) => {
  const url = new URL(window.location.href);
  const oldId = url.searchParams.get('id');
  const newIdStr = newId !== null ? newId.toString() : null;
  
  if (oldId !== newIdStr) {
    if (newId) {
      url.searchParams.set('id', newId.toString());
    } else {
      url.searchParams.delete('id');
    }
    window.history.pushState({}, '', url);
  }
});
</script>

<template>
  <div class="h-screen w-screen overflow-hidden" :class="state.isMobile ? '' : 'flex'">
    <Sidebar />

    <main class="flex-1 flex flex-col h-full relative min-w-0 bg-bg-main w-full">
      <header @dblclick="handleHeaderDblClick" class="h-14 flex items-center px-4 justify-between shrink-0 z-30 w-full bg-bg-main border-b border-border-main cursor-pointer select-none">
        <div class="flex items-center gap-3">
          <button 
            @click="state.isSidebarOpen = !state.isSidebarOpen" 
            @dblclick.stop
            class="text-text-muted hover:text-text-main w-8 h-8 flex items-center justify-center rounded-md hover:bg-bg-hover transition-colors"
          >
            <FontAwesomeIcon :icon="['fas', state.isSidebarOpen ? 'align-left' : 'bars']" />
          </button>
          <button 
            @click="startNewChat" 
            @dblclick.stop
            class="text-text-muted hover:text-text-main w-8 h-8 flex items-center justify-center rounded-md hover:bg-bg-hover transition-colors" 
            title="新对话"
          >
            <FontAwesomeIcon :icon="['far', 'pen-to-square']" />
          </button>
          
          <ModelSelector />
        </div>
      </header>

      <div class="flex-1 flex flex-col overflow-hidden relative transition-all duration-500 ease-in-out" :class="mobileKeyboardActive ? 'justify-start' : 'justify-center'">
        <MessageList 
          ref="messageListRef" 
          :class="[
            'transition-all duration-500 ease-in-out',
            isChatStarted ? 'flex-1 opacity-100' : 'h-0 opacity-0 pointer-events-none overflow-hidden'
          ]"
        />
  
        <ChatInput :isChatStarted="isChatStarted" @send="handleSend" @mobile-focus="mobileKeyboardActive = true" @mobile-blur="mobileKeyboardActive = false" />
      </div>
    </main>
    
    <ImagePreview />
    <TextSelectionOverlay />
  </div>
</template>
