export const isMobileDevice = (): boolean => {
  const ua = navigator.userAgent;
  return /Mobile|Android|iPhone|iPad/i.test(ua);
};
