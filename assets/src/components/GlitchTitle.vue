<script setup lang="ts">
/**
 * GlitchTitle —— glitch 设计语言的「信号源」字标（设计语言第二层）。
 *
 * 实现：基础文字永远静止、完全不透明（可读性优先）；`::before` / `::after`
 * 用 `content: attr(data-text)` 复制青/品红副本，burst 时以 `clip-path: inset()`
 * 横向切片 + 少量位移撕裂，关键帧不均匀排布、播完即散。
 * - 播放由 `auto` 控制；侧边栏/Profile 保持静态，登录/邀请页周期性 burst
 * - `auto` 开周期性自动 burst（登录/邀请页，「活着的系统」感）：
 *   间隔在 [minInterval, maxInterval] 内随机取值，避免节拍器式机械重复
 * - 文字经 prop 单一来源传入、data-text 由模板同步生成，
 *   天然规避「data-text 与正文漂移」的经典坑
 * - prefers-reduced-motion 下保持静态（干净的基础文字）
 * - 切片/位移只作用在伪元素上，元素本体保持静止（命中区稳定）
 */
import { onMounted, onBeforeUnmount, ref } from 'vue';

const props = withDefaults(defineProps<{
  text: string;
  /** 周期性自动 burst（登录/邀请页用）；应用内不传 */
  auto?: boolean;
  /** 自动 burst 的最小间隔（毫秒） */
  minInterval?: number;
  /** 自动 burst 的最大间隔（毫秒） */
  maxInterval?: number;
}>(), {
  auto: false,
  minInterval: 6000,
  maxInterval: 8000,
});

const el = ref<HTMLElement | null>(null);
let timer: number | undefined;

/** 播一次撕裂：先移除类 + 强制回流，保证连续触发也能重播 */
const burst = () => {
  const node = el.value;
  if (!node) return;
  node.classList.remove('glitch-title-burst');
  void node.offsetWidth;
  node.classList.add('glitch-title-burst');
};

const schedule = () => {
  if (!props.auto) return;
  const span = Math.max(0, props.maxInterval - props.minInterval);
  timer = window.setTimeout(() => {
    burst();
    schedule();
  }, props.minInterval + Math.random() * span);
};

onMounted(schedule);
onBeforeUnmount(() => clearTimeout(timer));
</script>

<template>
  <span ref="el" class="glitch-title" :data-text="text">{{ text }}</span>
</template>

<style scoped>
.glitch-title {
  position: relative;
  display: inline-block;
}

/* 静止时副本完全隐藏（不依赖首帧），撕裂只发生在彩色副本上 */
.glitch-title::before,
.glitch-title::after {
  content: attr(data-text);
  position: absolute;
  left: 0;
  top: 0;
  width: 100%;
  pointer-events: none;
  opacity: 0;
}

.glitch-title::before { color: var(--glitch-cyan); }
.glitch-title::after { color: var(--glitch-magenta); }

/* 两层用不同关键帧 + 40ms 错峰，撕裂看起来随机而非对称 */
.glitch-title-burst::before {
  animation: glitch-title-slice-a 380ms steps(1, end) forwards;
}

.glitch-title-burst::after {
  animation: glitch-title-slice-b 380ms steps(1, end) 40ms forwards;
}

@keyframes glitch-title-slice-a {
  0% { opacity: 1; clip-path: inset(10% 0 66% 0); transform: translate(3px, -1px); }
  8% { opacity: 1; clip-path: inset(52% 0 30% 0); transform: translate(-2px, 1px); }
  17% { opacity: 1; clip-path: inset(6% 0 80% 0); transform: translate(2px, 0); }
  29% { opacity: 1; clip-path: inset(64% 0 14% 0); transform: translate(-1.5px, 0); }
  42% { opacity: 0; clip-path: inset(0 0 100% 0); transform: none; }
  100% { opacity: 0; clip-path: inset(0 0 100% 0); transform: none; }
}

@keyframes glitch-title-slice-b {
  0% { opacity: 1; clip-path: inset(70% 0 8% 0); transform: translate(-3px, 1px); }
  10% { opacity: 1; clip-path: inset(22% 0 58% 0); transform: translate(2.5px, -1px); }
  21% { opacity: 1; clip-path: inset(46% 0 38% 0); transform: translate(-2px, 0); }
  33% { opacity: 1; clip-path: inset(12% 0 74% 0); transform: translate(1px, 0); }
  46% { opacity: 0; clip-path: inset(0 0 100% 0); transform: none; }
  100% { opacity: 0; clip-path: inset(0 0 100% 0); transform: none; }
}

@media (prefers-reduced-motion: reduce) {
  .glitch-title-burst::before,
  .glitch-title-burst::after {
    animation: none;
  }
}
</style>
