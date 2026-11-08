import { ref, computed, watch, reactive } from 'vue';
import { processImage, performOcr } from '../utils/image';
import { readAsArrayBuffer, performVr, performMarkitdown, detectAndReadTextFile } from '../utils/file';
import { state } from '../store';
import { useToast } from './useToast';

export interface UploadedFileItem {
  id: string;
  name: string;
  text: string;
  status?: 'converting' | 'ready';
}

const AUDIO_EXTENSIONS = ['mp3', 'wav', 'ogg', 'aac', 'flac'];
const MARKITDOWN_EXTENSIONS = ['pdf', 'docx', 'xlsx', 'pptx'];
const MAX_FILE_SIZE = 20 * 1024 * 1024;

function getExtension(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot >= 0 ? name.slice(dot + 1).toLowerCase() : '';
}

function isAudioFile(name: string): boolean {
  return AUDIO_EXTENSIONS.includes(getExtension(name));
}

function isBadRequest(e: unknown): boolean {
  if (e && typeof e === 'object' && 'response' in e) {
    return (e as { response?: { status?: number } }).response?.status === 400;
  }
  return false;
}

function createFileId(prefix = 'file'): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * 文件与图片编辑 composable
 * 封装 ChatInput 和 MessageBubble 编辑模式中的附件处理逻辑：
 * - 图片文件处理（含 HEIC/HEIF 支持）及手动 OCR 转文件卡片
 * - 音频/文档/文本文件上传后自动转换为文本并生成文件卡片
 * - 文件卡片拖拽排序、预览编辑、删除
 */
export function useImageEditor(options?: { maxImages?: number; maxFiles?: number; trackDraft?: boolean }) {
  const maxImages = options?.maxImages ?? 10;
  const maxFiles = options?.maxFiles ?? 10;
  const trackDraft = options?.trackDraft ?? false;
  const { showToast } = useToast();

  const images = ref<string[]>([]);
  const files = ref<UploadedFileItem[]>([]);
  const isProcessingImage = ref(false);
  const isOcrProcessing = ref(false);
  const isConverting = computed(() => files.value.some(f => f.status === 'converting'));
  const fileInputRef = ref<HTMLInputElement | null>(null);

  if (trackDraft) {
    watch(images, (newVal) => {
      state.hasDraftImages = newVal.length > 0;
    }, { deep: true });
    watch(files, (newVal) => {
      state.hasDraftFiles = newVal.length > 0;
    }, { deep: true });
  }

  /**
   * 后台转换单个非图片文件，转换完成后原地更新为 ready 状态
   */
  const convertSingleFile = async (file: File, fileItem: UploadedFileItem) => {
    const removeSelf = () => {
      const idx = files.value.findIndex(f => f.id === fileItem.id);
      if (idx !== -1) files.value.splice(idx, 1);
    };

    try {
      let extractedText = '';
      if (isAudioFile(file.name)) {
        const data = await readAsArrayBuffer(file);
        extractedText = await performVr(data, getExtension(file.name));
      } else {
        const ext = getExtension(file.name);
        if (MARKITDOWN_EXTENSIONS.includes(ext)) {
          const data = await readAsArrayBuffer(file);
          extractedText = await performMarkitdown(data, ext);
        } else {
          const text = await detectAndReadTextFile(file);
          if (text === null) {
            removeSelf();
            showToast(`无法解析的文件: ${file.name}`, 'error');
            return;
          }
          extractedText = text;
        }
      }

      // 若转换期间已被用户手动删除，则直接丢弃结果
      if (!files.value.some(f => f.id === fileItem.id)) return;

      if (!extractedText || !extractedText.trim()) {
        removeSelf();
        showToast(`文件内容为空或未识别到文字: ${file.name}`, 'info');
        return;
      }

      fileItem.text = extractedText;
      fileItem.status = 'ready';
    } catch (e) {
      console.error('File conversion failed:', e);
      removeSelf();
      if (isAudioFile(file.name)) {
        showToast(isBadRequest(e) ? '文件错误，无法识别' : '语音识别失败，请稍后重试', 'error');
      } else {
        showToast(isBadRequest(e) ? '文件错误，无法转换' : '文件转换失败，请稍后重试', 'error');
      }
    }
  };

  const addFiles = async (inputFiles: File[]) => {
    try {
      const pendingConversions: Promise<void>[] = [];

      for (const file of inputFiles) {
        if (file.size > MAX_FILE_SIZE) {
          showToast(`文件过大（超过20MB）: ${file.name}`, 'error');
          continue;
        }
        const isImage = file.type.startsWith('image/') ||
          file.name.toLowerCase().endsWith('.heic') ||
          file.name.toLowerCase().endsWith('.heif');

        if (isImage) {
          if (images.value.length >= maxImages) {
            showToast(`最多只能包含${maxImages}张图片`, 'error');
            continue;
          }
          isProcessingImage.value = true;
          try {
            const base64 = await processImage(file);
            images.value.push(base64);
          } catch (error) {
            console.error('Failed to process image:', error);
            showToast('图片处理失败，请稍后重试', 'error');
          } finally {
            isProcessingImage.value = false;
          }
        } else {
          if (files.value.length >= maxFiles) {
            showToast(`最多只能包含${maxFiles}个文件`, 'error');
            continue;
          }
          const fileItem = reactive<UploadedFileItem>({
            id: createFileId('file'),
            name: file.name || '未命名文件',
            text: '',
            status: 'converting',
          });
          files.value.push(fileItem);
          pendingConversions.push(convertSingleFile(file, fileItem));
        }
      }

      if (pendingConversions.length > 0) {
        await Promise.all(pendingConversions);
      }
    } catch (error) {
      isProcessingImage.value = false;
      throw error;
    }
  };

  const handleFileUpload = async (e: Event) => {
    const input = e.target as HTMLInputElement;
    const selected = input.files;
    if (selected && selected.length > 0) {
      const fileList = Array.from(selected);
      input.value = '';
      await addFiles(fileList);
    }
  };

  const handlePaste = async (e: ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (items) {
      const pastedFiles: File[] = [];
      for (let i = 0; i < items.length; i++) {
        if (items[i].kind === 'file') {
          const file = items[i].getAsFile();
          if (file) pastedFiles.push(file);
        }
      }
      if (pastedFiles.length > 0) {
        await addFiles(pastedFiles);
      }
    }
  };

  const handleDrop = async (e: DragEvent) => {
    e.preventDefault();
    // 忽略内部文件卡片拖拽排序事件
    if (e.dataTransfer?.types.includes('application/x-webchat-file')) {
      return;
    }
    const dropped = e.dataTransfer?.files;
    if (dropped && dropped.length > 0) {
      await addFiles(Array.from(dropped));
    }
  };

  const removeImage = (index: number) => {
    images.value.splice(index, 1);
  };

  const removeFile = (index: number) => {
    files.value.splice(index, 1);
  };

  const reorderFiles = (fromIndex: number, toIndex: number) => {
    if (
      fromIndex === toIndex ||
      fromIndex < 0 ||
      toIndex < 0 ||
      fromIndex >= files.value.length ||
      toIndex >= files.value.length
    ) {
      return;
    }
    const [moved] = files.value.splice(fromIndex, 1);
    files.value.splice(toIndex, 0, moved);
  };

  const updateFile = (index: number, newText: string, newName?: string) => {
    const target = files.value[index];
    if (!target) return;
    target.text = newText;
    if (newName) target.name = newName;
  };

  /**
   * 对指定图片执行 OCR，识别结果作为文件卡片加入 files
   */
  const handleOcr = async (index: number) => {
    if (isOcrProcessing.value) return;
    if (files.value.length >= maxFiles) {
      showToast(`最多只能包含${maxFiles}个文件`, 'error');
      return;
    }
    isOcrProcessing.value = true;
    try {
      const ocrText = await performOcr(images.value[index]);
      if (!ocrText || !ocrText.trim()) {
        showToast('未识别到文字', 'info');
        return;
      }
      images.value.splice(index, 1);
      files.value.push({
        id: createFileId('ocr'),
        name: `OCR_${files.value.length + 1}.jpg`,
        text: ocrText,
        status: 'ready',
      });
    } catch (e) {
      console.error('OCR failed:', e);
      showToast(isBadRequest(e) ? '文件错误，无法识别' : '文字识别失败，请稍后重试', 'error');
    } finally {
      isOcrProcessing.value = false;
    }
  };

  const clearImages = () => {
    images.value = [];
    files.value = [];
  };

  return {
    images,
    files,
    isProcessingImage,
    isOcrProcessing,
    isConverting,
    fileInputRef,
    handleFileUpload,
    handlePaste,
    handleDrop,
    removeImage,
    removeFile,
    reorderFiles,
    updateFile,
    handleOcr,
    clearImages,
  };
}
