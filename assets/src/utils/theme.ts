export type ThemeMode = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'theme_mode'
let mediaQuery: MediaQueryList | null = null
let currentMode: ThemeMode = 'system'

function getSystemDark(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

export function applyTheme(theme: ThemeMode): void {
  currentMode = theme
  const html = document.documentElement

  if (theme === 'system') {
    html.classList.toggle('dark', getSystemDark())
  } else {
    html.classList.toggle('dark', theme === 'dark')
  }
}

export function getStoredTheme(): ThemeMode {
  const val = localStorage.getItem(STORAGE_KEY)
  if (val === 'light' || val === 'dark' || val === 'system') return val
  return 'system'
}

export function storeTheme(theme: ThemeMode): void {
  localStorage.setItem(STORAGE_KEY, theme)
}

export function getCurrentTheme(): ThemeMode {
  return currentMode
}

export function initTheme(): void {
  const theme = getStoredTheme()
  currentMode = theme
  applyTheme(theme)

  mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
  mediaQuery.addEventListener('change', () => {
    if (currentMode === 'system') {
      applyTheme('system')
    }
  })
}
