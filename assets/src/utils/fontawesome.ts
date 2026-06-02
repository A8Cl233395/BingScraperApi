import { library } from '@fortawesome/fontawesome-svg-core'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
import type { App } from 'vue'

import {
  faBrain,
  faWrench,
  faChevronRight,
  faChevronLeft,
  faChevronDown,
  faChevronUp,
  faCheck,
  faSpinner,
  faXmark,
  faPaperPlane,
  faAlignLeft,
  faBars,
  faPlus,
  faTrashCan,
  faMagnifyingGlassPlus,
  faMagnifyingGlassMinus,
  faExpand,
  faDownload,
  faICursor,
  faRotateRight,
  faTriangleExclamation,
  faCircleInfo,
  faFileLines,
  faStop,
  faUserGear,
  faBolt,
  faThumbtack
} from '@fortawesome/free-solid-svg-icons'

import {
  faCopy,
  faPenToSquare,
  faImage
} from '@fortawesome/free-regular-svg-icons'

library.add(
  faBrain,
  faWrench,
  faChevronRight,
  faChevronLeft,
  faChevronDown,
  faChevronUp,
  faCheck,
  faSpinner,
  faXmark,
  faPaperPlane,
  faAlignLeft,
  faBars,
  faPlus,
  faTrashCan,
  faMagnifyingGlassPlus,
  faMagnifyingGlassMinus,
  faExpand,
  faDownload,
  faICursor,
  faRotateRight,
  faTriangleExclamation,
  faCircleInfo,
  faFileLines,
  faStop,
  faUserGear,
  faBolt,
  faThumbtack,
  faCopy,
  faPenToSquare,
  faImage
)

export function registerFontAwesome(app: App) {
  app.component('FontAwesomeIcon', FontAwesomeIcon)
}
