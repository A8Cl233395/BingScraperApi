<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';

const invite = ref('');
const qqid = ref('');
const turnstileToken = ref<string | null>(null);
const isSubmitting = ref(false);
const resultText = ref('');
const showResultContainer = ref(false);
const copyBtnText = ref('复制');
const isCopied = ref(false);
const toastMessage = ref('');
const toastType = ref('success');
const showToastMsg = ref(false);
const turnstileContainer = ref<HTMLElement | null>(null);
let widgetId: string | undefined = undefined;

const showToast = (message: string, type = 'success') => {
  toastMessage.value = message;
  toastType.value = type;
  showToastMsg.value = true;
  setTimeout(() => {
    showToastMsg.value = false;
  }, 3000);
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

onMounted(() => {
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

const handleSubmit = async () => {
  if (isSubmitting.value || !turnstileToken.value) return;

  const qqidVal = qqid.value.trim();
  if (!/^\d+$/.test(qqidVal)) {
    showToast('QQ号只能包含数字', 'error');
    return;
  }

  isSubmitting.value = true;
  showResultContainer.value = false;

  try {
    const response = await fetch(`${import.meta.env.VITE_API_BASE}/invite`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        challenge: turnstileToken.value,
        qqid: qqidVal,
        invite: invite.value.trim()
      })
    });

    if (!response.ok) {
      throw new Error(`请求失败: ${response.status}`);
    }

    const text = await response.text();
    
    resultText.value = text;
    showResultContainer.value = true;
    
    await autoCopy(text);
    showToast('验证码已复制到剪贴板', 'success');
  } catch (error: any) {
    console.error('Error:', error);
    showToast(error.message || '获取验证码失败，请稍后重试', 'error');
    
    if ((window as any).turnstile) {
      (window as any).turnstile.reset(widgetId);
    }
    turnstileToken.value = null;
  } finally {
    isSubmitting.value = false;
  }
};

const autoCopy = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text);
  } catch (err) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
  }
};

const copyToClipboard = async () => {
  if (!resultText.value) return;
  try {
    await navigator.clipboard.writeText(resultText.value);
    copyBtnText.value = '已复制';
    isCopied.value = true;
    setTimeout(() => {
      copyBtnText.value = '复制';
      isCopied.value = false;
    }, 2000);
  } catch (err) {
    showToast('复制失败，请手动复制', 'error');
  }
};
</script>

<template>
  <div class="invite-container">
    <div class="card">
      <h1 class="title">验证码获取</h1>
      
      <form @submit.prevent="handleSubmit">
        <div class="form-group">
          <label class="form-label" for="invite">邀请码</label>
          <input 
            type="text" 
            id="invite" 
            v-model="invite"
            class="form-input" 
            placeholder="请输入邀请码"
            required
            autocomplete="off"
          >
        </div>

        <div class="form-group">
          <label class="form-label" for="qqid">QQ号</label>
          <input 
            type="text" 
            id="qqid" 
            v-model="qqid"
            class="form-input" 
            placeholder="请输入QQ号"
            required
            inputmode="numeric"
            pattern="[0-9]*"
            autocomplete="off"
          >
        </div>

        <div class="turnstile-container" ref="turnstileContainer"></div>

        <button 
          type="submit" 
          class="submit-btn" 
          :class="{ loading: isSubmitting }"
          :disabled="!invite.trim() || !qqid.trim() || !turnstileToken || isSubmitting"
        >
          获取验证码
        </button>
      </form>

      <div class="result-container" :class="{ show: showResultContainer }">
        <div class="result-label">您的验证码</div>
        <div class="result-content">
          <div class="result-text">{{ resultText }}</div>
          <button 
            class="copy-btn" 
            :class="{ copied: isCopied }"
            @click="copyToClipboard"
          >
            {{ copyBtnText }}
          </button>
        </div>
      </div>
    </div>

    <div class="toast" :class="[toastType, { show: showToastMsg }]">
      {{ toastMessage }}
    </div>
  </div>
</template>

<style scoped>
.invite-container {
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

.turnstile-container {
  margin: 20px 0;
  display: flex;
  justify-content: center;
  min-height: 65px;
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

.result-container {
  margin-top: 20px;
  padding: 16px;
  background-color: var(--bg-panel);
  border: 1px solid var(--border-input);
  border-radius: 8px;
  display: none;
}

.result-container.show {
  display: block;
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(5px); }
  to { opacity: 1; transform: translateY(0); }
}

.result-label {
  font-size: 0.85rem;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.result-content {
  display: flex;
  gap: 8px;
  align-items: center;
}

.result-text {
  flex: 1;
  padding: 10px 12px;
  background-color: var(--bg-main);
  border: 1px solid var(--border-input);
  border-radius: 6px;
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  font-size: 0.85rem;
  word-break: break-all;
  color: var(--primary);
}

.copy-btn {
  padding: 8px 16px;
  background-color: var(--vscode-input);
  border: 1px solid var(--vscode-inputBorder);
  border-radius: 6px;
  color: var(--vscode-text);
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.copy-btn:hover {
  background-color: var(--vscode-hover);
  border-color: var(--vscode-blue);
}

.copy-btn.copied {
  background-color: #2d5a27;
  border-color: #3c8c3c;
  color: #7ee787;
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
  border-color: #3c8c3c;
  color: #7ee787;
}

.toast.error {
  border-color: var(--danger);
  color: var(--danger);
}

@media (max-width: 640px) {
  .invite-container {
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
