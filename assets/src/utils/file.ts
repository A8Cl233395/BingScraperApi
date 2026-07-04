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
 * 自动检测编码并读取文本文件
 * 取前 4KB 用 jschardet 猜测编码，置信度 > 0.9 则用该编码读取全文
 * 置信度 <= 0.9 返回 null
 */
export async function detectAndReadTextFile(file: File): Promise<string | null> {
  const jschardet = await import('jschardet');
  const header = file.slice(0, 4096);
  const headerBuf = await header.arrayBuffer();
  const bytes = new Uint8Array(headerBuf);
  const sample = Array.from(bytes, b => String.fromCharCode(b)).join('');
  const detected = jschardet.detect(sample);

  if (!detected || !detected.encoding || (detected.confidence ?? 0) <= 0.9) {
    return null;
  }

  const fullBuf = await file.arrayBuffer();
  const decoder = new TextDecoder(detected.encoding);
  return decoder.decode(fullBuf);
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
