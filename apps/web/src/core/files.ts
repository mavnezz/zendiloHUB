/** A file shown as a chip (`FileChips.vue`): sent already, or picked and on its way. */
export interface FileChip {
  id: string
  filename: string
  content_type: string
  size: number
  uploading?: boolean
}

/** Types the browser shows instead of downloading them (the server sends only these inline). */
export const IMAGE_TYPES: readonly string[] = ['image/png', 'image/jpeg', 'image/gif', 'image/webp']
