<script setup lang="ts">
import { ref } from 'vue';
import { usePet } from '../composables/usePet';
import { PET_STATES } from '../utils/pet-db';
import type { PetState } from '../utils/pet-db';
import { state } from '../store';
import ConfirmModal from './ConfirmModal.vue';
import { useToast } from '../composables/useToast';

const { showToast } = useToast();
const {
  petImages,
  isLoading,
  importSprite,
  removeImage,
  clearAll,
  setEnabled,
} = usePet();

const showClearConfirm = ref(false);
const isImporting = ref(false);
const spriteInputRef = ref<HTMLInputElement | null>(null);

const stateLabels: Record<PetState, string> = {
  idle: '空闲',
  thinking: '思考中',
  answering: '回答中',
  tool_calling: '工具调用',
};

const handleImport = async () => {
  const input = spriteInputRef.value;
  if (!input?.files?.length) return;

  const file = input.files[0];
  isImporting.value = true;
  try {
    await importSprite(file);
    showToast('Codex 精灵图已导入');
  } catch (e) {
    showToast('导入失败', 'error');
  } finally {
    isImporting.value = false;
    input.value = '';
  }
};

const isDragging = ref(false);
let dragCounter = 0;

const handleDragEnter = (e: DragEvent) => {
  e.preventDefault();
  dragCounter++;
  isDragging.value = true;
};

const handleDragLeave = (e: DragEvent) => {
  e.preventDefault();
  dragCounter--;
  if (dragCounter === 0) {
    isDragging.value = false;
  }
};

const handleDrop = async (e: DragEvent) => {
  e.preventDefault();
  dragCounter = 0;
  isDragging.value = false;

  const file = e.dataTransfer?.files[0];
  if (!file) return;

  isImporting.value = true;
  try {
    await importSprite(file);
    showToast('Codex 精灵图已导入');
  } catch (e) {
    showToast('导入失败', 'error');
  } finally {
    isImporting.value = false;
  }
};

const handleRemove = async (s: PetState) => {
  try {
    await removeImage(s);
    showToast(`${stateLabels[s]} 状态图片已清除`);
  } catch (e) {
    showToast('删除失败', 'error');
  }
};

const handleClearAll = async () => {
  showClearConfirm.value = false;
  try {
    await clearAll();
    showToast('所有宠物图片已清空');
  } catch (e) {
    showToast('清空失败', 'error');
  }
};

const handleToggle = async (e: Event) => {
  const checked = (e.target as HTMLInputElement).checked;
  await setEnabled(checked);
};
</script>

<template>
  <div class="pet-section">
    <div class="pet-header">
      <FontAwesomeIcon :icon="['fas', 'paw']" />
      <h2>宠物设置</h2>
    </div>
    <p class="pet-desc">导入 Codex 精灵图，宠物会根据 AI 当前状态自动播放对应动画。</p>

    <div v-if="isLoading" class="loading-state">
      <FontAwesomeIcon :icon="['fas', 'spinner']" spin />
      <span>加载中...</span>
    </div>

    <template v-else>
      <div class="pet-toggle-row">
        <span class="pet-toggle-label">宠物显示</span>
        <label class="toggle-switch">
          <input type="checkbox" :checked="state.petEnabled" @change="handleToggle">
          <span class="toggle-slider"></span>
        </label>
      </div>

      <div class="pet-preview-grid">
        <div v-for="s in PET_STATES" :key="s" class="pet-preview-card">
          <div class="pet-preview-label">{{ stateLabels[s] }}</div>
          <div class="pet-preview-box">
            <img v-if="petImages[s]" :src="petImages[s]!" :alt="stateLabels[s]" class="pet-preview-img">
            <div v-else class="pet-preview-placeholder">
              <FontAwesomeIcon :icon="['fas', 'paw']" />
            </div>
          </div>
          <button v-if="petImages[s]" class="pet-remove-btn" @click="handleRemove(s)">
            <FontAwesomeIcon :icon="['fas', 'xmark']" />
          </button>
        </div>
      </div>

      <div
        class="pet-import-section"
        :class="{ 'pet-import-dragging': isDragging }"
        @dragenter="handleDragEnter"
        @dragleave="handleDragLeave"
        @dragover.prevent
        @drop="handleDrop"
      >
        <input
          ref="spriteInputRef"
          type="file"
          accept="image/png,image/gif,image/webp,.apng"
          class="hidden"
          @change="handleImport"
        >
        <button class="pet-import-btn" @click="spriteInputRef?.click()" :disabled="isImporting">
          <FontAwesomeIcon v-if="isImporting" :icon="['fas', 'spinner']" spin />
          <FontAwesomeIcon v-else :icon="['fas', 'file-import']" />
          <span>导入 Codex 精灵图</span>
        </button>
        <span class="pet-import-hint">拖拽图片到此处，或点击按钮选择文件</span>
      </div>

      <div class="pet-clear-section">
        <button class="pet-clear-btn" @click="showClearConfirm = true">
          <FontAwesomeIcon :icon="['fas', 'trash-can']" />
          清空所有图片
        </button>
      </div>
    </template>

    <ConfirmModal
      :show="showClearConfirm"
      title="清空所有宠物图片"
      message="此操作将删除所有已上传的宠物状态图片，且无法恢复。确定要继续吗？"
      confirmText="清空"
      cancelText="取消"
      :isDanger="true"
      @confirm="handleClearAll"
      @cancel="showClearConfirm = false"
    />
  </div>
</template>

<style scoped>
.pet-section {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.pet-header {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-main);
}

.pet-header svg {
  font-size: 1rem;
  color: var(--primary);
}

.pet-header h2 {
  font-size: 0.95rem;
  font-weight: 600;
  margin: 0;
}

.pet-desc {
  font-size: 0.85rem;
  color: var(--text-muted);
  margin: 0;
  line-height: 1.5;
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px;
  color: var(--text-muted);
}

.pet-toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: 8px;
}

.pet-toggle-label {
  font-size: 0.9rem;
  color: var(--text-main);
  font-weight: 500;
}

.toggle-switch {
  position: relative;
  width: 44px;
  height: 24px;
  cursor: pointer;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  inset: 0;
  background-color: var(--bg-hover);
  border: 1px solid var(--border-input);
  border-radius: 12px;
  transition: all 0.2s ease;
}

.toggle-slider::before {
  content: '';
  position: absolute;
  width: 18px;
  height: 18px;
  left: 2px;
  bottom: 2px;
  background-color: var(--text-muted);
  border-radius: 50%;
  transition: all 0.2s ease;
}

.toggle-switch input:checked + .toggle-slider {
  background-color: var(--primary);
  border-color: var(--primary);
}

.toggle-switch input:checked + .toggle-slider::before {
  transform: translateX(20px);
  background-color: white;
}

.pet-preview-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.pet-preview-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px;
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: 8px;
}

.pet-preview-label {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-main);
}

.pet-preview-box {
  width: 100%;
  aspect-ratio: 192 / 208;
  background: var(--bg-main);
  border: 1px dashed var(--border-input);
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.pet-preview-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.pet-preview-placeholder {
  color: var(--text-placeholder);
  font-size: 1.5rem;
  opacity: 0.4;
}

.pet-remove-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 1px solid var(--border-input);
  background: var(--bg-main);
  color: var(--text-muted);
  font-size: 0.7rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
}

.pet-remove-btn:hover {
  background: var(--danger-bg);
  border-color: var(--danger);
  color: var(--danger);
}

.pet-import-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 20px 16px;
  background: var(--bg-panel);
  border: 2px dashed var(--border-color);
  border-radius: 8px;
  transition: all 0.2s ease;
}

.pet-import-dragging {
  border-color: var(--primary);
  background: var(--primary-bg, rgba(99, 102, 241, 0.05));
}

.pet-import-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 24px;
  background: var(--primary);
  color: var(--primary-text);
  border: none;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.pet-import-btn:hover:not(:disabled) {
  background: var(--primary-hover);
}

.pet-import-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.pet-import-hint {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.pet-clear-section {
  display: flex;
  justify-content: flex-end;
  padding-top: 8px;
  border-top: 1px solid var(--border-color);
}

.pet-clear-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  background: transparent;
  border: 1px solid var(--danger);
  border-radius: 6px;
  color: var(--danger);
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.15s ease;
}

.pet-clear-btn:hover {
  background: var(--danger);
  color: white;
}

.hidden {
  display: none;
}

@media (max-width: 767px) {
  .pet-preview-grid {
    grid-template-columns: 1fr;
  }
}
</style>
