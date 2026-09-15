import { ref, onUnmounted, type Ref } from 'vue';
import { performVr } from '../utils/file';
import { useToast } from './useToast';

export function useVoiceInput(textRef?: Ref<string>) {
  const { showToast } = useToast();

  const isRecording = ref(false);
  const isRecognizing = ref(false);

  let mediaStream: MediaStream | null = null;
  let mediaRecorder: MediaRecorder | null = null;
  let audioChunks: Blob[] = [];
  let cancelled = false;
  let stopRequested = false;
  let pendingResolve: ((text: string | null) => void) | null = null;

  const resolvePending = (text: string | null) => {
    if (pendingResolve) {
      pendingResolve(text);
      pendingResolve = null;
    }
  };

  const cleanup = () => {
    if (mediaStream) {
      mediaStream.getTracks().forEach(t => t.stop());
      mediaStream = null;
    }
    mediaRecorder = null;
    audioChunks = [];
    stopRequested = false;
  };

  onUnmounted(() => {
    cancelled = true;
    if (mediaRecorder?.state === 'recording') {
      mediaRecorder.stop();
    }
    cleanup();
    resolvePending(null);
  });

  const startRecording = async (): Promise<boolean> => {
    if (isRecognizing.value || isRecording.value) return false;

    cancelled = false;
    stopRequested = false;

    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      showToast('请允许麦克风权限', 'error');
      cleanup();
      resolvePending(null);
      return false;
    }

    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : 'audio/ogg';

    mediaRecorder = new MediaRecorder(mediaStream, { mimeType });
    audioChunks = [];

    mediaRecorder.ondataavailable = (ev) => {
      if (ev.data.size > 0) audioChunks.push(ev.data);
    };

    mediaRecorder.onstop = async () => {
      isRecording.value = false;
      const chunks = audioChunks;
      const wasCancelled = cancelled;
      cancelled = false;

      // 先释放麦克风，再上传识别
      if (mediaStream) {
        mediaStream.getTracks().forEach(t => t.stop());
        mediaStream = null;
      }

      if (wasCancelled || chunks.length === 0) {
        cleanup();
        resolvePending(null);
        return;
      }

      isRecognizing.value = true;
      try {
        const blob = new Blob(chunks, { type: mimeType });
        const buffer = await blob.arrayBuffer();
        const format = mimeType.includes('webm') ? 'webm' : 'ogg';
        const text = (await performVr(buffer, format)).trim();
        if (text && textRef) {
          textRef.value = textRef.value ? textRef.value + ' ' + text : text;
        } else if (!text) {
          showToast('未识别到语音内容', 'info');
        }
        resolvePending(text || null);
      } catch (e) {
        console.error('语音识别失败:', e);
        showToast('语音识别失败，请稍后重试', 'error');
        resolvePending(null);
      } finally {
        isRecognizing.value = false;
        cleanup();
      }
    };

    mediaRecorder.start();
    isRecording.value = true;

    // 等待权限期间用户已松手，立即停止
    if (stopRequested) {
      mediaRecorder.stop();
    }
    return true;
  };

  /**
   * 停止录音并等待识别结果
   * @returns 识别出的文本；取消、失败或识别为空时返回 null
   */
  const stopRecording = (): Promise<string | null> => {
    if (isRecognizing.value) return Promise.resolve(null);
    stopRequested = true;

    return new Promise((resolve) => {
      pendingResolve = resolve;
      if (mediaRecorder && mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
      } else if (!mediaRecorder) {
        // 尚未开始（等待权限中）或已结束
        pendingResolve = null;
        resolve(null);
      }
      // mediaRecorder.state 为 inactive 时 onstop 即将触发，等待其解析
    });
  };

  /** 取消录音，不进行识别 */
  const cancelRecording = () => {
    cancelled = true;
    stopRequested = true;
    if (mediaRecorder?.state === 'recording') {
      mediaRecorder.stop();
    }
  };

  const toggleRecording = async () => {
    if (isRecognizing.value) return;
    if (isRecording.value) {
      await stopRecording();
    } else {
      await startRecording();
    }
  };

  return {
    isRecording,
    isRecognizing,
    startRecording,
    stopRecording,
    cancelRecording,
    toggleRecording,
  };
}
