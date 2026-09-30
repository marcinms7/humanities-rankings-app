import { useEffect } from 'react'

const drafts = new Set<symbol>()

function warnBeforeUnload(event: BeforeUnloadEvent) {
  if (!drafts.size) return
  event.preventDefault()
  event.returnValue = ''
}

export function confirmDiscardUnsavedChanges() {
  return !drafts.size || window.confirm('Leave this page without saving your writing to your account?')
}

export function useUnsavedChanges(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return
    const draft = Symbol('study draft')
    drafts.add(draft)
    if (drafts.size === 1) window.addEventListener('beforeunload', warnBeforeUnload)
    return () => {
      drafts.delete(draft)
      if (!drafts.size) window.removeEventListener('beforeunload', warnBeforeUnload)
    }
  }, [dirty])
}
