<script setup lang="ts">
import { state } from '../store';
import { ref, computed } from 'vue';
import ConfirmModal from './ConfirmModal.vue';
import { useLongPress } from '../composables/useLongPress';

const chatListRef = ref<HTMLElement | null>(null);
const showDeleteConfirm = ref(false);
const chatToDelete = ref<number | null>(null);
const pressingChatId = ref<number | null>(null);
const isAtBottom = ref(false);

const { startLongPress, cancelLongPress } = useLongPress({
  onPressStart: () => {},
});

// --- 下拉刷新 ---
const PULL_THRESHOLD = 40;
const PULL_MAX = 48;
const pullDistance = ref(0);
const isPulling = ref(false);
const isRefreshing = ref(false);
let startY = 0;
let canPull = false;

const pullStyle = computed(() => ({
  transform: `translateY(${pullDistance.value}px)`,
  transition: isPulling.value ? 'none' : 'transform 0.3s cubic-bezier(0.25, 0.46, 0.45, 0.94)',
}));

const indicatorStyle = computed(() => {
  const progress = Math.min(1, pullDistance.value / PULL_THRESHOLD);
  return {
    height: `${pullDistance.value}px`,
    opacity: Math.min(1, progress * 1.5),
  };
});

const arrowRotation = computed(() => {
  if (pullDistance.value >= PULL_THRESHOLD) return 180;
  return (pullDistance.value / PULL_THRESHOLD) * 180;
});

const handleListTouchStart = (e: TouchEvent) => {
  const el = chatListRef.value;
  if (!el || el.scrollTop > 0 || isRefreshing.value) return;
  canPull = true;
  startY = e.touches[0].clientY;
};

const handleListTouchMove = (e: TouchEvent) => {
  if (!canPull) return;
  const el = chatListRef.value;
  if (!el) return;
  const dy = e.touches[0].clientY - startY;
  if (dy <= 0) {
    pullDistance.value = 0;
    isPulling.value = false;
    return;
  }
  if (el.scrollTop > 0) {
    canPull = false;
    pullDistance.value = 0;
    isPulling.value = false;
    return;
  }
  e.preventDefault();
  isPulling.value = true;
  pullDistance.value = Math.min(PULL_MAX, dy * 0.5);
};

const handleListTouchEnd = async () => {
  if (!isPulling.value) {
    canPull = false;
    return;
  }
  canPull = false;
  isPulling.value = false;

  if (pullDistance.value >= PULL_THRESHOLD && state.chats.length > 0) {
    pullDistance.value = 48;
    isRefreshing.value = true;
    await state.fetchNewChats();
    isRefreshing.value = false;
  }
  pullDistance.value = 0;
};

// 桌面端滚轮 —— 累积滚轮量模拟下拉
let wheelAccum = 0;
let wheelDecay: ReturnType<typeof setTimeout> | null = null;

const handleWheel = (e: WheelEvent) => {
  const el = chatListRef.value;
  if (!el || e.deltaY >= 0 || el.scrollTop > 0 || isRefreshing.value) return;

  isPulling.value = true;
  wheelAccum += Math.abs(e.deltaY) * 0.3;
  pullDistance.value = Math.min(PULL_MAX, wheelAccum);

  if (wheelDecay) clearTimeout(wheelDecay);
  wheelDecay = setTimeout(async () => {
    if (pullDistance.value >= PULL_THRESHOLD && state.chats.length > 0) {
      pullDistance.value = 48;
      isPulling.value = false;
      isRefreshing.value = true;
      await state.fetchNewChats();
      isRefreshing.value = false;
    } else {
      isPulling.value = false;
    }
    pullDistance.value = 0;
    wheelAccum = 0;
  }, 300);
};

// --- 滚动加载更多 ---
const checkScrollBottom = () => {
  const el = chatListRef.value;
  if (!el) return;
  isAtBottom.value = el.scrollTop + el.clientHeight >= el.scrollHeight - 10;
};

let scrollTimeout: ReturnType<typeof setTimeout> | null = null;

const handleScroll = () => {
  const el = chatListRef.value;
  if (!el) return;
  checkScrollBottom();
  state.updateScrollSpeed(el.scrollTop);
  if (scrollTimeout) clearTimeout(scrollTimeout);
  scrollTimeout = setTimeout(() => {
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 50) {
      state.fetchMoreHistory();
    }
  }, 100);
};

// --- 长按删除 ---
const handleTouchStart = (e: TouchEvent, id: number) => {
  if (!state.isMobile) return;
  pressingChatId.value = id;
  chatToDelete.value = id;
  startLongPress(e, () => {
    showDeleteConfirm.value = true;
    pressingChatId.value = null;
  });
};

const handleTouchEnd = () => {
  cancelLongPress();
  pressingChatId.value = null;
};

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
        <button @click="state.isSidebarOpen = false" v-if="state.isMobile" class="text-text-muted hover:text-text-main">
          <FontAwesomeIcon :icon="['fas', 'xmark']" />
        </button>
      </div>
      
      <a 
        href="#/"
        @click.prevent="state.currentChatId = null"
        class="px-4 py-2 border border-dashed border-border-input rounded-md mx-4 mb-4 text-sm hover:bg-bg-hover flex items-center justify-center cursor-pointer text-text-muted transition-colors no-underline"
      >
        <FontAwesomeIcon :icon="['fas', 'plus']" class="mr-2" /> 新对话
      </a>
      
      <div class="relative flex-1 min-h-0 overflow-hidden">
        <!-- 下拉刷新指示器 -->
        <div 
          class="absolute top-0 left-0 right-0 flex items-center justify-center overflow-hidden pointer-events-none z-10"
          :style="indicatorStyle"
        >
          <div class="flex items-center gap-2 text-xs text-text-placeholder">
            <FontAwesomeIcon 
              v-if="!isRefreshing"
              :icon="['fas', 'arrow-down']" 
              class="transition-transform duration-200"
              :style="{ transform: `rotate(${arrowRotation}deg)` }"
            />
            <FontAwesomeIcon 
              v-else
              :icon="['fas', 'spinner']" 
              spin
            />
            <span>{{ isRefreshing ? '刷新中...' : pullDistance >= PULL_THRESHOLD ? '释放刷新' : '下拉刷新' }}</span>
          </div>
        </div>

        <div 
          ref="chatListRef"
          class="h-full overflow-y-auto px-2 space-y-1"
          :style="pullStyle"
          @scroll="handleScroll"
          @wheel="handleWheel"
          @touchstart.passive="handleListTouchStart"
          @touchmove="handleListTouchMove"
          @touchend="handleListTouchEnd"
          @touchcancel="handleListTouchEnd"
        >
          <a 
            v-for="chat in state.chats" 
            :key="chat[0]"
            :href="`#/${chat[0]}`"
            @touchstart="handleTouchStart($event, chat[0])"
            @touchend="handleTouchEnd"
            @touchmove="handleTouchEnd"
            @touchcancel="handleTouchEnd"
            @contextmenu="state.isMobile ? $event.preventDefault() : null"
            class="group relative flex items-center justify-between p-2.5 rounded-md hover:bg-bg-hover cursor-pointer text-text-main transition-colors no-underline"
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
              @click.prevent.stop="handleDelete(chat[0])"
              class="hidden group-hover:block text-text-placeholder hover:text-danger-main absolute right-2 z-20 transition-colors p-1"
            >
              <FontAwesomeIcon :icon="['fas', 'trash-can']" class="text-xs" />
            </button>
          </a>
          <!-- Loading indicator -->
          <div v-if="state.isLoadingHistory" class="text-center py-3 text-xs text-text-placeholder">
            <FontAwesomeIcon :icon="['fas', 'spinner']" spin class="mr-1" /> 加载中...
          </div>
          <div v-if="!state.hasMoreHistory && state.chats.length > 0" class="text-center py-3 text-xs text-text-placeholder">
            没有更多了
          </div>
        </div>
        <!-- Bottom fade-out gradient -->
        <Transition name="fade">
          <div 
            v-if="!isAtBottom"
            class="absolute bottom-0 left-0 right-0 h-12 pointer-events-none z-10"
            style="background: linear-gradient(to top, var(--bg-panel), transparent);"
          ></div>
        </Transition>
      </div>

      <div class="p-3 border-t border-border-main">
        <a 
          href="/profile"
          class="flex items-center gap-2 px-3 py-2 rounded-md text-sm text-text-muted hover:text-text-main hover:bg-bg-hover transition-colors"
        >
          <FontAwesomeIcon :icon="['fas', 'user-gear']" />
          <span>个人资料</span>
        </a>
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
