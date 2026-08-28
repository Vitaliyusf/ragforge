/**
 * Workspace navigation must not blank the application.
 *
 * Without a boundary here, a transition between workspace URLs falls through
 * to the root `loading.jsx`, whose full-screen spinner replaces the entire
 * shell. The pages in this group render nothing — the shell is in the layout —
 * so the correct fallback for their content is nothing at all.
 */
export default function WorkspaceLoading() {
  return null
}
