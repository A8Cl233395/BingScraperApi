// 全部图标在此集中 import 并注册为 PascalCase 全局组件；新增图标必须加到这里。
// 注意：
// - 动态切图标用 <component :is="'组件名'"> 字符串形式；
// - 加载动画用 Loader2 + animate-spin（lucide 无内置 spin）；
// - marked 生成的 innerHTML 里无法使用 Vue 组件，markdown.ts 中的图标是内联 SVG 常量，
//   修改复制/图表按钮图标时需同步更新那边的 path 数据。
import type { App } from 'vue'

import {
  AlignLeft,
  ArrowDown,
  Brain,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Clock,
  Copy,
  Download,
  Expand,
  Eye,
  File,
  FileInput,
  FileText,
  Folder,
  Gauge,
  Info,
  KeyRound,
  Laptop,
  Loader2,
  LogOut,
  Menu,
  Mic,
  Monitor,
  Moon,
  Music,
  PawPrint,
  Pin,
  Plus,
  RotateCw,
  Search,
  Send,
  Settings,
  Square,
  SquarePen,
  Sun,
  TextCursor,
  Trash2,
  TriangleAlert,
  User,
  UserCog,
  Wrench,
  X,
  Zap,
  ZoomIn,
  ZoomOut
} from '@lucide/vue'

export function registerLucide(app: App) {
  app.component('AlignLeft', AlignLeft)
  app.component('ArrowDown', ArrowDown)
  app.component('Brain', Brain)
  app.component('Check', Check)
  app.component('ChevronDown', ChevronDown)
  app.component('ChevronLeft', ChevronLeft)
  app.component('ChevronRight', ChevronRight)
  app.component('ChevronUp', ChevronUp)
  app.component('Clock', Clock)
  app.component('Copy', Copy)
  app.component('Download', Download)
  app.component('Expand', Expand)
  app.component('Eye', Eye)
  app.component('File', File)
  app.component('FileInput', FileInput)
  app.component('FileText', FileText)
  app.component('Folder', Folder)
  app.component('Gauge', Gauge)
  app.component('Info', Info)
  app.component('KeyRound', KeyRound)
  app.component('Laptop', Laptop)
  app.component('Loader2', Loader2)
  app.component('LogOut', LogOut)
  app.component('Menu', Menu)
  app.component('Mic', Mic)
  app.component('Monitor', Monitor)
  app.component('Moon', Moon)
  app.component('Music', Music)
  app.component('PawPrint', PawPrint)
  app.component('Pin', Pin)
  app.component('Plus', Plus)
  app.component('RotateCw', RotateCw)
  app.component('Search', Search)
  app.component('Send', Send)
  app.component('Settings', Settings)
  app.component('Square', Square)
  app.component('SquarePen', SquarePen)
  app.component('Sun', Sun)
  app.component('TextCursor', TextCursor)
  app.component('Trash2', Trash2)
  app.component('TriangleAlert', TriangleAlert)
  app.component('User', User)
  app.component('UserCog', UserCog)
  app.component('Wrench', Wrench)
  app.component('X', X)
  app.component('Zap', Zap)
  app.component('ZoomIn', ZoomIn)
  app.component('ZoomOut', ZoomOut)
}