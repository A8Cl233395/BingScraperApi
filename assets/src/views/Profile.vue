<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue';
import { state } from '../store';
import api from '../utils/api';
import ConfirmModal from '../components/ConfirmModal.vue';
import { type ThemeMode, applyTheme, storeTheme, getCurrentTheme } from '../utils/theme';

const uid = localStorage.getItem('uid') || '';
const convCount = ref(0);
const memories = ref<string[]>([]);
const createdAt = ref(0);
const isLoading = ref(true);

const maskedUid = computed(() => {
  if (uid.length <= 2) return uid;
  if (uid.length <= 4) return uid[0] + '*' + uid[uid.length - 1];
  return uid.slice(0, 2) + '*'.repeat(uid.length - 4) + uid.slice(-2);
});

const daysUsed = computed(() => {
  if (!createdAt.value) return 0;
  return Math.floor((Date.now() / 1000 - createdAt.value) / 86400);
});

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

const activeTab = ref<'account' | 'memory' | 'appearance'>('account');
const isSidebarOpen = ref(true);
const isMobile = ref(false);

const showLogoutConfirm = ref(false);

const currentTheme = ref<ThemeMode>(getCurrentTheme());

const setTheme = (theme: ThemeMode) => {
  currentTheme.value = theme;
  applyTheme(theme);
  storeTheme(theme);
};

const checkMobile = () => {
  isMobile.value = window.innerWidth < 768;
  if (!isMobile.value) {
    isSidebarOpen.value = true;
  }
};

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
    createdAt.value = data.created_at || 0;
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
    showToast('密码修改成功，即将重新登录...');
    const uid = localStorage.getItem('uid');
    localStorage.removeItem('uid');
    localStorage.removeItem('token');
    setTimeout(() => {
      window.location.href = `/login?uid=${uid || ''}`;
    }, 1000);
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

const handleLogout = () => {
  showLogoutConfirm.value = true;
};

const confirmLogout = () => {
  localStorage.removeItem('uid');
  localStorage.removeItem('token');
  window.location.href = '/login';
};

const goBack = () => {
  window.location.href = '/webchat';
};

const switchTab = (tab: 'account' | 'memory' | 'appearance') => {
  activeTab.value = tab;
  if (isMobile.value) {
    isSidebarOpen.value = false;
  }
};

const handleHashChange = () => {
  const hash = window.location.hash;
  const match = hash.match(/^#\/(account|memory|appearance)$/);
  if (match) {
    activeTab.value = match[1] as 'account' | 'memory' | 'appearance';
  } else {
    activeTab.value = 'account';
  }
};

onMounted(() => {
  loadProfile();
  checkMobile();
  window.addEventListener('resize', checkMobile);

  const hash = window.location.hash;
  const match = hash.match(/^#\/(account|memory|appearance)$/);
  if (match) {
    activeTab.value = match[1] as 'account' | 'memory' | 'appearance';
  }
  window.addEventListener('hashchange', handleHashChange);
});

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile);
  window.removeEventListener('hashchange', handleHashChange);
});

watch(activeTab, (newTab) => {
  const newHash = `#/${newTab}`;
  if (window.location.hash !== newHash) {
    window.history.pushState({}, '', newHash);
  }
});
</script>

<template>
  <div class="profile-container">
    <!-- Sidebar Overlay -->
    <div v-if="isMobile && isSidebarOpen" class="sidebar-overlay" @click="isSidebarOpen = false"></div>

    <div class="profile-layout">
      <!-- Left Sidebar -->
      <aside 
        class="sidebar"
        :class="[
          isSidebarOpen ? 'translate-x-0' : '-translate-x-full',
          isMobile ? 'fixed inset-y-0 left-0 w-72' : 'relative w-64',
          !isSidebarOpen && !isMobile ? 'md:-ml-64 md:translate-x-0 md:border-r-0' : 'border-r border-border-main md:ml-0'
        ]"
      >
        <div :class="isMobile ? 'w-72' : 'w-64'" class="h-full flex flex-col shrink-0">
          <!-- Header -->
          <div class="p-4 flex justify-between items-center">
            <span class="font-bold text-lg text-text-main">个人资料</span>
            <button @click="isSidebarOpen = false" class="md:hidden text-text-muted hover:text-text-main">
              <FontAwesomeIcon :icon="['fas', 'xmark']" />
            </button>
          </div>

          <!-- Back Button -->
          <div class="px-4 mb-4">
            <button 
              @click="goBack"
              class="w-full px-4 py-2 border border-dashed border-border-input rounded-md text-sm hover:bg-bg-hover flex items-center justify-center cursor-pointer text-text-muted transition-colors"
            >
              <FontAwesomeIcon :icon="['fas', 'chevron-left']" class="mr-2" />
              <span>返回聊天</span>
            </button>
          </div>

          <!-- Tab List -->
          <div class="flex-1 min-h-0 px-2 space-y-1">
            <button
              class="w-full flex items-center gap-2 p-2.5 rounded-md cursor-pointer text-sm transition-colors"
              :class="activeTab === 'account' ? 'bg-bg-active text-text-main' : 'text-text-muted hover:text-text-main hover:bg-bg-hover'"
              @click="switchTab('account')"
            >
              <FontAwesomeIcon :icon="['fas', 'gauge']" />
              <span>账户设置</span>
            </button>
            <button
              class="w-full flex items-center gap-2 p-2.5 rounded-md cursor-pointer text-sm transition-colors"
              :class="activeTab === 'memory' ? 'bg-bg-active text-text-main' : 'text-text-muted hover:text-text-main hover:bg-bg-hover'"
              @click="switchTab('memory')"
            >
              <FontAwesomeIcon :icon="['fas', 'brain']" />
              <span>记忆管理</span>
            </button>
            <button
              class="w-full flex items-center gap-2 p-2.5 rounded-md cursor-pointer text-sm transition-colors"
              :class="activeTab === 'appearance' ? 'bg-bg-active text-text-main' : 'text-text-muted hover:text-text-main hover:bg-bg-hover'"
              @click="switchTab('appearance')"
            >
              <FontAwesomeIcon :icon="['fas', 'palette']" />
              <span>外观设置</span>
            </button>
          </div>
        </div>
      </aside>

      <!-- Mobile Toggle Button -->
      <button 
        v-if="isMobile && !isSidebarOpen" 
        class="fixed top-4 left-4 z-50 p-2 rounded-md bg-bg-panel border border-border-main text-text-muted hover:text-text-main hover:bg-bg-hover transition-colors shadow-sm"
        @click="isSidebarOpen = true"
      >
        <FontAwesomeIcon :icon="['fas', 'bars']" />
      </button>

      <!-- Main Content -->
      <div class="tab-content">
        <div v-if="isLoading" class="loading-state">
          <FontAwesomeIcon :icon="['fas', 'spinner']" spin />
          <span>加载中...</span>
        </div>

        <!-- Account Settings -->
        <div v-else-if="activeTab === 'account'" class="account-section">
          <!-- 用户摘要卡片 -->
          <div class="card user-summary">
            <div class="user-summary-header">
              <div class="user-summary-avatar">
                <FontAwesomeIcon :icon="['fas', 'user']" />
              </div>
              <div class="user-summary-info">
                <span class="user-summary-uid">用户 #{{ maskedUid }}</span>
                <span class="user-summary-days">
                  <FontAwesomeIcon :icon="['fas', 'clock']" />
                  已使用 {{ daysUsed }} 天
                </span>
              </div>
            </div>
            <div class="user-summary-stats">
              <div class="stat-item">
                <div class="stat-content">
                  <span class="stat-value">{{ convCount }}</span>
                  <span class="stat-label">对话</span>
                </div>
              </div>
              <div class="stat-divider"></div>
              <div class="stat-item">
                <div class="stat-content">
                  <span class="stat-value">{{ memories.length }}</span>
                  <span class="stat-label">记忆</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 偏好设置 -->
          <div class="card preferences-card">
            <div class="card-header">
              <FontAwesomeIcon :icon="['fas', 'gear']" />
              <h2>偏好设置</h2>
            </div>
            <div class="pref-list">
              <div class="pref-item">
                <span class="pref-label">当前模型</span>
                <span class="pref-badge model-badge">{{ state.currentModel || '未设置' }}</span>
              </div>
              <div class="pref-item">
                <span class="pref-label">视觉模型</span>
                <span class="pref-badge model-badge">{{ state.currentVModel || '未设置' }}</span>
              </div>
              <div class="pref-item">
                <span class="pref-label">Thinking</span>
                <span class="pref-badge" :class="state.isThinking ? 'badge-on' : 'badge-off'">
                  {{ state.isThinking ? '开启' : '关闭' }}
                </span>
              </div>
              <div class="pref-item">
                <span class="pref-label">Function Calling</span>
                <span class="pref-badge" :class="state.isEnableFunction ? 'badge-on' : 'badge-off'">
                  {{ state.isEnableFunction ? '开启' : '关闭' }}
                </span>
              </div>
            </div>
          </div>

          <!-- 修改密码 -->
          <div class="card password-card">
            <div class="card-header">
              <FontAwesomeIcon :icon="['fas', 'key']" />
              <h2>修改密码</h2>
            </div>
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

              <div class="form-row">
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
              </div>

              <div v-if="pwdError" class="error-message">
                <FontAwesomeIcon :icon="['fas', 'triangle-exclamation']" />
                {{ pwdError }}
              </div>
              <div v-if="pwdSuccess" class="success-message">
                <FontAwesomeIcon :icon="['fas', 'check']" />
                {{ pwdSuccess }}
              </div>

              <button
                type="submit"
                class="submit-btn"
                :class="{ loading: isChangingPwd }"
                :disabled="isChangingPwd"
              >
                <FontAwesomeIcon v-if="isChangingPwd" :icon="['fas', 'spinner']" spin />
                <span>修改密码</span>
              </button>
            </form>
          </div>

          <!-- 退出登录 -->
          <div class="card logout-card">
            <button class="logout-btn" @click="handleLogout">
              <FontAwesomeIcon :icon="['fas', 'right-from-bracket']" />
              <span>退出登录</span>
            </button>
          </div>
        </div>

        <!-- Memory Management -->
        <div v-else-if="activeTab === 'memory'" class="memory-section">
          <div class="memory-header">
            <FontAwesomeIcon :icon="['fas', 'brain']" />
            <h2>记忆管理</h2>
          </div>
          <p class="memory-desc">记忆会作为上下文提供给 AI，帮助其更好地理解你的需求。</p>

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
                <FontAwesomeIcon v-if="isAddingMemory" :icon="['fas', 'spinner']" spin />
                <FontAwesomeIcon v-else :icon="['fas', 'plus']" />
                <span>添加</span>
              </button>
            </div>
            <div v-if="memError" class="error-message">
              <FontAwesomeIcon :icon="['fas', 'triangle-exclamation']" />
              {{ memError }}
            </div>
          </form>

          <div v-if="memories.length === 0" class="empty-state">
            <FontAwesomeIcon :icon="['fas', 'brain']" />
            <span>暂无记忆</span>
          </div>

          <div v-else class="memory-list">
            <div v-for="(mem, index) in memories" :key="index" class="memory-item">
              <span class="memory-text">{{ mem }}</span>
              <button class="remove-btn" @click="handleRemoveMemory(mem)" title="删除">
                <FontAwesomeIcon :icon="['fas', 'xmark']" />
              </button>
            </div>
          </div>

          <div v-if="memories.length > 0" class="memory-count">
            {{ memories.length }} / 50 条记忆
          </div>
        </div>

        <!-- Appearance Settings -->
        <div v-else-if="activeTab === 'appearance'" class="appearance-section">
          <div class="appearance-header">
            <FontAwesomeIcon :icon="['fas', 'palette']" />
            <h2>外观设置</h2>
          </div>
          <p class="appearance-desc">选择你喜欢的界面主题风格。</p>

          <div class="theme-options">
            <button
              class="theme-option"
              :class="{ active: currentTheme === 'light' }"
              @click="setTheme('light')"
            >
              <FontAwesomeIcon :icon="['fas', 'sun']" class="theme-icon" />
              <span class="theme-label">浅色</span>
              <span class="theme-desc">明亮清爽</span>
            </button>
            <button
              class="theme-option"
              :class="{ active: currentTheme === 'dark' }"
              @click="setTheme('dark')"
            >
              <FontAwesomeIcon :icon="['fas', 'moon']" class="theme-icon" />
              <span class="theme-label">深色</span>
              <span class="theme-desc">护眼舒适</span>
            </button>
            <button
              class="theme-option"
              :class="{ active: currentTheme === 'system' }"
              @click="setTheme('system')"
            >
              <FontAwesomeIcon :icon="['fas', 'desktop']" class="theme-icon" />
              <span class="theme-label">跟随系统</span>
              <span class="theme-desc">自动切换</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Logout Confirmation Modal -->
    <ConfirmModal
      :show="showLogoutConfirm"
      title="退出登录"
      message="确定要退出当前账号吗？"
      confirmText="退出"
      cancelText="取消"
      :isDanger="true"
      @confirm="confirmLogout"
      @cancel="showLogoutConfirm = false"
    />

    <div class="toast" :class="[toastType, { show: showToastMsg }]">
      <FontAwesomeIcon :icon="toastType === 'success' ? ['fas', 'check'] : ['fas', 'triangle-exclamation']" />
      {{ toastMessage }}
    </div>
  </div>
</template>

<style scoped>
.profile-container {
  background-color: var(--bg-main);
  color: var(--text-main);
  min-height: 100vh;
  transition: background-color 0.3s ease, color 0.3s ease;
}

.sidebar-overlay {
  position: fixed;
  inset: 0;
  background-color: rgba(0, 0, 0, 0.4);
  z-index: 90;
}

.profile-layout {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  background-color: var(--bg-panel);
  transition: all 0.3s ease-in-out;
  z-index: 100;
  box-shadow: 1px 0 5px rgba(0, 0, 0, 0.05);
  overflow: hidden;
}

.tab-content {
  flex: 1;
  padding: 24px;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px;
  color: var(--text-muted);
  font-size: 1rem;
}

/* 账户选项卡 */
.account-section {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: auto auto auto;
  gap: 16px;
  max-width: 100%;
}

.user-summary {
  grid-column: 1 / -1;
}

.preferences-card {
  grid-column: 1;
}

.password-card {
  grid-column: 2;
}

.logout-card {
  grid-column: 1 / -1;
}

/* 用户摘要卡片 */
.user-summary {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.user-summary-header {
  display: flex;
  align-items: center;
  gap: 16px;
}

.user-summary-avatar {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background-color: var(--primary);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
  flex-shrink: 0;
}

.user-summary-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.user-summary-uid {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-main);
}

.user-summary-days {
  font-size: 0.8rem;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 6px;
}

.user-summary-stats {
  display: flex;
  align-items: center;
  justify-content: center;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

.stat-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 8px 16px;
}

.stat-content {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-value {
  font-size: 2.25rem;
  font-weight: 700;
  color: var(--primary);
  line-height: 1.2;
}

.stat-label {
  font-size: 0.7rem;
  color: var(--text-muted);
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.stat-divider {
  width: 1px;
  height: 48px;
  background-color: var(--border-color);
}

/* 偏好设置卡片 */
.preferences-card .card-header {
  margin-bottom: 16px;
}

.pref-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.pref-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: var(--bg-main);
  border-radius: 6px;
  border: 1px solid var(--border-color);
}

.pref-label {
  font-size: 0.85rem;
  color: var(--text-muted);
}

.pref-badge {
  font-size: 0.75rem;
  font-weight: 500;
  padding: 3px 10px;
  border-radius: 4px;
  background: var(--bg-hover);
  color: var(--text-main);
}

.model-badge {
  background: rgba(0, 95, 184, 0.1);
  color: var(--primary);
}

.badge-on {
  background: var(--success-bg);
  color: var(--success);
}

.badge-off {
  background: var(--bg-hover);
  color: var(--text-muted);
}

/* 外观设置 */
.appearance-section {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.appearance-header {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-main);
}

.appearance-header svg {
  font-size: 1rem;
  color: var(--primary);
}

.appearance-header h2 {
  font-size: 0.95rem;
  font-weight: 600;
  margin: 0;
}

.appearance-desc {
  font-size: 0.85rem;
  color: var(--text-muted);
  margin: 0;
}

.theme-options {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.theme-option {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 20px 16px;
  background: var(--bg-panel);
  border: 2px solid var(--border-color);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
  color: var(--text-muted);
}

.theme-option:hover {
  border-color: var(--text-placeholder);
  background: var(--bg-hover);
}

.theme-option.active {
  border-color: var(--primary);
  color: var(--primary);
  background: var(--bg-panel);
}

.theme-icon {
  font-size: 1.8rem;
}

.theme-label {
  font-size: 0.9rem;
  font-weight: 600;
}

.theme-desc {
  font-size: 0.75rem;
  color: var(--text-placeholder);
}

.theme-option.active .theme-desc {
  color: var(--primary);
  opacity: 0.7;
}

/* 通用卡片 */
.card {
  background-color: var(--bg-panel);
  border-radius: 8px;
  padding: 24px;
  border: 1px solid var(--border-color);
}

.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;
  color: var(--text-main);
}

.card-header svg {
  font-size: 1rem;
  color: var(--primary);
}

.card-header h2 {
  font-size: 0.95rem;
  font-weight: 600;
  margin: 0;
}

/* 表单 */
.form-group {
  margin-bottom: 16px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.form-label {
  display: block;
  font-size: 0.8rem;
  margin-bottom: 6px;
  color: var(--text-muted);
  font-weight: 500;
}

.form-input {
  width: 100%;
  padding: 10px 14px;
  background-color: var(--bg-main);
  border: 1px solid var(--border-input);
  border-radius: 8px;
  color: var(--text-main);
  font-size: 0.9rem;
  transition: all 0.15s ease;
  outline: none;
  box-sizing: border-box;
}

.form-input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px var(--primary-bg);
}

.form-input::placeholder {
  color: var(--text-placeholder);
}

.error-message {
  margin-top: 12px;
  padding: 10px 14px;
  background-color: var(--danger-bg);
  border: 1px solid var(--danger);
  border-radius: 8px;
  color: var(--danger);
  font-size: 0.85rem;
  display: flex;
  align-items: center;
  gap: 8px;
}

.success-message {
  margin-top: 12px;
  padding: 10px 14px;
  background-color: var(--success-bg);
  border: 1px solid var(--success-border);
  border-radius: 8px;
  color: var(--success);
  font-size: 0.85rem;
  display: flex;
  align-items: center;
  gap: 8px;
}

.submit-btn {
  width: 100%;
  padding: 12px 20px;
  background-color: var(--primary);
  color: var(--primary-text);
  border: none;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  margin-top: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
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

.submit-btn.loading svg {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  color: var(--primary-text);
}

/* 退出登录 */
.logout-card {
  padding: 16px 24px;
}

.logout-btn {
  width: 100%;
  padding: 10px 20px;
  background-color: transparent;
  color: var(--danger);
  border: 1px solid var(--danger);
  border-radius: 6px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.logout-btn:hover {
  background-color: var(--danger);
  color: white;
}

.memory-section {
  width: 100%;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.memory-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
  color: var(--text-main);
}

.memory-header svg {
  font-size: 1rem;
  color: var(--primary);
}

.memory-header h2 {
  font-size: 0.95rem;
  font-weight: 600;
  margin: 0;
}

.memory-desc {
  font-size: 0.85rem;
  color: var(--text-muted);
  margin: 0 0 20px 0;
}

.memory-add-form {
  margin-bottom: 20px;
}

.memory-input-row {
  display: flex;
  gap: 10px;
}

.memory-input-row .form-input {
  flex: 1;
}

.memory-textarea {
  resize: none;
  min-height: 42px;
  line-height: 1.5;
  overflow-y: auto;
}

.add-btn {
  padding: 10px 18px;
  background-color: var(--primary);
  color: var(--primary-text);
  border: none;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 6px;
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

.add-btn.loading svg {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  color: var(--primary-text);
}

.empty-state {
  text-align: center;
  padding: 48px 24px;
  color: var(--text-muted);
  font-size: 0.9rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.empty-state svg {
  font-size: 2rem;
  opacity: 0.5;
}

.memory-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex: 1;
}

.memory-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  background-color: var(--bg-main);
  border: 1px solid var(--border-input);
  border-radius: 8px;
  transition: all 0.15s ease;
}

.memory-item:hover {
  border-color: var(--primary);
  background-color: var(--bg-hover);
}

.memory-text {
  flex: 1;
  font-size: 0.85rem;
  word-break: break-all;
  line-height: 1.5;
  white-space: pre-wrap;
}

.remove-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: transparent;
  border: none;
  border-radius: 6px;
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
  margin-top: 16px;
  text-align: right;
  font-size: 0.8rem;
  color: var(--text-muted);
}

@media (max-width: 767px) {
  .profile-layout {
    flex-direction: column;
  }

  .tab-content {
    padding: 16px;
  }

  .account-section {
    grid-template-columns: 1fr;
  }

  .user-summary,
  .preferences-card,
  .password-card,
  .logout-card {
    grid-column: 1;
  }

  .user-summary-avatar {
    width: 48px;
    height: 48px;
    font-size: 1.25rem;
  }

  .user-summary-uid {
    font-size: 1rem;
  }

  .stat-value {
    font-size: 1.25rem;
  }

  .form-row {
    grid-template-columns: 1fr;
    gap: 0;
  }

  .memory-input-row {
    flex-direction: column;
  }

  .add-btn {
    width: 100%;
    justify-content: center;
  }

  .theme-options {
    grid-template-columns: 1fr;
  }
}

@media (min-width: 768px) {
  .mobile-toggle-btn {
    display: none;
  }

  .sidebar-overlay {
    display: none;
  }
}
</style>
