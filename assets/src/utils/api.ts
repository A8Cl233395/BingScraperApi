import axios from 'axios';
import { getAuthHeaders, clearAuth, redirectToLogin } from './auth';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE,
});

api.interceptors.request.use((config) => {
  const headers = getAuthHeaders();

  if (!headers.uid || !headers.session || !headers.token) {
    if (!window.location.pathname.startsWith('/login')) {
      redirectToLogin();
    }
    return Promise.reject(new axios.Cancel('未登录，已跳转到登录页'));
  }

  Object.assign(config.headers, headers);
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      clearAuth();
      redirectToLogin();
    }
    return Promise.reject(error);
  }
);

export default api;
