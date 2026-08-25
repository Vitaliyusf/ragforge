/**
 * Chat route. The shell lives in the workspace layout and ChatContext reads
 * the active chat id straight from the pathname, so this page renders nothing
 * — which is precisely what keeps the shell mounted across chat switches.
 */
export default function ChatPage() {
  return null
}
