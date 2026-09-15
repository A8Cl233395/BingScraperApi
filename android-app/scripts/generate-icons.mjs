import sharp from 'sharp'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const root = join(here, '..')
const resDir = join(root, 'android', 'app', 'src', 'main', 'res')
const iconPath = join(root, '..', 'assets', 'public', 'icon.svg')

const BG = '#E8F1FA'
const svgSource = readFileSync(iconPath, 'utf8')
const inner = svgSource.replace(/^[\s\S]*?<svg[^>]*>/, '').replace(/<\/svg>\s*$/, '')

function wrap({ size, scale, bg }) {
  const iconSize = size * scale
  const offset = (size - iconSize) / 2
  let background = ''
  if (bg === 'rect') {
    background = `<rect width="${size}" height="${size}" fill="${BG}"/>`
  } else if (bg === 'circle') {
    background = `<circle cx="${size / 2}" cy="${size / 2}" r="${size / 2}" fill="${BG}"/>`
  }
  return Buffer.from(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">` +
      background +
      `<svg x="${offset}" y="${offset}" width="${iconSize}" height="${iconSize}" viewBox="0 0 32 32">${inner}</svg>` +
      `</svg>`
  )
}

async function render(svgBuffer, size) {
  return sharp(svgBuffer, { density: 288 }).resize(size, size, { fit: 'contain' }).png().toBuffer()
}

const mipmaps = [
  ['mipmap-mdpi', 48, 108],
  ['mipmap-hdpi', 72, 162],
  ['mipmap-xhdpi', 96, 216],
  ['mipmap-xxhdpi', 144, 324],
  ['mipmap-xxxhdpi', 192, 432],
]

for (const [dir, legacySize, foregroundSize] of mipmaps) {
  const out = join(resDir, dir)
  mkdirSync(out, { recursive: true })

  const legacy = await render(wrap({ size: legacySize, scale: 0.72, bg: 'rect' }), legacySize)
  writeFileSync(join(out, 'ic_launcher.png'), legacy)

  const round = await render(wrap({ size: legacySize, scale: 0.58, bg: 'circle' }), legacySize)
  writeFileSync(join(out, 'ic_launcher_round.png'), round)

  const foreground = await render(wrap({ size: foregroundSize, scale: 0.62, bg: 'none' }), foregroundSize)
  writeFileSync(join(out, 'ic_launcher_foreground.png'), foreground)
}

writeFileSync(
  join(resDir, 'values', 'ic_launcher_background.xml'),
  `<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="ic_launcher_background">${BG}</color>\n</resources>\n`
)

// 系统启动图图标为手写矢量图 res/drawable/splash_icon.xml（等价 icon.svg），随 icon.svg 变更手动同步

console.log('应用图标已生成')
