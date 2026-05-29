<script setup lang="ts">
import { ref, onMounted } from 'vue';

const uid = ref('');
const pwd = ref('');
const isSubmitting = ref(false);
const errorMessage = ref('');
const toastMessage = ref('');
const toastType = ref('success');
const showToastMsg = ref(false);
const isUidError = ref(false);

const uidInput = ref<HTMLInputElement | null>(null);

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
  errorMessage.value = '';
};

const onPwdInput = () => {
  updateValidation();
  errorMessage.value = '';
};

const showToast = (message: string, type = 'success') => {
  toastMessage.value = message;
  toastType.value = type;
  showToastMsg.value = true;
  setTimeout(() => {
    showToastMsg.value = false;
  }, 3000);
};

const handleSubmit = async () => {
  if (isSubmitting.value) return;

  const uidVal = uid.value.trim();
  const pwdVal = pwd.value.trim();

  if (!/^\d+$/.test(uidVal)) {
    errorMessage.value = '用户ID只能包含数字';
    isUidError.value = true;
    return;
  }

  isSubmitting.value = true;
  errorMessage.value = '';

  try {
    const response = await fetch(`${import.meta.env.VITE_API_BASE}/api/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uid: parseInt(uidVal), pwd: pwdVal })
    });

    if (response.status === 200) {
      const serverToken = await response.text();
      localStorage.setItem('uid', uidVal);
      localStorage.setItem('token', serverToken);
      
      showToast('登录成功，正在跳转...', 'success');
      setTimeout(() => {
        window.location.href = '/webchat';
      }, 500);
    } else {
      const errorText = await response.text();
      errorMessage.value = errorText || '登录失败，请检查用户ID和密码';
      pwd.value = '';
      showToast('登录失败', 'error');
    }
  } catch (error) {
    console.error('Error:', error);
    errorMessage.value = '网络错误，请稍后重试';
    showToast('网络错误', 'error');
  } finally {
    isSubmitting.value = false;
  }
};

onMounted(() => {
  if (uidInput.value) uidInput.value.focus();
  updateValidation();
});
</script>

<template>
  <div class="login-container">
    <div class="card">
      <h1 class="title">登录</h1>
      
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

        <div class="error-message" :class="{ show: errorMessage }">
          {{ errorMessage }}
        </div>

        <button 
          type="submit" 
          class="submit-btn" 
          :class="{ loading: isSubmitting }"
          :disabled="isSubmitting || !uid.trim() || !pwd.trim() || isUidError"
        >
          登录
        </button>
      </form>
    </div>

    <div class="toast" :class="[toastType, { show: showToastMsg }]">
      {{ toastMessage }}
    </div>
  </div>
</template>

<style scoped>
.login-container {
  --vscode-bg: var(--bg-main);
  --vscode-modalBg: var(--bg-panel);
  --vscode-text: var(--text-main);
  --vscode-blue: var(--primary);
  --vscode-blueHover: var(--primary-hover);
  --vscode-input: var(--bg-main);
  --vscode-inputBorder: var(--border-input);
  --vscode-hover: var(--bg-hover);

  background-color: var(--vscode-bg);
  color: var(--vscode-text);
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  width: 100%;
  transition: background-color 0.3s ease, color 0.3s ease;
}

.card {
  background-color: var(--vscode-modalBg);
  border-radius: 8px;
  padding: 24px;
  width: 100%;
  max-width: 448px;
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
  border: 1px solid var(--border-color);
  transition: all 0.3s ease;
}

.title {
  font-size: 1.25rem;
  font-weight: 600;
  margin-bottom: 24px;
  text-align: center;
  color: var(--vscode-text);
}

.form-group {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  font-size: 0.85rem;
  margin-bottom: 6px;
  color: var(--text-muted);
}

.form-input {
  width: 100%;
  padding: 12px 16px;
  background-color: var(--vscode-input);
  border: 1px solid var(--vscode-inputBorder);
  border-radius: 8px;
  color: var(--vscode-text);
  font-size: 0.95rem;
  transition: all 0.15s ease;
  outline: none;
}

.form-input:focus {
  border-color: var(--vscode-blue);
  box-shadow: 0 0 0 1px var(--vscode-blue);
}

.form-input::placeholder {
  color: var(--text-placeholder);
}

.form-input.error {
  border-color: var(--danger);
  box-shadow: 0 0 0 1px var(--danger);
}

.error-message {
  display: none;
  margin-top: 8px;
  padding: 12px;
  background-color: var(--danger-bg);
  border: 1px solid var(--danger);
  border-radius: 6px;
  color: var(--danger);
  font-size: 0.9rem;
}

.error-message.show {
  display: block;
  animation: fadeIn 0.2s ease;
}

.submit-btn {
  width: 100%;
  padding: 12px 24px;
  background-color: var(--vscode-blue);
  color: var(--primary-text);
  border: none;
  border-radius: 8px;
  font-size: 0.95rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  margin-top: 8px;
}

.submit-btn:hover:not(:disabled) {
  background-color: var(--vscode-blueHover);
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
  width: 20px;
  height: 20px;
  top: 50%;
  left: 50%;
  margin-left: -10px;
  margin-top: -10px;
  border: 2px solid var(--primary-text);
  border-radius: 50%;
  border-top-color: transparent;
  animation: spinner 0.8s linear infinite;
}

@keyframes spinner {
  to { transform: rotate(360deg); }
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(5px); }
  to { opacity: 1; transform: translateY(0); }
}

.toast {
  position: fixed;
  top: 20px;
  left: 50%;
  transform: translateX(-50%) translateY(-20px);
  padding: 12px 24px;
  background-color: var(--vscode-modalBg);
  border: 1px solid var(--vscode-inputBorder);
  border-radius: 8px;
  font-size: 0.9rem;
  opacity: 0;
  transition: all 0.2s ease;
  z-index: 1000;
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2);
  pointer-events: none;
}

.toast.show {
  opacity: 1;
  transform: translateX(-50%) translateY(0);
}

.toast.success {
  border-color: var(--success-border);
  color: var(--success);
}

.toast.error {
  border-color: var(--danger);
  color: var(--danger);
}

@media (max-width: 640px) {
  .login-container {
    padding: 12px;
  }
  .card {
    padding: 20px;
  }
  .title {
    font-size: 1.1rem;
  }
}
</style>
