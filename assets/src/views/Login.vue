<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useToast } from '../composables/useToast';
import ToastMessage from '../components/ToastMessage.vue';

const { showToast } = useToast();

const uid = ref('');
const pwd = ref('');
const isSubmitting = ref(false);
const errorMessage = ref('');
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
  const urlParams = new URLSearchParams(window.location.search);
  const uidParam = urlParams.get('uid');
  if (uidParam) {
    uid.value = uidParam;
    updateValidation();
  }
  if (uidInput.value) uidInput.value.focus();
  updateValidation();
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

        <div v-if="errorMessage" class="error-message">
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

    <ToastMessage />
  </div>
</template>

<style scoped>
.card {
  max-width: 448px;
}
</style>
