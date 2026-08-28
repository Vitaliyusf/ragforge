/**
 * Dashboard route. Historically this rendered its own TabbedPageLayout, so
 * arriving here tore down the workspace shell and built a second one. It now
 * lives under the workspace layout and contributes no markup, exactly like
 * `/` and `/chat/[chatId]`.
 */
export default function Dashboard() {
  return null
}
