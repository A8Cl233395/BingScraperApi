<script setup lang="ts">
import { state } from '../store';
import { ref, computed, nextTick } from 'vue';
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

// --- 标题搜索 ---
const SEARCH_DEBOUNCE = 300;
const isSearchOpen = ref(false);
const searchQuery = ref('');
const searchResults = ref<[number, string][]>([]);
const isSearching = ref(false);
const hasMoreSearch = ref(true);
const isLoadingMoreSearch = ref(false);
const searchInputRef = ref<HTMLInputElement | null>(null);
let searchDebounce: ReturnType<typeof setTimeout> | null = null;
let searchSeq = 0; // 递增序号，丢弃过期请求的结果
let isComposing = false; // 输入法组合状态

// 已应用到列表的查询词：搜索完成前不改动列表，输入过程中保持上一次的状态
const appliedQuery = ref('');
const isSearchMode = computed(() => isSearchOpen.value && appliedQuery.value !== '');
const displayChats = computed(() => (isSearchMode.value ? searchResults.value : state.chats));

// 应用搜索结果；列表内容发生整体切换时回到顶部并清掉悬停框
const applySearchResults = (query: string, results: [number, string][]) => {
  const shouldReset = query !== appliedQuery.value;
  appliedQuery.value = query;
  searchResults.value = results;
  if (shouldReset) resetListScroll();
};

const openSearch = () => {
  isSearchOpen.value = true;
  // preventScroll：聚焦瞬间避免浏览器为输入框滚动容器（侧栏内容比带 1px 右边框的内容盒宽 1px）
  nextTick(() => searchInputRef.value?.focus({ preventScroll: true }));
};

const cancelSearchDebounce = () => {
  if (searchDebounce) {
    clearTimeout(searchDebounce);
    searchDebounce = null;
  }
};

const clearSearch = () => {
  cancelSearchDebounce();
  searchSeq++;
  searchQuery.value = '';
  isSearching.value = false;
  hasMoreSearch.value = true;
  isLoadingMoreSearch.value = false;
  applySearchResults('', []);
};

const closeSearch = () => {
  isSearchOpen.value = false;
  clearSearch();
};

const handleClearSearch = () => {
  clearSearch();
  searchInputRef.value?.focus();
};

const toggleSearch = () => {
  if (isSearchOpen.value) closeSearch();
  else openSearch();
};

const runSearch = async () => {
  const query = searchQuery.value.trim();
  const seq = ++searchSeq;
  if (!query) {
    isSearching.value = false;
    applySearchResults('', []);
    return;
  }
  isSearching.value = true;
  hasMoreSearch.value = true;
  try {
    const results = await state.searchChats(query, undefined, state.dynamicLimit);
    if (seq !== searchSeq) return; // 已有更新的请求，丢弃本次结果
    applySearchResults(query, results);
    hasMoreSearch.value = results.length >= state.dynamicLimit;
  } catch (e) {
    // 请求失败时保持上一次的结果，避免输入过程中列表被清空
    if (seq === searchSeq) console.error('搜索对话失败', e);
  } finally {
    if (seq === searchSeq) isSearching.value = false;
  }
};

// 滚动到底继续加载搜索结果（与普通列表一致，按 id 游标分段返回）
const fetchMoreSearch = async () => {
  if (!isSearchMode.value || isSearching.value || isLoadingMoreSearch.value || !hasMoreSearch.value) return;
  const query = appliedQuery.value;
  // 正在输入新查询（与已应用的结果不一致）时不翻页
  if (!query || searchQuery.value.trim() !== query || searchResults.value.length === 0) return;
  const seq = searchSeq;
  isLoadingMoreSearch.value = true;
  try {
    const lastId = searchResults.value[searchResults.value.length - 1][0];
    const results = await state.searchChats(query, lastId, state.dynamicLimit);
    if (seq !== searchSeq) return; // 查询已变化，丢弃本次结果
    if (results.length === 0) {
      hasMoreSearch.value = false;
    } else {
      searchResults.value.push(...results);
      hasMoreSearch.value = results.length >= state.dynamicLimit;
    }
  } catch (e) {
    if (seq === searchSeq) console.error('加载更多搜索结果失败', e);
  } finally {
    if (seq === searchSeq) isLoadingMoreSearch.value = false;
  }
};

const scheduleSearch = () => {
  cancelSearchDebounce();
  searchDebounce = setTimeout(runSearch, SEARCH_DEBOUNCE);
};

const handleSearchInput = (e: Event) => {
  searchQuery.value = (e.target as HTMLInputElement).value;
  // 组合中只同步文本，等 compositionend 再防抖搜索（部分浏览器 isComposing 不可靠，用标志位兜底）
  if (isComposing || (e as InputEvent).isComposing) return;
  scheduleSearch();
};

const handleSearchCompositionStart = () => {
  isComposing = true;
};

const handleSearchCompositionEnd = (e: CompositionEvent) => {
  isComposing = false;
  searchQuery.value = (e.target as HTMLInputElement).value;
  scheduleSearch();
};

// --- 搜索抽屉滑动手势（移动端） ---
// 在顶部行横向滑动开合搜索抽屉：关闭态向右滑打开（抽屉从左滑出，方向呼应），打开态向左滑关闭
const SWIPE_THRESHOLD = 48;
let swipeTouchId: number | null = null;
let swipeStartX = 0;
let swipeStartY = 0;
let swipeDir: 'none' | 'h' = 'none';

const resetSwipeGesture = () => {
  swipeTouchId = null;
  swipeDir = 'none';
};

const handleRowTouchStart = (e: TouchEvent) => {
  if (!state.isMobile || e.touches.length > 1) return;
  const t = e.touches[0];
  swipeTouchId = t.identifier;
  swipeStartX = t.clientX;
  swipeStartY = t.clientY;
  swipeDir = 'none';
};

const handleRowTouchMove = (e: TouchEvent) => {
  if (swipeTouchId === null) return;
  const t = Array.from(e.touches).find(item => item.identifier === swipeTouchId);
  if (!t) return;
  const dx = t.clientX - swipeStartX;
  const dy = t.clientY - swipeStartY;
  if (swipeDir === 'none') {
    if (Math.abs(dx) < 6 && Math.abs(dy) < 6) return;
    // 水平位移占优才认定为横向滑动，否则视为纵向操作放弃
    if (Math.abs(dx) <= Math.abs(dy)) {
      resetSwipeGesture();
      return;
    }
    swipeDir = 'h';
  }
  e.preventDefault();
};

const handleRowTouchEnd = (e: TouchEvent) => {
  if (swipeTouchId === null) return;
  const t = Array.from(e.changedTouches).find(item => item.identifier === swipeTouchId);
  if (!t) return; // 抬起的是另一根手指，跟踪中的滑动继续
  const wasHorizontal = swipeDir === 'h';
  resetSwipeGesture();
  if (!wasHorizontal) return;
  // 阻止合成的 click，避免滑动误触「新对话」/模型选择器/竖条
  e.preventDefault();
  const dx = t.clientX - swipeStartX;
  if (dx >= SWIPE_THRESHOLD && !isSearchOpen.value) openSearch();
  else if (dx <= -SWIPE_THRESHOLD && isSearchOpen.value) closeSearch();
};

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
  if (!el || el.scrollTop > 0 || isRefreshing.value || isSearchMode.value) return;
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

  if (pullDistance.value >= PULL_THRESHOLD && state.chats.length > 0 && !isSearchMode.value) {
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
  if (!el || e.deltaY >= 0 || el.scrollTop > 0 || isRefreshing.value || isSearchMode.value) return;

  isPulling.value = true;
  wheelAccum += Math.abs(e.deltaY) * 0.3;
  pullDistance.value = Math.min(PULL_MAX, wheelAccum);

  if (wheelDecay) clearTimeout(wheelDecay);
  wheelDecay = setTimeout(async () => {
    if (pullDistance.value >= PULL_THRESHOLD && state.chats.length > 0 && !isSearchMode.value) {
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
  if (!el) {
    // 条目已被替换或删除，清掉悬停态，避免残留位移撑高滚动区域
    hoveredId.value = null;
    return;
  }
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

// 列表内容整体切换（普通列表 ⇄ 搜索结果）时置顶，并清掉悬停框
// （悬停框是绝对定位元素，残留的 translateY 会撑高滚动区域，导致大片空白）
const resetListScroll = () => {
  hoveredId.value = null;
  indicatorTop.value = 0;
  indicatorHeight.value = 0;
  nextTick(() => {
    if (chatListRef.value) chatListRef.value.scrollTop = 0;
    checkScrollBottom();
  });
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
    if (!el || el.scrollTop + el.clientHeight < el.scrollHeight - 50) return;
    if (isSearchMode.value) fetchMoreSearch();
    else state.fetchMoreHistory();
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
    const id = chatToDelete.value;
    state.deleteChat(id);
    searchResults.value = searchResults.value.filter(chat => chat[0] !== id);
    chatToDelete.value = null;
    showDeleteConfirm.value = false;
  }
};
</script>

<template>
  <aside 
    class="bg-bg-panel h-full transition-all duration-300 ease-in-out shrink-0 z-100 shadow-[1px_0_5px_rgba(0,0,0,0.05)] overflow-hidden sidebar-shell"
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
      <!-- 搜索入口竖条移到行首（与「AI Chat」标题左对齐），搜索抽屉改为从左侧滑入 -->
      <div
        class="mx-4 mb-4 flex items-center gap-2"
        @touchstart="handleRowTouchStart"
        @touchmove="handleRowTouchMove"
        @touchend="handleRowTouchEnd"
        @touchcancel="resetSwipeGesture"
      >
        <!-- 搜索入口竖条：与对话列表滚动条等宽（5px）、同色，悬停显示抽屉方向箭头 -->
        <button
          @click="toggleSearch"
          class="group/sb relative w-[5px] h-8 shrink-0"
          :title="isSearchOpen ? '关闭搜索' : '搜索对话'"
        >
          <span
            class="absolute inset-0 transition-colors duration-200"
            :class="isSearchOpen ? 'bg-primary-main' : 'bg-border-input group-hover/sb:bg-text-placeholder'"
          ></span>
          <span class="pointer-events-none absolute left-[3px] top-1/2 -translate-y-1/2 text-[11px] leading-none text-text-placeholder opacity-0 transition-opacity duration-200 group-hover/sb:opacity-100">
            <ChevronRight class="transition-transform duration-200" :class="isSearchOpen ? 'rotate-180' : ''" />
          </span>
          <!-- 扩大点击热区（视觉仍是 5px 竖条） -->
          <span class="absolute -inset-y-1 -left-2 -right-2"></span>
        </button>
        <!-- 抽屉容器：新对话 + 模型选择器 ⇄ 搜索框 -->
        <div class="relative flex-1 min-w-0 h-8">
          <div class="absolute inset-0 flex items-center gap-2" :inert="isSearchOpen">
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
          <!-- 搜索抽屉：从左侧滑入，覆盖整行 -->
          <Transition name="drawer">
            <div v-if="isSearchOpen" class="absolute inset-0 z-10 bg-bg-panel">
              <Search class="absolute left-3 top-1/2 -translate-y-1/2 text-text-placeholder pointer-events-none" />
              <input
                ref="searchInputRef"
                :value="searchQuery"
                type="text"
                placeholder="搜索对话标题"
                class="w-full h-8 bg-bg-main border border-border-input pl-8 pr-8 text-sm text-text-main outline-none transition-colors focus:border-primary-main placeholder:text-text-placeholder"
                @input="handleSearchInput"
                @compositionstart="handleSearchCompositionStart"
                @compositionend="handleSearchCompositionEnd"
                @keydown.esc="closeSearch"
              />
              <!-- 搜索中：右侧显示转圈（输入过程中列表保持上一次的结果，用这里的转圈表示正在搜） -->
              <Loader2 v-if="isSearching" class="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-text-placeholder animate-spin pointer-events-none" />
              <button
                v-else-if="searchQuery"
                @click="handleClearSearch"
                class="absolute right-2 top-1/2 -translate-y-1/2 flex items-center justify-center text-text-placeholder hover:text-text-main transition-colors"
                title="清空"
              >
                <X class="text-xs" />
              </button>
            </div>
          </Transition>
        </div>
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
            v-for="chat in displayChats" 
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
          <!-- 搜索状态提示 -->
          <div v-if="isSearchMode && (isSearching || isLoadingMoreSearch)" class="text-center py-3 text-xs text-text-placeholder">
            <Loader2 class="animate-spin mr-1" /> {{ isSearching ? '搜索中...' : '加载中...' }}
          </div>
          <div v-else-if="isSearchMode && searchResults.length === 0" class="text-center py-3 text-xs text-text-placeholder truncate px-2">
            未找到匹配「{{ appliedQuery }}」的对话
          </div>
          <div v-else-if="isSearchMode && !hasMoreSearch" class="text-center py-3 text-xs text-text-placeholder">
            没有更多了
          </div>
          <!-- Loading indicator -->
          <div v-else-if="!isSearchMode && state.isLoadingHistory" class="text-center py-3 text-xs text-text-placeholder">
            <Loader2 class="animate-spin mr-1" /> 加载中...
          </div>
          <div v-else-if="!isSearchMode && !state.hasMoreHistory && state.chats.length > 0" class="text-center py-3 text-xs text-text-placeholder">
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
/* 侧栏内容（w-64）比带 1px 右边框的内容盒宽 1px，聚焦右边缘的搜索竖条时浏览器会把它滚进视野，
   整列被顶出 1px 且不回弹。overflow: clip 同样裁切但不产生滚动容器（不支持时保留 overflow-hidden） */
.sidebar-shell {
  overflow: clip;
}

/* 搜索抽屉：从搜索竖条一侧向右展开覆盖「新对话 + 模型选择器」，收起时向竖条方向收回
   （clip-path 裁切展开而非位移：内容不随动画变形，也不会再越过侧栏左边缘） */
.drawer-enter-active,
.drawer-leave-active {
  transition: clip-path 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.drawer-enter-from,
.drawer-leave-to {
  clip-path: inset(0 100% 0 0);
}

.drawer-enter-to,
.drawer-leave-from {
  clip-path: inset(0 0 0 0);
}

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
