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
  <div class="page-container">
    <div class="card">
      <h1 class="card-title">验证码获取</h1>
      
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
.card {
  max-width: 448px;
}

/* Invite.vue 特殊样式 */
.turnstile-container {
  margin: 20px 0;
  display: flex;
  justify-content: center;
  min-height: 65px;
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
  background-color: var(--bg-main);
  border: 1px solid var(--border-input);
  border-radius: 6px;
  color: var(--text-main);
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.copy-btn:hover {
  background-color: var(--bg-hover);
  border-color: var(--primary);
}

.copy-btn.copied {
  background-color: var(--success-bg);
  border-color: var(--success-border);
  color: var(--success);
}
</style>
