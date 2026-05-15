import { ref } from 'vue';
import { processImage } from '../utils/image';
import { performOcr } from '../utils/image';

/**
 * 图片编辑 composable
 * 封装 ChatInput 和 MessageBubble 编辑模式中重复的图片处理逻辑：
 * - 添加图片文件（含 HEIC/HEIF 支持）
 * - 文件上传、粘贴、拖放处理
 * - OCR 文字识别
 * - 删除图片
 */
export function useImageEditor(options?: { maxImages?: number }) {
  const maxImages = options?.maxImages ?? 10;

  const images = ref<string[]>([]);
  const isProcessingImage = ref(false);
  const isOcrProcessing = ref(false);
  const fileInputRef = ref<HTMLInputElement | null>(null);

  const addFiles = async (files: File[]) => {
    isProcessingImage.value = true;
    try {
      for (const file of files) {
        if (images.value.length >= maxImages) break;
        const isImage = file.type.startsWith('image/') ||
          file.name.toLowerCase().endsWith('.heic') ||
          file.name.toLowerCase().endsWith('.heif');

        if (isImage) {
          try {
            const base64 = await processImage(file);
            images.value.push(base64);
          } catch (error) {
            console.error('Failed to process image:', error);
            alert('图片处理失败，请稍后重试');
          }
        }
      }
    } finally {
      isProcessingImage.value = false;
    }
  };

  const handleFileUpload = async (e: Event) => {
    const files = (e.target as HTMLInputElement).files;
    if (files) {
      await addFiles(Array.from(files));
    }
  };

  const handlePaste = async (e: ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (items) {
      const files = [];
      for (let i = 0; i < items.length; i++) {
        if (items[i].type.indexOf('image') !== -1) {
          const file = items[i].getAsFile();
          if (file) files.push(file);
        }
      }
      await addFiles(files);
    }
  };

  const handleDrop = async (e: DragEvent) => {
    e.preventDefault();
    const files = e.dataTransfer?.files;
    if (files) {
      await addFiles(Array.from(files));
    }
  };

  const removeImage = (index: number) => {
    images.value.splice(index, 1);
  };

  /**
   * 对指定图片执行 OCR，识别结果插入到 textRef 前面
   * @param index 图片索引
   * @param textRef 文本 ref（识别结果会合并到此 ref）
   */
  const handleOcr = async (index: number, textRef: { value: string }) => {
    if (isOcrProcessing.value) return;
    isOcrProcessing.value = true;
    try {
      const ocrText = await performOcr(images.value[index]);
      if (textRef.value.trim()) {
        textRef.value = ocrText + '\n\n---\n\n' + textRef.value;
      } else {
        textRef.value = ocrText;
      }
      images.value.splice(index, 1);
    } catch (e) {
      console.error('OCR failed:', e);
      alert('文字识别失败，请稍后重试');
    } finally {
      isOcrProcessing.value = false;
    }
  };

  const clearImages = () => {
    images.value = [];
  };

  return {
    images,
    isProcessingImage,
    isOcrProcessing,
    fileInputRef,
    addFiles,
    handleFileUpload,
    handlePaste,
    handleDrop,
    removeImage,
    handleOcr,
    clearImages,
  };
}
