import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE,
});

api.interceptors.request.use((config) => {
  const uid = localStorage.getItem('uid');
  const token = localStorage.getItem('token');

  if (!uid || !token) {
    if (!window.location.pathname.startsWith('/login')) {
      window.location.href = '/login';
    }
  }

  config.headers['uid'] = uid;
  config.headers['token'] = token;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem('uid');
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;
