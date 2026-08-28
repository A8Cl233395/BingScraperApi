<script setup lang="ts">
import { state } from '../store';
import { ref, computed } from 'vue';
import ConfirmModal from './ConfirmModal.vue';
import ModelSelector from './ModelSelector.vue';
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

// --- 悬停跟随选择框 ---
const hoveredId = ref<number | null>(null);
const indicatorTop = ref(0);
const indicatorHeight = ref(0);
const indicatorReady = ref(false);
const justClickedId = ref<number | null>(null);
let clickAnimTimer: ReturnType<typeof setTimeout> | null = null;

const indicatorVisible = computed(
  () => hoveredId.value !== null && hoveredId.value !== state.currentChatId
);

const hoverIndicatorStyle = computed(() => ({
  transform: `translateY(${indicatorTop.value}px)`,
  height: `${indicatorHeight.value}px`,
  transition: indicatorReady.value
    ? 'transform 0.18s ease-out, height 0.18s ease-out, opacity 0.15s ease'
    : 'opacity 0.15s ease',
}));

const moveIndicatorTo = (el: HTMLElement) => {
  indicatorTop.value = el.offsetTop;
  indicatorHeight.value = el.offsetHeight;
};

const onItemEnter = (e: MouseEvent, id: number) => {
  const el = e.currentTarget as HTMLElement;
  if (hoveredId.value === null) {
    // 首次进入列表时直接定位，不做滑动动画
    indicatorReady.value = false;
    moveIndicatorTo(el);
    requestAnimationFrame(() => {
      indicatorReady.value = true;
    });
  } else {
    moveIndicatorTo(el);
  }
  hoveredId.value = id;
};

const onListLeave = () => {
  hoveredId.value = null;
};

const repositionIndicator = () => {
  if (hoveredId.value === null) return;
  const el = chatListRef.value?.querySelector<HTMLElement>(
    `[data-chat-id="${hoveredId.value}"]`
  );
  if (!el) return;
  indicatorReady.value = false;
  moveIndicatorTo(el);
  requestAnimationFrame(() => {
    indicatorReady.value = true;
  });
};

// 左上角相对盒子中心的锥形角度（0° = 正上方，顺时针）
const sweepFrom = (w: number, h: number) => 270 + (Math.atan(h / w) * 180) / Math.PI;

// 生成 linear() 缓动采样：让锥形角度沿周长弧长线性推进（匀速扫过边框）
const buildSweepEasing = (w: number, h: number, from: number): string => {
  const hw = w / 2;
  const hh = h / 2;
  const deg = (r: number) => (r * 180) / Math.PI;
  const N = 60;
  const pts: string[] = ['0'];
  let prev = from;
  for (let i = 1; i <= N; i++) {
    const s = (i / N) * 2 * (w + h);
    let r: number;
    if (s <= w) {
      r = Math.atan2(-hw + s, hh); // 顶边
    } else if (s <= w + h) {
      r = Math.atan2(hw, hh - (s - w)); // 右边
    } else if (s <= 2 * w + h) {
      r = Math.atan2(hw - (s - w - h), -hh); // 底边
    } else {
      r = Math.atan2(-hw, -(hh - (s - 2 * w - h))); // 左边
    }
    let a = ((deg(r) % 360) + 360) % 360;
    while (a < prev) a += 360;
    prev = a;
    pts.push(`${((a - from) / 360).toFixed(4)} ${((i / N) * 100).toFixed(2)}%`);
  }
  return `linear(${pts.join(', ')})`;
};

// 点击时触发虚线→实线扫描动画，起点精确对准条目左上角且沿周长匀速
const sweepEasingCache = new Map<string, string>();
const getSweepEasing = (w: number, h: number, from: number): string => {
  const key = `${w}x${h}x${from.toFixed(1)}`;
  let easing = sweepEasingCache.get(key);
  if (!easing) {
    easing = buildSweepEasing(w, h, from);
    sweepEasingCache.set(key, easing);
  }
  return easing;
};

let sweepTarget: number | null = null;

const onItemClick = (e: MouseEvent, id: number) => {
  const el = e.currentTarget as HTMLElement;
  const w = el.offsetWidth;
  const h = el.offsetHeight;
  const from = sweepFrom(w, h);
  el.style.setProperty('--sb-from', `${from.toFixed(2)}deg`);
  el.style.animationTimingFunction = getSweepEasing(w, h, from);
  sweepTarget = id;
  if (justClickedId.value !== id) {
    justClickedId.value = id;
  } else {
    // 连续点击同一条目：class 不变不会重播动画，先移除再在下一帧恢复
    justClickedId.value = null;
    requestAnimationFrame(() => {
      if (sweepTarget === id) justClickedId.value = id;
    });
  }
  if (clickAnimTimer) clearTimeout(clickAnimTimer);
  clickAnimTimer = setTimeout(() => {
    justClickedId.value = null;
  }, 600);
};

// --- 滚动加载更多 ---
const checkScrollBottom = () => {
  const el = chatListRef.value;
  if (!el) return;
  isAtBottom.value = el.scrollTop + el.clientHeight >= el.scrollHeight - 10;
};

let scrollTimeout: ReturnType<typeof setTimeout> | null = null;
let scrollRaf = 0;

const handleScroll = () => {
  // rAF 节流：滚动高频触发时每帧最多更新一次 indicator/底部遮罩/滚动速度
  if (!scrollRaf) {
    scrollRaf = requestAnimationFrame(() => {
      scrollRaf = 0;
      const el = chatListRef.value;
      if (!el) return;
      checkScrollBottom();
      repositionIndicator();
      state.updateScrollSpeed(el.scrollTop);
    });
  }
  if (scrollTimeout) clearTimeout(scrollTimeout);
  scrollTimeout = setTimeout(() => {
    const el = chatListRef.value;
    if (el && el.scrollTop + el.clientHeight >= el.scrollHeight - 50) {
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
        <button
          @click="state.isSidebarOpen = !state.isSidebarOpen"
          class="-my-0.5 w-8 h-8 flex items-center justify-center text-text-muted hover:text-text-main hover:bg-bg-hover transition-colors"
          :title="state.isMobile ? '关闭侧栏' : '收起侧栏'"
        >
          <component :is="state.isMobile ? 'X' : 'AlignLeft'" />
        </button>
      </div>
      <div class="mx-4 mb-4 flex items-center gap-2">
        <a
          href="#/"
          @click.prevent="state.currentChatId = null"
          class="shrink-0 w-8 h-8 flex items-center justify-center border border-border-input text-text-muted hover:text-text-main hover:bg-bg-hover transition-colors no-underline"
          title="新对话"
        >
          <Plus />
        </a>
        <ModelSelector merged class="flex-1 min-w-0" />
      </div>
      
      <div class="relative flex-1 min-h-0 overflow-hidden">
        <!-- 下拉刷新指示器 -->
        <div 
          class="absolute top-0 left-0 right-0 flex items-center justify-center overflow-hidden pointer-events-none z-10"
          :style="indicatorStyle"
        >
          <div class="flex items-center gap-2 text-xs text-text-placeholder">
            <ArrowDown 
              v-if="!isRefreshing"
              class="transition-transform duration-200"
              :style="{ transform: `rotate(${arrowRotation}deg)` }"
            />
            <Loader2 
              v-else
              class="animate-spin"
            />
            <span>{{ isRefreshing ? '刷新中...' : pullDistance >= PULL_THRESHOLD ? '释放刷新' : '下拉刷新' }}</span>
          </div>
        </div>

        <div 
          ref="chatListRef"
          class="relative h-full overflow-y-auto px-2 space-y-1"
          :style="pullStyle"
          @scroll="handleScroll"
          @wheel="handleWheel"
          @mouseleave="onListLeave"
          @touchstart.passive="handleListTouchStart"
          @touchmove="handleListTouchMove"
          @touchend="handleListTouchEnd"
          @touchcancel="handleListTouchEnd"
        >
          <!-- 悬停跟随选择框：淡白背景 + 蓝色虚线（左右留 8px 与条目同宽） -->
          <div
            class="hover-indicator absolute left-2 right-2 top-0 z-0 pointer-events-none"
            :class="{ 'is-visible': indicatorVisible }"
            :style="hoverIndicatorStyle"
          ></div>
          <!-- 悬停工具条：垃圾桶与选择框同步滑动 -->
          <div
            v-if="!state.isMobile"
            class="hover-toolbar absolute left-2 right-2 top-0 z-30 pointer-events-none"
            :class="{ 'is-visible': hoveredId !== null }"
            :style="hoverIndicatorStyle"
          >
            <button
              @click="hoveredId !== null && handleDelete(hoveredId)"
              class="absolute right-2 top-1/2 -translate-y-1/2 text-text-placeholder hover:text-danger-main transition-colors p-1 flex items-center justify-center pointer-events-auto"
              title="删除聊天"
            >
              <Trash2 class="text-xs" />
            </button>
          </div>
          <a 
            v-for="chat in state.chats" 
            :key="chat[0]"
            :href="`#/${chat[0]}`"
            :data-chat-id="chat[0]"
            @mouseenter="onItemEnter($event, chat[0])"
            @click="onItemClick($event, chat[0])"
            @touchstart="handleTouchStart($event, chat[0])"
            @touchend="handleTouchEnd"
            @touchmove="handleTouchEnd"
            @touchcancel="handleTouchEnd"
            @contextmenu="state.isMobile ? $event.preventDefault() : null"
            class="chat-item relative flex items-center justify-between p-2.5 cursor-pointer text-text-main no-underline"
            :class="[
              state.currentChatId === chat[0] ? 'is-active' : '',
              justClickedId === chat[0] ? 'is-anim' : '',
              pressingChatId === chat[0] ? 'scale-[0.98] bg-bg-hover' : ''
            ]"
          >
            <!-- 选择框图层：虚线（扫描轨道）+ 实线（选中态） -->
            <span class="box-dashed" aria-hidden="true"></span>
            <span class="box-solid" aria-hidden="true"></span>
            <!-- Selected effect -->
            <Transition name="fade">
              <div 
                v-if="pressingChatId === chat[0]"
                class="absolute inset-0 bg-white/20 z-20 pointer-events-none"
              ></div>
            </Transition>
            <span class="relative z-10 truncate text-sm pr-6">{{ chat[1] }}</span>
          </a>
          <!-- Loading indicator -->
          <div v-if="state.isLoadingHistory" class="text-center py-3 text-xs text-text-placeholder">
            <Loader2 class="animate-spin mr-1" /> 加载中...
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
          class="flex items-center gap-2 px-3 py-2 text-sm text-text-muted hover:text-text-main hover:bg-bg-hover transition-colors"
        >
          <UserCog />
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

/* 选择框蓝色：跟随明暗主题 */
.chat-item,
.hover-indicator {
  --sb-blue: var(--primary);
}
:global(html.dark) .chat-item,
:global(html.dark) .hover-indicator {
  --sb-blue: var(--info);
}

/* 悬停跟随选择框：稍淡白色背景 + 蓝色虚线 */
.hover-indicator {
  background-color: rgba(255, 255, 255, 0.07);
  border: 1px dashed var(--sb-blue);
  opacity: 0;
}
.hover-indicator.is-visible {
  opacity: 1;
}
:global(html:not(.dark)) .hover-indicator {
  background-color: rgba(255, 255, 255, 0.65);
}

/* 悬停工具条（垃圾桶）：与选择框同步滑动，悬停激活项时选择框隐藏但工具条保留 */
.hover-toolbar {
  opacity: 0;
}
.hover-toolbar.is-visible {
  opacity: 1;
}

/* 选中态背景：比悬停稍亮 */
.chat-item.is-active {
  background-color: rgba(255, 255, 255, 0.12);
}
:global(html:not(.dark)) .chat-item.is-active {
  background-color: rgba(255, 255, 255, 0.85);
}

/* 扫描角度：360° 为完整实线（不支持 @property 时退化为直接显示） */
@property --sb-sweep {
  syntax: '<angle>';
  inherits: true;
  initial-value: 360deg;
}

.chat-item {
  --sb-sweep: 360deg;
  /* 颜色 + 按压缩放（scale-[0.98]）统一平滑过渡 */
  transition: color 0.15s ease, background-color 0.15s ease, transform 0.15s ease;
}

/* 选中态选择框：稍亮白色外圈 + 蓝色实线 */
.box-solid,
.box-dashed {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.2s ease;
}
.box-solid {
  border: 1px solid var(--sb-blue);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.3);
  /* 实线框：仅已扫过的区域可见；起点角度由 JS 写入 --sb-from，对准左上角 */
  -webkit-mask: conic-gradient(from var(--sb-from, 315deg), #000 var(--sb-sweep), transparent var(--sb-sweep));
  mask: conic-gradient(from var(--sb-from, 315deg), #000 var(--sb-sweep), transparent var(--sb-sweep));
}
.box-dashed {
  border: 1px dashed var(--sb-blue);
  /* 虚线框：仅未扫到的区域可见，被实线逐段覆盖 */
  -webkit-mask: conic-gradient(from var(--sb-from, 315deg), transparent var(--sb-sweep), #000 var(--sb-sweep));
  mask: conic-gradient(from var(--sb-from, 315deg), transparent var(--sb-sweep), #000 var(--sb-sweep));
}
.chat-item.is-active .box-solid {
  opacity: 1;
}

/* 点击动画：实线从左上角沿虚线扫一圈逐段覆盖；角度匀速，实际线速度由 JS 写入的
   linear() 缓动按条目宽高比修正（不支持的浏览器退化为匀角速） */
.chat-item.is-anim {
  animation: sb-sweep 0.45s linear both;
}
.chat-item.is-anim .box-solid,
.chat-item.is-anim .box-dashed {
  opacity: 1;
  transition: none;
}

@keyframes sb-sweep {
  from { --sb-sweep: 0deg; }
  to { --sb-sweep: 360deg; }
}
</style>
