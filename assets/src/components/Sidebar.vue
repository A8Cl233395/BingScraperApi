<script setup lang="ts">
import { state } from '../store';
import { ref, onBeforeUnmount } from 'vue';
import ConfirmModal from './ConfirmModal.vue';

const longPressTimer = ref<number | null>(null);
const preLongPressTimer = ref<number | null>(null);
const chatListRef = ref<HTMLElement | null>(null);
const showDeleteConfirm = ref(false);
const chatToDelete = ref<number | null>(null);
const pressingChatId = ref<number | null>(null);

const handleChatClick = (id: number) => {
  state.currentChatId = id;
};

const startLongPress = (id: number) => {
  if (state.isMobile) {
    cancelLongPress();
    preLongPressTimer.value = window.setTimeout(() => {
      pressingChatId.value = id;
      longPressTimer.value = window.setTimeout(() => {
        chatToDelete.value = id;
        showDeleteConfirm.value = true;
        pressingChatId.value = null;
      }, 600);
    }, 150); // Delay before starting long-press animation and timer
  }
};

const cancelLongPress = () => {
  if (preLongPressTimer.value) {
    clearTimeout(preLongPressTimer.value);
    preLongPressTimer.value = null;
  }
  if (longPressTimer.value) {
    clearTimeout(longPressTimer.value);
    longPressTimer.value = null;
  }
  pressingChatId.value = null;
};

onBeforeUnmount(() => {
  cancelLongPress();
});

const handleDelete = (id: number) => {
  chatToDelete.value = id;
  showDeleteConfirm.value = true;
};

const confirmDelete = () => {
  if (chatToDelete.value !== null) {
    state.deleteChat(chatToDelete.value);
    chatToDelete.value = null;
    showDeleteConfirm.value = false;
  }
};

const handleScroll = () => {
  const el = chatListRef.value;
  if (!el) return;
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 50) {
    state.fetchMoreHistory();
  }
};
</script>

<template>
  <aside 
    class="bg-bg-panel h-full transition-all duration-300 ease-in-out shrink-0 z-100 shadow-[1px_0_5px_rgba(0,0,0,0.05)] overflow-hidden"
    :class="[
      state.isSidebarOpen ? 'translate-x-0' : '-translate-x-full',
      state.isMobile ? 'fixed inset-y-0 left-0 w-72' : 'relative w-64',
      !state.isSidebarOpen && !state.isMobile ? 'md:-ml-64 md:translate-x-0 md:border-r-0' : 'border-r border-border-main md:ml-0'
    ]"
  >
    <div :class="state.isMobile ? 'w-72' : 'w-64'" class="h-full flex flex-col shrink-0">
      <div class="p-4 flex justify-between items-center">
        <span class="font-bold text-lg text-text-main">AI Chat</span>
        <button @click="state.isSidebarOpen = false" class="md:hidden text-text-muted hover:text-text-main">
          <i class="fas fa-times"></i>
        </button>
      </div>
      
      <div 
        @click="state.currentChatId = null"
        class="px-4 py-2 border border-dashed border-border-input rounded-md mx-4 mb-4 text-sm hover:bg-bg-hover flex items-center justify-center cursor-pointer text-text-muted transition-colors"
      >
        <i class="fas fa-plus mr-2"></i> 新对话
      </div>
      
      <div 
        ref="chatListRef"
        class="flex-1 overflow-y-auto px-2 space-y-1"
        @scroll="handleScroll"
      >
        <div 
          v-for="chat in state.chats" 
          :key="chat[0]"
          @click="handleChatClick(chat[0])"
          @touchstart="startLongPress(chat[0])"
          @touchend="cancelLongPress"
          @touchmove="cancelLongPress"
          @touchcancel="cancelLongPress"
          @contextmenu.prevent
          class="group relative flex items-center justify-between p-2.5 rounded-md hover:bg-bg-hover cursor-pointer text-text-main transition-colors"
          :class="[
            state.currentChatId === chat[0] ? 'bg-bg-active' : '',
            pressingChatId === chat[0] ? 'scale-[0.98] bg-bg-hover' : ''
          ]"
        >
          <!-- Selected effect -->
          <Transition name="fade">
            <div 
              v-if="pressingChatId === chat[0]"
              class="absolute inset-0 bg-white/20 z-20 pointer-events-none"
            ></div>
          </Transition>
          <span class="relative z-10 truncate text-sm pr-6">{{ chat[1] }}</span>
          <button 
            v-if="!state.isMobile"
            @click.stop="handleDelete(chat[0])"
            class="hidden group-hover:block text-text-placeholder hover:text-danger-main absolute right-2 z-20 transition-colors p-1"
          >
            <i class="fas fa-trash-alt text-xs"></i>
          </button>
        </div>
        <!-- Loading indicator -->
        <div v-if="state.isLoadingHistory" class="text-center py-3 text-xs text-text-placeholder">
          <i class="fas fa-spinner fa-spin mr-1"></i> 加载中...
        </div>
        <div v-if="!state.hasMoreHistory && state.chats.length > 0" class="text-center py-3 text-xs text-text-placeholder">
          没有更多了
        </div>
      </div>
    </div>
  </aside>
  
  <!-- Mobile Overlay -->
  <div 
    v-if="state.isSidebarOpen && state.isMobile" 
    @click="state.isSidebarOpen = false" 
    class="fixed inset-0 z-90 transition-opacity"
    style="background-color: rgba(0, 0, 0, 0.4);"
  ></div>

  <!-- Delete Confirmation Modal -->
  <ConfirmModal 
    :show="showDeleteConfirm"
    title="删除聊天"
    message="确定要删除该聊天记录吗？此操作不可撤销。"
    confirmText="删除"
    cancelText="取消"
    :isDanger="true"
    @confirm="confirmDelete"
    @cancel="showDeleteConfirm = false"
  />
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
