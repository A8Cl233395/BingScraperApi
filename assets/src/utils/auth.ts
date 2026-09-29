/**
 * 登录态（uid/session/token）的读取与清理。
 * axios 请求由 api.ts 拦截器统一附带认证头；SSE 走 fetchEventSource 时
 * 不经过 axios，需手动调用 getAuthHeaders()。
 */

/** 读取认证请求头（未登录项为空字符串） */
export function getAuthHeaders(): Record<string, string> {
  return {
    uid: localStorage.getItem('uid') || '',
    session: localStorage.getItem('session') || '',
    token: localStorage.getItem('token') || '',
  };
}

/** 清除本地登录态 */
export function clearAuth(): void {
  localStorage.removeItem('uid');
  localStorage.removeItem('session');
  localStorage.removeItem('token');
}

/** 跳转登录页（uid 参数缺省时从 localStorage 读取，登录页用于回填） */
export function redirectToLogin(uid?: string): void {
  const savedUid = uid ?? localStorage.getItem('uid') ?? '';
  window.location.href = `/login${savedUid ? `#uid=${savedUid}` : ''}`;
}
