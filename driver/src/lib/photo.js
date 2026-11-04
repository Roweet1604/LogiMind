// Phone photos are often larger than the server's 3 MB limit. Re-encode to JPEG, at most 1600 px on the long
// side, before upload. Re-encoding through a canvas also drops EXIF data (which can contain GPS position).
// If the browser cannot do this (or in tests), the original file is sent and the server's limits apply.
export const MAX_SIDE = 1600

export async function shrinkImage(file, { maxSide = MAX_SIDE, quality = 0.82 } = {}) {
  try {
    if (typeof createImageBitmap !== 'function' || typeof document === 'undefined') return file
    const bmp = await createImageBitmap(file)
    const scale = Math.min(1, maxSide / Math.max(bmp.width, bmp.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(bmp.width * scale)
    canvas.height = Math.round(bmp.height * scale)
    const ctx = canvas.getContext('2d')
    if (!ctx) return file
    ctx.drawImage(bmp, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality))
    return blob ? new File([blob], 'photo.jpg', { type: 'image/jpeg' }) : file
  } catch {
    return file
  }
}
