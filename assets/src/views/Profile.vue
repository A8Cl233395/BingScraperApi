<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue';
import api from '../utils/api';

const convCount = ref(0);
const memories = ref<string[]>([]);
const isLoading = ref(true);

const oldPwd = ref('');
const newPwd = ref('');
const newPwdConfirm = ref('');
const isChangingPwd = ref(false);
const pwdError = ref('');
const pwdSuccess = ref('');

const newMemory = ref('');
const isAddingMemory = ref(false);
const memError = ref('');
const memoryTextareaRef = ref<HTMLTextAreaElement | null>(null);

const adjustMemoryHeight = () => {
  if (memoryTextareaRef.value) {
    memoryTextareaRef.value.style.height = 'auto';
    memoryTextareaRef.value.style.height = memoryTextareaRef.value.scrollHeight + 'px';
  }
};

const handleMemoryKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Enter') {
    if (e.ctrlKey) {
      e.preventDefault();
      const textarea = memoryTextareaRef.value!;
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      newMemory.value = newMemory.value.substring(0, start) + '\n' + newMemory.value.substring(end);
      nextTick(() => {
        textarea.selectionStart = textarea.selectionEnd = start + 1;
        adjustMemoryHeight();
      });
    } else if (!e.shiftKey) {
      e.preventDefault();
      handleAddMemory();
    }
  }
};

const toastMessage = ref('');
const toastType = ref('success');
const showToastMsg = ref(false);

const showToast = (message: string, type = 'success') => {
  toastMessage.value = message;
  toastType.value = type;
  showToastMsg.value = true;
  setTimeout(() => {
    showToastMsg.value = false;
  }, 3000);
};

const loadProfile = async () => {
  try {
    isLoading.value = true;
    const { data } = await api.get('/api/profile');
    convCount.value = data.conv_count;
    memories.value = data.memory || [];
  } catch (error: any) {
    showToast(error.response?.data?.detail || '加载资料失败', 'error');
  } finally {
    isLoading.value = false;
  }
};

const handleChangePwd = async () => {
  pwdError.value = '';
  pwdSuccess.value = '';

  if (!oldPwd.value.trim()) {
    pwdError.value = '请输入旧密码';
    return;
  }
  if (newPwd.value.length < 6) {
    pwdError.value = '新密码长度不能少于6个字符';
    return;
  }
  if (newPwd.value === oldPwd.value) {
    pwdError.value = '新密码不能与旧密码相同';
    return;
  }
  if (newPwd.value !== newPwdConfirm.value) {
    pwdError.value = '两次输入的新密码不一致';
    return;
  }

  try {
    isChangingPwd.value = true;
    await api.post('/api/changepwd', {
      old_pwd: oldPwd.value,
      new_pwd: newPwd.value
    });
    pwdSuccess.value = '密码修改成功';
    oldPwd.value = '';
    newPwd.value = '';
    newPwdConfirm.value = '';
    showToast('密码修改成功');
  } catch (error: any) {
    const status = error.response?.status;
    if (status === 403) {
      pwdError.value = '旧密码错误';
    } else if (status === 409) {
      pwdError.value = '新密码不能与旧密码相同';
    } else {
      pwdError.value = error.response?.data?.detail || '修改密码失败';
    }
  } finally {
    isChangingPwd.value = false;
  }
};

const handleAddMemory = async () => {
  memError.value = '';
  const mem = newMemory.value.trim();

  if (!mem) {
    memError.value = '请输入记忆内容';
    return;
  }
  if (mem.length > 100) {
    memError.value = '记忆长度不能超过100个字符';
    return;
  }
  if (memories.value.includes(mem)) {
    memError.value = '该记忆已存在';
    return;
  }
  if (memories.value.length >= 50) {
    memError.value = '记忆数量已达上限（50条）';
    return;
  }

  try {
    isAddingMemory.value = true;
    await api.post('/api/addmem', mem, {
      headers: { 'Content-Type': 'text/plain' }
    });
    memories.value.push(mem);
    newMemory.value = '';
    nextTick(() => {
      if (memoryTextareaRef.value) {
        memoryTextareaRef.value.style.height = '';
      }
    });
    showToast('记忆添加成功');
  } catch (error: any) {
    memError.value = error.response?.data || error.response?.data?.detail || '添加记忆失败';
  } finally {
    isAddingMemory.value = false;
  }
};

const handleRemoveMemory = async (memory: string) => {
  try {
    await api.post('/api/removemem', memory, {
      headers: { 'Content-Type': 'text/plain' }
    });
    memories.value = memories.value.filter(m => m !== memory);
    showToast('记忆已删除');
  } catch (error: any) {
    showToast(error.response?.data || error.response?.data?.detail || '删除记忆失败', 'error');
  }
};

const goBack = () => {
  window.location.href = '/webchat';
};

onMounted(() => {
  loadProfile();
});
</script>

<template>
  <div class="profile-container">
    <div class="profile-header">
      <button class="back-btn" @click="goBack">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
        返回
      </button>
      <h1 class="page-title">个人资料</h1>
    </div>

    <div v-if="isLoading" class="loading-state">
      <div class="spinner"></div>
      <span>加载中...</span>
    </div>

    <template v-else>
      <div class="content-grid">
        <div class="left-column">
          <div class="card">
            <h2 class="card-title">概览</h2>
            <div class="stats">
              <div class="stat-item">
                <span class="stat-value">{{ convCount }}</span>
                <span class="stat-label">对话数量</span>
              </div>
              <div class="stat-item">
                <span class="stat-value">{{ memories.length }}</span>
                <span class="stat-label">记忆数量</span>
              </div>
            </div>
          </div>

          <div class="card">
            <h2 class="card-title">修改密码</h2>
            <form @submit.prevent="handleChangePwd">
              <div class="form-group">
                <label class="form-label" for="oldPwd">旧密码</label>
                <input
                  type="password"
                  id="oldPwd"
                  v-model="oldPwd"
                  class="form-input"
                  placeholder="请输入旧密码"
                  autocomplete="current-password"
                >
              </div>

              <div class="form-group">
                <label class="form-label" for="newPwd">新密码</label>
                <input
                  type="password"
                  id="newPwd"
                  v-model="newPwd"
                  class="form-input"
                  placeholder="至少6个字符"
                  autocomplete="new-password"
                >
              </div>

              <div class="form-group">
                <label class="form-label" for="newPwdConfirm">确认新密码</label>
                <input
                  type="password"
                  id="newPwdConfirm"
                  v-model="newPwdConfirm"
                  class="form-input"
                  placeholder="再次输入新密码"
                  autocomplete="new-password"
                >
              </div>

              <div v-if="pwdError" class="error-message">{{ pwdError }}</div>
              <div v-if="pwdSuccess" class="success-message">{{ pwdSuccess }}</div>

              <button
                type="submit"
                class="submit-btn"
                :class="{ loading: isChangingPwd }"
                :disabled="isChangingPwd"
              >
                修改密码
              </button>
            </form>
          </div>
        </div>

        <div class="right-column card">
          <h2 class="card-title">记忆管理</h2>
          <p class="card-desc">记忆会作为上下文提供给 AI，帮助其更好地理解你的需求。</p>

          <form @submit.prevent="handleAddMemory" class="memory-add-form">
            <div class="memory-input-row">
              <textarea
                ref="memoryTextareaRef"
                v-model="newMemory"
                class="form-input memory-textarea"
                placeholder="添加新记忆（最多100字符）"
                maxlength="100"
                rows="1"
                @input="adjustMemoryHeight"
                @keydown="handleMemoryKeydown"
              ></textarea>
              <button
                type="submit"
                class="add-btn"
                :class="{ loading: isAddingMemory }"
                :disabled="isAddingMemory || !newMemory.trim()"
              >
                添加
              </button>
            </div>
            <div v-if="memError" class="error-message">{{ memError }}</div>
          </form>

          <div v-if="memories.length === 0" class="empty-state">
            暂无记忆
          </div>

          <div v-else class="memory-list">
            <div v-for="(mem, index) in memories" :key="index" class="memory-item">
              <span class="memory-text">{{ mem }}</span>
              <button class="remove-btn" @click="handleRemoveMemory(mem)" title="删除">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M18 6L6 18M6 6l12 12"/>
                </svg>
              </button>
            </div>
          </div>

          <div v-if="memories.length > 0" class="memory-count">
            {{ memories.length }} / 50 条记忆
          </div>
        </div>
      </div>
    </template>

    <div class="toast" :class="[toastType, { show: showToastMsg }]">
      {{ toastMessage }}
    </div>
  </div>
</template>

<style scoped>
/* Profile.vue 特殊样式 */
.profile-container {
  background-color: var(--bg-main);
  color: var(--text-main);
  min-height: 100vh;
  padding: 24px;
  transition: background-color 0.3s ease, color 0.3s ease;
}

.profile-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
  max-width: 1200px;
  margin-left: auto;
  margin-right: auto;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: transparent;
  border: 1px solid var(--border-input);
  border-radius: 6px;
  color: var(--text-main);
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.15s ease;
}

.back-btn:hover {
  background-color: var(--bg-hover);
}

.page-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-main);
}

.content-grid {
  display: grid;
  grid-template-columns: 360px 1fr;
  gap: 16px;
  max-width: 1200px;
  margin: 0 auto;
  align-items: start;
}

.left-column {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.card {
  background-color: var(--bg-panel);
  border-radius: 8px;
  padding: 20px;
  border: 1px solid var(--border-color);
  transition: all 0.3s ease;
  max-width: none;
  width: 100%;
}

.card-title {
  font-size: 1rem;
  font-weight: 600;
  margin-bottom: 16px;
  color: var(--text-main);
}

.card-desc {
  font-size: 0.85rem;
  color: var(--text-muted);
  margin-bottom: 16px;
}

.stats {
  display: flex;
  gap: 24px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--primary);
}

.stat-label {
  font-size: 0.85rem;
  color: var(--text-muted);
}

.form-group {
  margin-bottom: 14px;
}

.form-label {
  display: block;
  font-size: 0.85rem;
  margin-bottom: 6px;
  color: var(--text-muted);
}

.form-input {
  width: 100%;
  padding: 10px 14px;
  background-color: var(--bg-main);
  border: 1px solid var(--border-input);
  border-radius: 6px;
  color: var(--text-main);
  font-size: 0.9rem;
  transition: all 0.15s ease;
  outline: none;
}

.form-input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 1px var(--primary);
}

.form-input::placeholder {
  color: var(--text-placeholder);
}

.error-message {
  margin-top: 8px;
  padding: 8px 12px;
  background-color: var(--danger-bg);
  border: 1px solid var(--danger);
  border-radius: 6px;
  color: var(--danger);
  font-size: 0.85rem;
}

.success-message {
  margin-top: 8px;
  padding: 8px 12px;
  background-color: var(--success-bg);
  border: 1px solid var(--success-border);
  border-radius: 6px;
  color: var(--success);
  font-size: 0.85rem;
}

.submit-btn {
  width: 100%;
  padding: 10px 20px;
  background-color: var(--primary);
  color: var(--primary-text);
  border: none;
  border-radius: 6px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  margin-top: 8px;
}

.submit-btn:hover:not(:disabled) {
  background-color: var(--primary-hover);
  box-shadow: 0 0 20px rgba(0, 120, 212, 0.2);
}

.submit-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.submit-btn.loading {
  position: relative;
  color: transparent;
}

.submit-btn.loading::after {
  content: "";
  position: absolute;
  width: 18px;
  height: 18px;
  top: 50%;
  left: 50%;
  margin-left: -9px;
  margin-top: -9px;
  border: 2px solid var(--primary-text);
  border-radius: 50%;
  border-top-color: transparent;
  animation: spinner 0.8s linear infinite;
}

.right-column {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.memory-add-form {
  margin-bottom: 16px;
}

.memory-input-row {
  display: flex;
  gap: 8px;
}

.memory-input-row .form-input {
  flex: 1;
}

.memory-textarea {
  resize: none;
  min-height: 40px;
  line-height: 1.4;
  overflow-y: auto;
}

.add-btn {
  padding: 10px 16px;
  background-color: var(--primary);
  color: var(--primary-text);
  border: none;
  border-radius: 6px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.add-btn:hover:not(:disabled) {
  background-color: var(--primary-hover);
}

.add-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.add-btn.loading {
  position: relative;
  color: transparent;
}

.add-btn.loading::after {
  content: "";
  position: absolute;
  width: 16px;
  height: 16px;
  top: 50%;
  left: 50%;
  margin-left: -8px;
  margin-top: -8px;
  border: 2px solid var(--primary-text);
  border-radius: 50%;
  border-top-color: transparent;
  animation: spinner 0.8s linear infinite;
}

.empty-state {
  text-align: center;
  padding: 48px 24px;
  color: var(--text-muted);
  font-size: 0.9rem;
}

.memory-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.memory-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 14px;
  background-color: var(--bg-main);
  border: 1px solid var(--border-input);
  border-radius: 6px;
  transition: all 0.15s ease;
}

.memory-item:hover {
  border-color: var(--primary);
}

.memory-text {
  flex: 1;
  font-size: 0.85rem;
  word-break: break-all;
  line-height: 1.4;
  white-space: pre-wrap;
}

.remove-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: transparent;
  border: none;
  border-radius: 4px;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s ease;
  flex-shrink: 0;
}

.remove-btn:hover {
  background-color: var(--danger-bg);
  color: var(--danger);
}

.memory-count {
  margin-top: 12px;
  text-align: right;
  font-size: 0.8rem;
  color: var(--text-muted);
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px;
  color: var(--text-muted);
}

.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--border-input);
  border-radius: 50%;
  border-top-color: var(--primary);
  animation: spinner 0.8s linear infinite;
}

@keyframes spinner {
  to { transform: rotate(360deg); }
}

@media (max-width: 768px) {
  .profile-container {
    padding: 16px;
  }

  .content-grid {
    grid-template-columns: 1fr;
  }

  .card {
    padding: 16px;
  }

  .stats {
    gap: 16px;
  }

  .stat-value {
    font-size: 1.25rem;
  }
}
</style>
