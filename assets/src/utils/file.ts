import api from './api';

/**
 * 将音频文件读取为 ArrayBuffer
 */
export async function processAudio(file: File): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = reject;
    reader.readAsArrayBuffer(file);
  });
}

/**
 * 将其他文件读取为 ArrayBuffer
 */
export async function processFile(file: File): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = reject;
    reader.readAsArrayBuffer(file);
  });
}

/**
 * 前端读取纯文本文件内容
 */
export async function readTextFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsText(file);
  });
}

/**
 * 调用后端语音识别接口 /api/vr
 */
export async function performVr(data: ArrayBuffer, format: string): Promise<string> {
  const response = await api.post('/api/vr', data, {
    headers: {
      'Content-Type': 'application/octet-stream',
      'format': format,
    },
  });
  return response.data as string;
}

/**
 * 调用后端文档转换接口 /api/markitdown
 */
export async function performMarkitdown(data: ArrayBuffer, format: string): Promise<string> {
  const response = await api.post('/api/markitdown', data, {
    headers: {
      'Content-Type': 'application/octet-stream',
      'format': format,
    },
  });
  return response.data as string;
}
