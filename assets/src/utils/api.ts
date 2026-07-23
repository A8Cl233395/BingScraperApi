import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE,
});

api.interceptors.request.use((config) => {
  const uid = localStorage.getItem('uid');
  const session = localStorage.getItem('session');
  const token = localStorage.getItem('token');

  if (!uid || !session || !token) {
    if (!window.location.pathname.startsWith('/login')) {
      const uidHash = uid ? `#uid=${uid}` : '';
      window.location.href = `/login${uidHash}`;
    }
    return Promise.reject(new axios.Cancel('未登录，已跳转到登录页'));
  }

  config.headers['uid'] = uid;
  config.headers['session'] = session;
  config.headers['token'] = token;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      const uid = localStorage.getItem('uid');
      localStorage.removeItem('uid');
      localStorage.removeItem('session');
      localStorage.removeItem('token');
      const uidHash = uid ? `#uid=${uid}` : '';
      window.location.href = `/login${uidHash}`;
    }
    return Promise.reject(error);
  }
);

export default api;
