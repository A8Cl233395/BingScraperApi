import { reactive } from 'vue';
import api from '../utils/api';

export const state = reactive({
  isSidebarOpen: true,
  isMobile: false,
  chats: [] as [number, string][],
  currentChatId: null as number | null,
  currentModel: '',
  currentVModel: '',
  isThinking: false,
  isEnableFunction: true,
  defaultSettings: {
    model: '',
    vmodel: '',
    thinking: false,
    enable_function: true,
  },
  hasMoreHistory: true,
  isLoadingHistory: false,
  isMouseDown: false,
  isTextSelected: false,
  models: {} as Record<string, { desc: string; vision?: boolean; thinking?: boolean }>,
  
  async fetchHome() {
    try {
      const res = await api.get('/api/home');
      this.chats = res.data.chats;
      this.defaultSettings = {
        model: res.data.model,
        vmodel: res.data.vmodel,
        thinking: res.data.thinking,
        enable_function: res.data.enable_function,
      };
      // Initialize session settings with defaults
      this.currentModel = res.data.model;
      this.currentVModel = res.data.vmodel;
      this.isThinking = res.data.thinking;
      this.isEnableFunction = res.data.enable_function;
    } catch (e) {
      console.error('Failed to fetch home content', e);
    }
  },

  async fetchModels() {
    try {
      const res = await api.get('/api/models');
      this.models = res.data;
    } catch (e) {
      console.error('Failed to fetch models', e);
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
    } finally {
      this.isLoadingHistory = false;
    }
  }
});
