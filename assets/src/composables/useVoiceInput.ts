import { ref, onUnmounted, type Ref } from 'vue';
import { performVr } from '../utils/file';
import { useToast } from './useToast';

export function useVoiceInput(textRef: Ref<string>) {
  const { showToast } = useToast();

  const isRecording = ref(false);
  const isRecognizing = ref(false);

  let mediaStream: MediaStream | null = null;
  let mediaRecorder: MediaRecorder | null = null;
  let audioChunks: Blob[] = [];

  const cleanup = () => {
    if (mediaStream) {
      mediaStream.getTracks().forEach(t => t.stop());
      mediaStream = null;
    }
    mediaRecorder = null;
    audioChunks = [];
  };

  onUnmounted(() => {
    cleanup();
  });

  const toggleRecording = async () => {
    if (isRecognizing.value) return;

    // 正在录音 → 停止
    if (isRecording.value) {
      if (mediaRecorder?.state === 'recording') {
        mediaRecorder.stop();
      }
      return;
    }

    // 开始录音
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      showToast('请允许麦克风权限', 'error');
      cleanup();
      return;
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
      isRecognizing.value = true;
      try {
        const blob = new Blob(audioChunks, { type: mimeType });
        const buffer = await blob.arrayBuffer();
        const format = mimeType.includes('webm') ? 'webm' : 'ogg';
        const text = await performVr(buffer, format);
        if (text.trim()) {
          textRef.value = textRef.value ? textRef.value + ' ' + text.trim() : text.trim();
        }
      } catch (e) {
        console.error('语音识别失败:', e);
        showToast('语音识别失败，请稍后重试', 'error');
      } finally {
        isRecognizing.value = false;
        cleanup();
      }
    };

    mediaRecorder.start();
    isRecording.value = true;
  };

  return {
    isRecording,
    isRecognizing,
    toggleRecording,
  };
}
