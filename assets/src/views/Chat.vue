<script setup lang="ts">
import { onMounted, ref, computed } from 'vue';
import { state } from '../store';
import { isMobileDevice } from '../utils/device';
import Sidebar from '../components/Sidebar.vue';
import ModelSelector from '../components/ModelSelector.vue';
import ChatInput from '../components/ChatInput.vue';
import MessageList from '../components/MessageList.vue';
import ImagePreview from '../components/ImagePreview.vue';
import TextSelectionOverlay from '../components/TextSelectionOverlay.vue';

const messageListRef = ref<any>(null);

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

onMounted(() => {
  checkDevice();
  window.addEventListener('resize', checkDevice);
  window.addEventListener('mousedown', () => state.isMouseDown = true);
  window.addEventListener('mouseup', () => {
    state.isMouseDown = false;
    // Immediate check after mouseup to catch the selection state
    const sel = window.getSelection();
    state.isTextSelected = !!(sel && !sel.isCollapsed);
  });
  window.addEventListener('selectionchange', () => {
    const sel = window.getSelection();
    state.isTextSelected = !!(sel && !sel.isCollapsed);
  });
  state.fetchHome();
});
</script>

<template>
  <div class="h-screen w-screen overflow-hidden" :class="state.isMobile ? '' : 'flex'">
    <Sidebar />

    <main class="flex-1 flex flex-col h-full relative min-w-0 bg-bg-main w-full">
      <header class="h-14 flex items-center px-4 justify-between flex-shrink-0 z-30 w-full bg-bg-main border-b border-border-main">
        <div class="flex items-center gap-3">
          <button 
            @click="state.isSidebarOpen = !state.isSidebarOpen" 
            class="text-text-muted hover:text-text-main w-8 h-8 flex items-center justify-center rounded-md hover:bg-bg-hover transition-colors"
          >
            <i class="fas" :class="state.isSidebarOpen ? 'fa-align-left' : 'fa-bars'"></i>
          </button>
          <button 
            @click="startNewChat" 
            class="text-text-muted hover:text-text-main w-8 h-8 flex items-center justify-center rounded-md hover:bg-bg-hover transition-colors" 
            title="新对话"
          >
            <i class="far fa-pen-to-square"></i>
          </button>
          
          <ModelSelector />
        </div>
      </header>

      <div class="flex-1 flex flex-col overflow-hidden relative transition-all duration-500 ease-in-out justify-center">
        <MessageList 
          ref="messageListRef" 
          :class="[
            'transition-all duration-500 ease-in-out',
            isChatStarted ? 'flex-1 opacity-100' : 'h-0 opacity-0 pointer-events-none overflow-hidden'
          ]"
        />
  
        <ChatInput :isChatStarted="isChatStarted" @send="handleSend" />
      </div>
    </main>
    
    <ImagePreview />
    <TextSelectionOverlay />
  </div>
</template>
