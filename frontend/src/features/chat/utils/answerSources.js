/**
 * One definition of what a "source" is, shared by the chips under an answer and
 * by the compact quality line above them.
 *
 * The user-facing vocabulary is deliberately narrow:
 *
 *   source = a unique document
 *   chunk  = a retrieved passage from one
 *
 * Several passages from the same file are one source to a reader, so both
 * surfaces group through `groupSourcesByDocument` rather than counting the raw
 * retrieval array. Chunk counts belong to the Developer Inspector.
 *
 * Every function is pure so the presentation can be tested without a DOM.
 */

/** The document a retrieved passage belongs to, as a person would name it. */
export function sourceName(source, index) {
  return source?.source_name || source?.source || source?.filename || source?.title || `Source ${index + 1}`
}

function excerptOf(source) {
  const text = source?.text_preview || source?.text
  return typeof text === 'string' && text.trim() ? text.trim() : null
}

/**
 * Group retrieved passages by the document they came from, preserving the
 * order retrieval returned them in. Passages with neither text nor a page
 * carry nothing a reader can use, so they are dropped from the group's
 * `passages` while still establishing the document as a source.
 */
export function groupSourcesByDocument(sources) {
  if (!Array.isArray(sources)) return []

  const groups = []
  const byName = new Map()

  for (const [index, source] of sources.entries()) {
    const name = sourceName(source, index)
    let group = byName.get(name)
    if (!group) {
      group = { name, passages: [] }
      byName.set(name, group)
      groups.push(group)
    }
    const excerpt = excerptOf(source)
    const page = source?.page ?? null
    if (excerpt || page != null) group.passages.push({ page, excerpt })
  }

  return groups
}

/** How many distinct documents backed this answer. */
export function countDocumentSources(sources) {
  return groupSourcesByDocument(sources).length
}

/** How many passages were retrieved, preferring the server's own count. */
export function countChunks(sources, retrievalSummary) {
  if (Number.isFinite(retrievalSummary?.chunk_count)) return retrievalSummary.chunk_count
  return Array.isArray(sources) ? sources.length : 0
}
