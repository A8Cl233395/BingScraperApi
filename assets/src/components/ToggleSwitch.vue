<script setup lang="ts">
const props = withDefaults(defineProps<{
  modelValue: boolean;
  disabled?: boolean;
  ariaLabel?: string;
}>(), {
  disabled: false,
  ariaLabel: '切换',
});

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
}>();

const toggle = () => {
  if (props.disabled) return;
  emit('update:modelValue', !props.modelValue);
};
</script>

<template>
  <button
    type="button"
    class="toggle-switch"
    :class="{ active: modelValue }"
    role="switch"
    :aria-checked="modelValue"
    :aria-label="ariaLabel"
    :disabled="disabled"
    @click="toggle"
  >
    <span class="toggle-knob"></span>
  </button>
</template>

<style scoped>
.toggle-switch {
  position: relative;
  width: 44px;
  height: 24px;
  flex-shrink: 0;
  padding: 0;
  box-sizing: border-box;
  appearance: none;
  background: var(--bg-hover);
  border: 2px solid var(--border-input);
  border-radius: 0;
  cursor: pointer;
  transition: background-color 0.18s cubic-bezier(0.2, 0, 0, 1),
    border-color 0.18s cubic-bezier(0.2, 0, 0, 1);
  -webkit-tap-highlight-color: transparent;
}

/* 左侧状态指示灯 */
.toggle-switch::before {
  content: '';
  position: absolute;
  left: -6px;
  top: 4px;
  bottom: 4px;
  width: 2px;
  background: var(--border-input);
  opacity: 0.6;
  transition: background-color 0.18s ease, opacity 0.18s ease;
}

/* 移动端隐形扩大点击域 */
.toggle-switch::after {
  content: '';
  position: absolute;
  inset: -8px;
}

.toggle-knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  background: var(--text-muted);
  border-radius: 0;
  transition: transform 0.18s cubic-bezier(0.2, 0, 0, 1),
    background-color 0.18s ease;
}

.toggle-switch.active {
  background: var(--primary);
  border-color: var(--primary);
}

.toggle-switch.active::before {
  background: var(--primary);
  opacity: 1;
}

.toggle-switch.active .toggle-knob {
  transform: translateX(20px);
  background: #fff;
}

@media (hover: hover) {
  .toggle-switch:not(:disabled):hover {
    border-color: var(--primary);
  }

  .toggle-switch:not(:disabled):hover::before {
    opacity: 1;
  }
}

.toggle-switch:not(:disabled):active .toggle-knob {
  transform: scaleX(0.86);
}

.toggle-switch.active:not(:disabled):active .toggle-knob {
  transform: translateX(20px) scaleX(0.86);
}

.toggle-switch:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.toggle-switch:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

@media (prefers-reduced-motion: reduce) {
  .toggle-switch,
  .toggle-switch::before,
  .toggle-knob {
    transition: none;
  }
}
</style>
