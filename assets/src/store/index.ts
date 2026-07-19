import { reactive } from 'vue';
import api from '../utils/api';
import { isMobileDevice } from '../utils/device';
import { useToast } from '../composables/useToast';

const { showToast } = useToast();

const CONFIG_STORAGE_KEY = 'user_config';
const CONFIG_VERSION_KEY = 'config_version';

function loadConfigFromStorage() {
  try {
    const stored = localStorage.getItem(CONFIG_STORAGE_KEY);
    if (stored) {
      return JSON.parse(stored);
    }
  } catch {}
  return null;
}

function saveConfigToStorage(config: any) {
  localStorage.setItem(CONFIG_STORAGE_KEY, JSON.stringify(config));
}

function loadConfigVersion(): string {
  return localStorage.getItem(CONFIG_VERSION_KEY) || '';
}

function saveConfigVersion(version: string) {
  localStorage.setItem(CONFIG_VERSION_KEY, version);
}

const storedConfig = loadConfigFromStorage();

export const state = reactive({
  isSidebarOpen: !isMobileDevice(),
  isMobile: isMobileDevice(),
  chats: [] as [number, string][],
  currentChatId: null as number | null,
  currentModel: storedConfig?.model || '',
  previewImageUrl: null as string | null,
  currentVModel: storedConfig?.vmodel || '',
  isThinking: storedConfig?.thinking ?? false,
  isStreaming: false,
  isEnableFunction: storedConfig?.enable_function ?? true,
  aiSignal: 'idle' as 'idle' | 'thinking' | 'answering' | 'tool_calling',
  petEnabled: localStorage.getItem('pet_enabled') === 'true',
  defaultExpandThinking: localStorage.getItem('expand_thinking') === 'true',
  defaultExpandTools: localStorage.getItem('expand_tools') === 'true',
  chatRequiresVision: false,
  hasDraftImages: false,
  hasDraftFiles: false,
  get isVisionMode(): boolean {
    return this.chatRequiresVision || this.hasDraftImages;
  },
  defaultSettings: {
    model: storedConfig?.model || '',
    vmodel: storedConfig?.vmodel || '',
    thinking: storedConfig?.thinking ?? false,
    enable_function: storedConfig?.enable_function ?? true,
  },
  configVersion: loadConfigVersion(),
  hasMoreHistory: true,
  isLoadingHistory: false,
  isMouseDown: false,
  isTextSelected: false,
  selectionText: '',
  showSelectionOverlay: false,
  models: {} as Record<string, { desc: string; vision?: boolean; thinking?: boolean }>,

  async fetchHome() {
    try {
      const res = await api.get('/api/home');
      this.chats = res.data.chats;
      const serverVersion = res.data.config_version;
      if (!this.configVersion || serverVersion !== this.configVersion) {
        await this.fetchConfig();
      }
    } catch (e) {
      console.error('Failed to fetch home content', e);
      showToast('获取首页内容失败', 'error');
    }
  },

  async fetchConfig() {
    try {
      const res = await api.get('/api/config');
      const config = res.data;
      this.defaultSettings = {
        model: config.model,
        vmodel: config.vmodel,
        thinking: config.thinking,
        enable_function: config.enable_function,
      };
      this.currentModel = config.model;
      this.currentVModel = config.vmodel;
      this.isThinking = config.thinking;
      this.isEnableFunction = config.enable_function;
      this.configVersion = config.config_version;
      saveConfigToStorage(config);
      saveConfigVersion(config.config_version);
    } catch (e) {
      console.error('Failed to fetch config', e);
      showToast('获取配置失败', 'error');
    }
  },

  async updateConfig(payload: Record<string, any>) {
    try {
      const res = await api.post('/api/config', payload);
      this.configVersion = res.data;
      const stored = JSON.parse(localStorage.getItem(CONFIG_STORAGE_KEY) || '{}');
      Object.assign(stored, payload);
      stored.config_version = res.data;
      saveConfigToStorage(stored);
      saveConfigVersion(res.data);
      return res.data;
    } catch (e) {
      console.error('Failed to update config', e);
      showToast('更新配置失败', 'error');
      throw e;
    }
  },

  async fetchModels() {
    try {
      const res = await api.get('/api/models');
      this.models = res.data;
    } catch (e) {
      console.error('Failed to fetch models', e);
      showToast('获取模型列表失败', 'error');
    }
  },

  async deleteChat(id: number) {
    try {
      await api.get(`/api/delete?id=${id}`);
      this.chats = this.chats.filter(chat => chat[0] !== id);
      if (this.currentChatId === id) {
        this.currentChatId = null;
      }
    } catch (e) {
      console.error('Failed to delete chat', e);
      showToast('删除聊天失败', 'error');
    }
  },

  async fetchMoreHistory() {
    if (this.isLoadingHistory || !this.hasMoreHistory || this.chats.length === 0) return;
    this.isLoadingHistory = true;
    try {
      const lastId = this.chats[this.chats.length - 1][0];
      const res = await api.get(`/api/history?before=${lastId}`);
      if (res.data.length === 0) {
        this.hasMoreHistory = false;
      } else {
        this.chats.push(...res.data);
      }
    } catch (e) {
      console.error('Failed to fetch more history', e);
      showToast('获取历史记录失败', 'error');
    } finally {
      this.isLoadingHistory = false;
    }
  }
});
