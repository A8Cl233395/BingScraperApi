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
          <a 
            href="#/"
            @click.prevent="startNewChat" 
            @dblclick.stop
            class="text-text-muted hover:text-text-main w-8 h-8 flex items-center justify-center rounded-md hover:bg-bg-hover transition-colors no-underline" 
            title="新对话"
          >
            <FontAwesomeIcon :icon="['far', 'pen-to-square']" />
          </a>
          
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
  
        <ChatInput ref="chatInputRef" :isChatStarted="isChatStarted" @send="handleSend" @stop="handleStop" @mobile-focus="mobileKeyboardActive = true" @mobile-blur="mobileKeyboardActive = false" />
      </div>
    </main>
    
    <ImagePreview />
    <TextSelectionOverlay />
    <PetAvatar v-if="state.petEnabled" />
  </div>
</template>
