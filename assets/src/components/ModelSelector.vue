<script setup lang="ts">
import { state } from '../store';
import { ref, onMounted, onUnmounted } from 'vue';
import api from '../utils/api';

const isOpen = ref(false);
const expandedModel = ref<string | null>(null);
const containerRef = ref<HTMLElement | null>(null);

const toggleDropdown = async () => {
  if (!isOpen.value && Object.keys(state.models).length === 0) {
    await state.fetchModels();
  }
  isOpen.value = !isOpen.value;
};

const toggleModelDetails = (name: string) => {
  expandedModel.value = expandedModel.value === name ? null : name;
};

const setSessionModel = (model: string, isVision: boolean) => {
  if (isVision) { state.currentVModel = model; }
  else { state.currentModel = model; }
  isOpen.value = false;
};

const setDefaultModel = async (model: string, isVision: boolean) => {
  try {
    const payload: any = {};
    if (isVision) {
      payload.vmodel = model;
      state.defaultSettings.vmodel = model;
      state.currentVModel = model;
    } else {
      payload.model = model;
      state.defaultSettings.model = model;
      state.currentModel = model;
    }
    await api.post('/api/default', payload);
  } catch (e) {
    console.error('Failed to set default model', e);
  }
};

// Close on outside click
const handleOutsideClick = (e: MouseEvent) => {
  if (isOpen.value && containerRef.value && !containerRef.value.contains(e.target as Node)) {
    isOpen.value = false;
  }
};

onMounted(() => { document.addEventListener('click', handleOutsideClick); });
onUnmounted(() => { document.removeEventListener('click', handleOutsideClick); });
</script>

<template>
  <div ref="containerRef" class="relative ml-2" @dblclick.stop>
    <button
      @click="toggleDropdown()"
      class="flex items-center gap-2 border border-border-input rounded-md px-3 py-1.5 hover:bg-bg-hover bg-bg-main transition-colors"
    >
      <span class="text-sm text-text-main">
        {{ state.currentModel || '选择模型' }}
        <span v-if="state.currentVModel" class="text-text-placeholder">/ {{ state.currentVModel }}</span>
      </span>
      <i class="fas fa-chevron-down text-[10px] text-text-placeholder transition-transform duration-200" :class="isOpen ? 'rotate-180' : ''"></i>
    </button>

    <transition
      @enter="(el: any) => { el.style.height = '0px'; el.offsetHeight; el.style.height = el.scrollHeight + 'px'; }"
      @after-enter="(el: any) => { el.style.height = 'auto'; }"
      @leave="(el: any) => { el.style.height = el.scrollHeight + 'px'; el.offsetHeight; el.style.height = '0px'; }"
    >
      <!-- Dropdown -->
      <div
        v-if="isOpen"
        class="absolute left-0 mt-2 w-64 bg-bg-main border border-border-main rounded-lg shadow-xl z-50 py-1 overflow-hidden origin-top-left transition-all duration-300 ease-in-out"
      >
        <template v-for="(info, name) in state.models" :key="name">
          <div
            class="px-4 py-2 hover:bg-bg-hover cursor-pointer flex flex-col transition-colors border-b last:border-b-0 border-border-main"
            :class="state.currentModel === name ? 'bg-bg-active' : ''"
            @click="toggleModelDetails(name as string)"
          >
            <div class="flex items-center justify-between">
              <span class="text-sm" :class="state.currentModel === name ? 'text-primary-main font-semibold' : 'text-text-main'">
                {{ name }}
              </span>
              <i class="fas fa-chevron-right text-[10px] text-text-placeholder transition-transform duration-200" :class="expandedModel === name ? 'rotate-90' : ''"></i>
            </div>
            
            <!-- Details inline -->
            <transition
              @enter="(el: any) => { el.style.height = '0px'; el.offsetHeight; el.style.height = el.scrollHeight + 'px'; }"
              @after-enter="(el: any) => { el.style.height = 'auto'; }"
              @leave="(el: any) => { el.style.height = el.scrollHeight + 'px'; el.offsetHeight; el.style.height = '0px'; }"
            >
              <div
                v-if="expandedModel === name"
                class="mt-2 pt-2 border-t border-border-main overflow-hidden transition-all duration-300 ease-in-out"
                @click.stop
              >
                <p class="text-xs text-text-muted mb-2">{{ info.desc }}</p>
                <div class="grid grid-cols-2 gap-1 text-[11px]">
                  <button @click.stop="setSessionModel(name as string, false)" class="px-2 py-1.5 bg-btn-secondary-bg border border-border-input rounded hover:bg-bg-hover text-btn-secondary-text transition-colors">设置</button>
                  <button @click.stop="setDefaultModel(name as string, false)" class="px-2 py-1.5 bg-btn-secondary-bg border border-border-input rounded hover:bg-bg-hover text-btn-secondary-text transition-colors">设置默认</button>
                  <button v-if="info.vision" @click.stop="setSessionModel(name as string, true)" class="px-2 py-1.5 bg-primary-main/10 text-primary-main border border-primary-main/20 rounded hover:bg-primary-main/20 transition-colors">设置视觉</button>
                  <button v-if="info.vision" @click.stop="setDefaultModel(name as string, true)" class="px-2 py-1.5 bg-primary-main/10 text-primary-main border border-primary-main/20 rounded hover:bg-primary-main/20 transition-colors">默认视觉</button>
                </div>
              </div>
            </transition>
          </div>
        </template>
      </div>
    </transition>
  </div>
</template>
