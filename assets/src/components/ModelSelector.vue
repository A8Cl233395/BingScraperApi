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
      <FontAwesomeIcon :icon="['fas', 'chevron-down']" class="text-[10px] text-text-placeholder transition-transform duration-200" :class="isOpen ? 'rotate-180' : ''" />
    </button>

    <transition
      @enter="(el: any) => { el.style.transition = 'none'; el.style.height = '0px'; el.style.opacity = '0'; el.offsetHeight; el.style.transition = 'height 0.25s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.25s cubic-bezier(0.4, 0, 0.2, 1)'; el.style.height = el.scrollHeight + 'px'; el.style.opacity = '1'; }"
      @after-enter="(el: any) => { el.style.transition = ''; el.style.height = 'auto'; }"
      @leave="(el: any) => { el.style.transition = 'none'; el.style.height = el.scrollHeight + 'px'; el.style.opacity = '1'; el.offsetHeight; el.style.transition = 'height 0.25s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.25s cubic-bezier(0.4, 0, 0.2, 1)'; el.style.height = '0px'; el.style.opacity = '0'; }"
      @after-leave="(el: any) => { el.style.transition = ''; }"
    >
      <!-- Dropdown -->
      <div
        v-if="isOpen"
        class="absolute left-0 mt-2 w-64 bg-bg-main border border-border-main rounded-lg shadow-xl z-50 py-1 overflow-hidden origin-top-left"
      >
        <template v-for="(info, name) in state.models" :key="name">
          <div
            class="px-4 py-2 hover:bg-bg-hover cursor-pointer flex flex-col transition-colors border-b last:border-b-0 border-border-main"
            :class="state.currentModel === name ? 'bg-bg-active' : ''"
            @click="toggleModelDetails(name as string)"
          >
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2 min-w-0">
                <span class="text-sm truncate" :class="state.currentModel === name ? 'text-primary-main font-semibold' : 'text-text-main'">
                  {{ name }}
                </span>
                <span v-if="state.currentModel === name" class="shrink-0 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-primary-main/15 text-primary-main">当前</span>
                <span v-else-if="state.defaultSettings.model === name" class="shrink-0 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-success-bg text-success-main">默认</span>
              </div>
              <FontAwesomeIcon :icon="['fas', 'chevron-right']" class="text-[10px] text-text-placeholder transition-transform duration-200 shrink-0" :class="expandedModel === name ? 'rotate-90' : ''" />
            </div>
            
            <!-- Details inline -->
            <transition
              @enter="(el: any) => { el.style.transition = 'none'; el.style.height = '0px'; el.style.opacity = '0'; el.offsetHeight; el.style.transition = 'height 0.25s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.25s cubic-bezier(0.4, 0, 0.2, 1)'; el.style.height = el.scrollHeight + 'px'; el.style.opacity = '1'; }"
              @after-enter="(el: any) => { el.style.transition = ''; el.style.height = 'auto'; }"
              @leave="(el: any) => { el.style.transition = 'none'; el.style.height = el.scrollHeight + 'px'; el.style.opacity = '1'; el.offsetHeight; el.style.transition = 'height 0.25s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.25s cubic-bezier(0.4, 0, 0.2, 1)'; el.style.height = '0px'; el.style.opacity = '0'; }"
              @after-leave="(el: any) => { el.style.transition = ''; }"
            >
              <div
                v-if="expandedModel === name"
                class="mt-2 pt-2 border-t border-border-main overflow-hidden"
                @click.stop
              >
                <p class="text-xs text-text-muted mb-2">{{ info.desc }}</p>
                <div class="grid grid-cols-2 gap-1 text-[11px]">
                  <button @click.stop="setSessionModel(name as string, false)" class="group/btn relative px-2 py-1.5 bg-btn-secondary-bg border border-border-input rounded hover:bg-bg-hover text-btn-secondary-text transition-colors flex items-center justify-center gap-1.5" title="设为当前会话模型">
                    <FontAwesomeIcon :icon="['fas', 'bolt']" class="text-[10px] text-text-muted group-hover/btn:text-primary-main transition-colors" />
                    <span>会话</span>
                  </button>
                  <button @click.stop="setDefaultModel(name as string, false)" class="group/btn relative px-2 py-1.5 bg-btn-secondary-bg border border-border-input rounded hover:bg-bg-hover text-btn-secondary-text transition-colors flex items-center justify-center gap-1.5" title="设为默认模型">
                    <FontAwesomeIcon :icon="['fas', 'thumbtack']" class="text-[10px] text-text-muted group-hover/btn:text-primary-main transition-colors" />
                    <span>默认</span>
                  </button>
                  <button v-if="info.vision" @click.stop="setSessionModel(name as string, true)" class="group/btn relative px-2 py-1.5 bg-primary-main/10 text-primary-main border border-primary-main/20 rounded hover:bg-primary-main/20 transition-colors flex items-center justify-center gap-1.5" title="设为当前视觉模型">
                    <FontAwesomeIcon :icon="['fas', 'eye']" class="text-[10px]" />
                    <span>视觉</span>
                  </button>
                  <button v-if="info.vision" @click.stop="setDefaultModel(name as string, true)" class="group/btn relative px-2 py-1.5 bg-primary-main/10 text-primary-main border border-primary-main/20 rounded hover:bg-primary-main/20 transition-colors flex items-center justify-center gap-1.5" title="设为默认视觉模型">
                    <FontAwesomeIcon :icon="['fas', 'thumbtack']" class="text-[10px]" />
                    <span>默认视觉</span>
                  </button>
                </div>
              </div>
            </transition>
          </div>
        </template>
      </div>
    </transition>
  </div>
</template>
