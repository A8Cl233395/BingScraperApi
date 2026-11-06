import { ref, watch, nextTick, type Ref } from 'vue';
import { state } from '../store';

export interface AutoResizeTextareaOptions {
  maxHeight?: number;
  borderOffset?: number;
  onSubmit?: () => void;
  textareaRef?: Ref<HTMLTextAreaElement | null>;
}

/**
 * 自动调整高度与快捷键（Enter 提交 / Ctrl+Enter 换行）Composable
 * 统一 ChatInput、MessageBubble 编辑框与 Profile 记忆输入框的交互逻辑
 */
export function useAutoResizeTextarea(
  text: Ref<string>,
  options: AutoResizeTextareaOptions = {}
) {
  const { maxHeight = 200, borderOffset = 0, onSubmit } = options;
  const textareaRef = options.textareaRef ?? ref<HTMLTextAreaElement | null>(null);

  const adjustHeight = () => {
    const el = textareaRef.value;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight + borderOffset, maxHeight) + 'px';
  };

  const resetHeight = () => {
    if (textareaRef.value) {
      textareaRef.value.style.height = '';
    }
  };

  watch(text, () => {
    nextTick(adjustHeight);
  });

  const handleKeydown = (e: KeyboardEvent) => {
    if (e.key !== 'Enter' || e.isComposing) return;
    if (!state.isMobile && !e.ctrlKey && !e.shiftKey) {
      e.preventDefault();
      onSubmit?.();
    } else if (e.ctrlKey && textareaRef.value) {
      e.preventDefault();
      const textarea = textareaRef.value;
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      text.value = text.value.substring(0, start) + '\n' + text.value.substring(end);
      nextTick(() => {
        textarea.selectionStart = textarea.selectionEnd = start + 1;
        adjustHeight();
      });
    }
  };

  return {
    textareaRef,
    adjustHeight,
    resetHeight,
    handleKeydown,
  };
}
