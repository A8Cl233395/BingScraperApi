import { createRouter, createWebHistory } from 'vue-router';
import Chat from '../views/Chat.vue';

const routes = [
  {
    path: '/',
    name: 'Home',
    redirect: '/webchat'
  },
  {
    path: '/webchat',
    name: 'Chat',
    component: Chat
  }
];

const router = createRouter({
  history: createWebHistory(),
  routes
});

// Navigation guard
router.beforeEach((_to, _from, next) => {
  const uid = localStorage.getItem('uid');
  const token = localStorage.getItem('token');
  
  if (!uid || !token) {
    // Redirect to login.html (separate entry point)
    window.location.href = '/login';
    return;
  }
  next();
});

export default router;
