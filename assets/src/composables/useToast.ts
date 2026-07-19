let container: HTMLDivElement | null = null;

function getContainer(): HTMLDivElement {
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }
  return container;
}

const typeVarMap: Record<string, string> = {
  success: 'var(--success)',
  error: 'var(--danger)',
  info: 'var(--info)',
};

/**
 * 弹出 Toast
 * @param message - 显示的文字
 * @param type - 类型：success / error / info
 * @param duration - 自动消失毫秒数，默认 3000
 */
export function useToast() {
  const showToast = (
    message: string,
    type: 'success' | 'error' | 'info' = 'success',
    duration: number = 3000
  ) => {
    const parent = getContainer();

    const toast = document.createElement('div');
    toast.className = 'toast-item';

    const bar = document.createElement('div');
    bar.className = 'bar';
    bar.style.background = typeVarMap[type] || typeVarMap.success;
    toast.appendChild(bar);

    const body = document.createElement('div');
    body.className = 'body';
    body.textContent = message;
    toast.appendChild(body);

    const dismiss = () => {
      toast.classList.add('exit');
      setTimeout(() => {
        if (toast.parentNode) toast.remove();
      }, 150);
    };

    toast.addEventListener('click', dismiss);

    let timer = setTimeout(dismiss, duration);

    toast.addEventListener('mouseenter', () => clearTimeout(timer));
    toast.addEventListener('mouseleave', () => {
      timer = setTimeout(dismiss, Math.min(duration, 2000));
    });

    parent.appendChild(toast);
  };

  return { showToast };
}
