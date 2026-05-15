import { ref, computed, onBeforeUnmount } from 'vue';

export interface LongPressOptions {
  /** 长按前的预延迟 (ms) */
  preDelay?: number;
  /** 长按确认延迟 (ms) */
  pressDelay?: number;
  /** 菜单宽度 (px)，用于边界计算 */
  menuWidth?: number;
  /** 菜单高度 (px)，用于边界计算 */
  menuHeight?: number;
}

/**
 * 通用长按菜单 composable
 * 封装长按计时器、菜单定位、边界限制等重复逻辑
 */
export function useLongPress(options: LongPressOptions = {}) {
  const {
    preDelay = 150,
    pressDelay = 400,
    menuWidth = 160,
    menuHeight = 100,
  } = options;

  const showMenu = ref(false);
  const menuPos = ref({ x: 0, y: 0 });
  const longPressTimer = ref<number | null>(null);
  const preLongPressTimer = ref<number | null>(null);
  const isPressing = ref(false);

  const cancelLongPress = () => {
    if (preLongPressTimer.value) {
      clearTimeout(preLongPressTimer.value);
      preLongPressTimer.value = null;
    }
    if (longPressTimer.value) {
      clearTimeout(longPressTimer.value);
      longPressTimer.value = null;
    }
    isPressing.value = false;
  };

  /**
   * 开始长按
   * @param e TouchEvent
   * @param onTriggered 可选回调，长按触发时执行（在 showMenu 设为 true 之前）
   */
  const startLongPress = (e: TouchEvent, onTriggered?: () => void) => {
    cancelLongPress();
    const touch = e.touches[0];
    menuPos.value = { x: touch.clientX, y: touch.clientY };
    preLongPressTimer.value = window.setTimeout(() => {
      isPressing.value = true;
      longPressTimer.value = window.setTimeout(() => {
        onTriggered?.();
        showMenu.value = true;
        isPressing.value = false;
      }, pressDelay);
    }, preDelay);
  };

  const menuStyle = computed(() => {
    if (!showMenu.value) return {};
    const x = menuPos.value.x;
    const y = menuPos.value.y;
    const screenWidth = window.innerWidth;
    const screenHeight = window.innerHeight;

    let left = x - 20;
    let top = y - 20;

    if (left + menuWidth > screenWidth - 10) left = screenWidth - menuWidth - 10;
    if (left < 10) left = 10;
    if (top + menuHeight > screenHeight - 10) top = screenHeight - menuHeight - 10;
    if (top < 10) top = 10;

    return {
      left: `${left}px`,
      top: `${top}px`,
      width: `${menuWidth}px`,
    };
  });

  const closeMenu = () => {
    showMenu.value = false;
  };

  onBeforeUnmount(() => {
    cancelLongPress();
  });

  return {
    showMenu,
    menuPos,
    isPressing,
    menuStyle,
    startLongPress,
    cancelLongPress,
    closeMenu,
  };
}
