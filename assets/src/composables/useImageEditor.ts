import { ref, watch } from 'vue';
import { processImage, performOcr } from '../utils/image';
import { processAudio, processFile, performVr, performMarkitdown, detectAndReadTextFile } from '../utils/file';
import { state } from '../store';
import { useToast } from './useToast';

interface FileItem {
  type: 'audio' | 'file';
  data: ArrayBuffer;
  textContent: string;
  originalName: string;
  format: string;
  supported: boolean;
  isTextFile: boolean;
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

/**
 * 文件编辑 composable
 * 封装 ChatInput 和 MessageBubble 编辑模式中的文件处理逻辑：
 * - 图片文件处理（含 HEIC/HEIF 支持）
 * - 音频文件处理（常见音频格式）
 * - 其他文件处理（文档、文本等）
 * - OCR/VR/Markitdown 文字转换
 * - 文件上传、粘贴、拖放处理
 */
export function useImageEditor(options?: { maxImages?: number; trackDraft?: boolean }) {
  const maxImages = options?.maxImages ?? 10;
  const trackDraft = options?.trackDraft ?? false;
  const { showToast } = useToast();

  const images = ref<string[]>([]);
  const audioFiles = ref<FileItem[]>([]);
  const otherFiles = ref<FileItem[]>([]);
  const isProcessingImage = ref(false);
  const isProcessingAudio = ref(false);
  const isProcessingFile = ref(false);
  const isOcrProcessing = ref(false);
  const isConverting = ref(false);
  const fileInputRef = ref<HTMLInputElement | null>(null);

  if (trackDraft) {
    watch(images, (newVal) => {
      state.hasDraftImages = newVal.length > 0;
    }, { deep: true });
    watch([audioFiles, otherFiles], ([a, o]) => {
      state.hasDraftFiles = a.length + o.length > 0;
    }, { deep: true });
  }

  const addFiles = async (files: File[]) => {
    try {
      for (const file of files) {
        if (file.size > MAX_FILE_SIZE) {
          showToast(`文件过大（超过20MB）: ${file.name}`, 'error');
          continue;
        }
        const isImage = file.type.startsWith('image/') ||
          file.name.toLowerCase().endsWith('.heic') ||
          file.name.toLowerCase().endsWith('.heif');

        if (isImage) {
          if (images.value.length >= maxImages) continue;
          isProcessingImage.value = true;
          try {
            const base64 = await processImage(file);
            images.value.push(base64);
          } catch (error) {
            console.error('Failed to process image:', error);
            alert('图片处理失败，请稍后重试');
          } finally {
            isProcessingImage.value = false;
          }
        } else if (isAudioFile(file.name)) {
          isProcessingAudio.value = true;
          try {
            const data = await processAudio(file);
            audioFiles.value.push({
              type: 'audio',
              data,
              textContent: '',
              originalName: file.name,
              format: getExtension(file.name),
              supported: true,
              isTextFile: false,
            });
          } catch (error) {
            console.error('Failed to process audio:', error);
            alert('音频处理失败，请稍后重试');
          } finally {
            isProcessingAudio.value = false;
          }
        } else {
          const ext = getExtension(file.name);
          isProcessingFile.value = true;
          try {
            if (MARKITDOWN_EXTENSIONS.includes(ext)) {
              const data = await processFile(file);
              otherFiles.value.push({
                type: 'file',
                data,
                textContent: '',
                originalName: file.name,
                format: ext,
                supported: true,
                isTextFile: false,
              });
            } else {
              const text = await detectAndReadTextFile(file);
              if (text !== null) {
                otherFiles.value.push({
                  type: 'file',
                  data: new ArrayBuffer(0),
                  textContent: text,
                  originalName: file.name,
                  format: ext,
                  supported: true,
                  isTextFile: true,
                });
              } else {
                showToast(`无法解析的文件: ${file.name}`, 'error');
              }
            }
          } catch (error) {
            console.error('Failed to process file:', error);
            showToast('文件处理失败，请稍后重试', 'error');
          } finally {
            isProcessingFile.value = false;
          }
        }
      }
    } catch (error) {
      // 外层异常兜底，确保所有标志位重置
      isProcessingImage.value = false;
      isProcessingAudio.value = false;
      isProcessingFile.value = false;
      throw error;
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

  const removeAudio = (index: number) => {
    audioFiles.value.splice(index, 1);
  };

  const removeOtherFile = (index: number) => {
    otherFiles.value.splice(index, 1);
  };

  const insertText = (text: string, textRef: { value: string }) => {
    if (textRef.value.trim()) {
      textRef.value = text + '\n\n' + textRef.value;
    } else {
      textRef.value = text;
    }
  };

  /**
   * 对指定图片执行 OCR，识别结果插入到 textRef 前面
   */
  const handleOcr = async (index: number, textRef: { value: string }) => {
    if (isOcrProcessing.value) return;
    isOcrProcessing.value = true;
    try {
      const ocrText = await performOcr(images.value[index]);
      insertText(`<source format="jpg">\n${ocrText}\n</source>`, textRef);
      images.value.splice(index, 1);
    } catch (e) {
      console.error('OCR failed:', e);
      showToast(isBadRequest(e) ? '文件错误，无法识别' : '文字识别失败，请稍后重试', 'error');
    } finally {
      isOcrProcessing.value = false;
    }
  };

  /**
   * 对指定音频文件执行语音识别，转换结果插入到 textRef 前面
   */
  const handleAudioConvert = async (index: number, textRef: { value: string }) => {
    if (isConverting.value) return;
    isConverting.value = true;
    const item = audioFiles.value[index];
    try {
      const text = await performVr(item.data, item.format);
      insertText(`<source format="${item.format}">\n${text}\n</source>`, textRef);
      audioFiles.value.splice(index, 1);
    } catch (e) {
      console.error('Audio recognition failed:', e);
      showToast(isBadRequest(e) ? '文件错误，无法识别' : '语音识别失败，请稍后重试', 'error');
    } finally {
      isConverting.value = false;
    }
  };

  /**
   * 对指定文件执行文字提取，结果插入到 textRef 前面
   */
  const handleFileConvert = async (index: number, textRef: { value: string }) => {
    if (isConverting.value) return;
    isConverting.value = true;
    const item = otherFiles.value[index];
    try {
      let text: string;
      if (item.isTextFile) {
        text = item.textContent;
      } else {
        text = await performMarkitdown(item.data, item.format);
      }
      insertText(`<source filename="${item.originalName}">\n${text}\n</source>`, textRef);
      otherFiles.value.splice(index, 1);
    } catch (e) {
      console.error('File conversion failed:', e);
      showToast(isBadRequest(e) ? '文件错误，无法转换' : '文件转换失败，请稍后重试', 'error');
    } finally {
      isConverting.value = false;
    }
  };

  const clearImages = () => {
    images.value = [];
    audioFiles.value = [];
    otherFiles.value = [];
  };

  return {
    images,
    audioFiles,
    otherFiles,
    isProcessingImage,
    isProcessingAudio,
    isProcessingFile,
    isOcrProcessing,
    isConverting,
    fileInputRef,
    addFiles,
    handleFileUpload,
    handlePaste,
    handleDrop,
    removeImage,
    removeAudio,
    removeOtherFile,
    handleOcr,
    handleAudioConvert,
    handleFileConvert,
    clearImages,
  };
}
