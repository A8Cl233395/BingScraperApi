<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { useToast } from '../composables/useToast';

const { showToast } = useToast();

const uid = ref('');
const pwd = ref('');
const isSubmitting = ref(false);
const isUidError = ref(false);
const turnstileToken = ref<string | null>(null);

const uidInput = ref<HTMLInputElement | null>(null);
const turnstileContainer = ref<HTMLElement | null>(null);
let widgetId: string | undefined = undefined;

const updateValidation = () => {
  const uidVal = uid.value.trim();
  const isValid = /^\d+$/.test(uidVal);
  if (uidVal && !isValid) {
    isUidError.value = true;
  } else {
    isUidError.value = false;
  }
};

const onUidInput = () => {
  updateValidation();
};

const onPwdInput = () => {
  updateValidation();
};

const initTurnstile = () => {
  if ((window as any).turnstile && turnstileContainer.value) {
    widgetId = (window as any).turnstile.render(turnstileContainer.value, {
      sitekey: import.meta.env.VITE_TURNSTILE_SITEKEY,
      callback: function(token: string) {
        turnstileToken.value = token;
      },
      'error-callback': function() {
        turnstileToken.value = null;
        showToast('验证加载失败，请刷新页面重试', 'error');
      },
      'expired-callback': function() {
        turnstileToken.value = null;
        showToast('验证已过期，请重新验证', 'error');
      },
      theme: 'auto'
    });
  }
};

const handleSubmit = async () => {
  if (isSubmitting.value || !turnstileToken.value) return;

  const uidVal = uid.value.trim();
  const pwdVal = pwd.value.trim();

  if (!/^\d+$/.test(uidVal)) {
    isUidError.value = true;
    showToast('用户ID只能包含数字', 'error');
    return;
  }

  isSubmitting.value = true;

  try {
    const response = await fetch(`${import.meta.env.VITE_API_BASE}/api/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uid: parseInt(uidVal), pwd: pwdVal, challenge: turnstileToken.value })
    });

    if (response.status === 200) {
      const data = await response.json();
      localStorage.setItem('uid', uidVal);
      localStorage.setItem('session', data.session);
      localStorage.setItem('token', data.token);
      
      showToast('登录成功，正在跳转...', 'success');
      setTimeout(() => {
        window.location.href = '/webchat';
      }, 500);
    } else if (response.status === 400) {
      showToast('验证失败，请重试', 'error');
      if ((window as any).turnstile) {
        (window as any).turnstile.reset(widgetId);
      }
      turnstileToken.value = null;
    } else if (response.status === 403) {
      pwd.value = '';
      showToast('密码错误', 'error');
    } else {
      const errorText = await response.text();
      pwd.value = '';
      showToast(errorText || '登录失败', 'error');
    }
  } catch (error) {
    console.error('Error:', error);
    showToast('网络错误', 'error');
  } finally {
    isSubmitting.value = false;
  }
};

onMounted(() => {
  const hash = window.location.hash;
  const match = hash.match(/#uid=(\d+)/);
  if (match) {
    uid.value = match[1];
    updateValidation();
  }
  if (uidInput.value) uidInput.value.focus();
  updateValidation();

  if (!document.querySelector('script[src="https://challenges.cloudflare.com/turnstile/v0/api.js"]')) {
    const script = document.createElement('script');
    script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js';
    script.async = true;
    script.defer = true;
    script.onload = () => {
      setTimeout(initTurnstile, 100);
    };
    document.head.appendChild(script);
  } else {
    setTimeout(initTurnstile, 100);
  }
});

onUnmounted(() => {
  if ((window as any).turnstile && widgetId !== undefined) {
    (window as any).turnstile.remove(widgetId);
  }
});
</script>

<template>
  <div class="page-container">
    <div class="card">
      <h1 class="card-title">登录</h1>
      
      <form @submit.prevent="handleSubmit">
        <div class="form-group">
          <label class="form-label" for="uid">用户ID</label>
          <input 
            type="text" 
            id="uid" 
            v-model="uid"
            @input="onUidInput"
            class="form-input" 
            :class="{ error: isUidError }"
            placeholder="请输入用户ID"
            required
            inputmode="numeric"
            pattern="[0-9]*"
            autocomplete="username"
            ref="uidInput"
          >
        </div>

        <div class="form-group">
          <label class="form-label" for="pwd">密码</label>
          <input 
            type="password" 
            id="pwd" 
            v-model="pwd"
            @input="onPwdInput"
            class="form-input" 
            placeholder="请输入密码"
            required
            autocomplete="current-password"
          >
        </div>

        <div class="turnstile-container" ref="turnstileContainer"></div>

        <button 
          type="submit" 
          class="submit-btn" 
          :class="{ loading: isSubmitting }"
          :disabled="isSubmitting || !uid.trim() || !pwd.trim() || isUidError || !turnstileToken"
        >
          登录
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.card {
  max-width: 448px;
}

.turnstile-container {
  margin: 20px 0;
  display: flex;
  justify-content: center;
  min-height: 65px;
}
</style>
