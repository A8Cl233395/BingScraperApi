import { ref } from 'vue';

const toastMessage = ref('');
const toastType = ref<'success' | 'error'>('success');
const showToastMsg = ref(false);

let toastTimer: ReturnType<typeof setTimeout> | null = null;

export function useToast() {
  const showToast = (message: string, type: 'success' | 'error' = 'success') => {
    if (toastTimer) clearTimeout(toastTimer);
    toastMessage.value = message;
    toastType.value = type;
    showToastMsg.value = true;
    toastTimer = setTimeout(() => {
      showToastMsg.value = false;
    }, 3000);
  };

  return {
    toastMessage,
    toastType,
    showToastMsg,
    showToast,
  };
}
