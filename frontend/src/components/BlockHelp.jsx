import { useEffect, useRef, useState } from 'react'
import { getBlockHelp } from '../lib/blockHelp.mjs'

const OPEN_EVENT = 'block-help-open'

export default function BlockHelp({ id }) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)
  const entry = getBlockHelp(id)
  const body = entry?.body ?? 'No help available for this block.'

  useEffect(() => {
    if (!open) return undefined
    const onDoc = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false)
    }
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false)
    }
    const onOther = (e) => {
      if (e.detail?.id !== id) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    window.addEventListener(OPEN_EVENT, onOther)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
      window.removeEventListener(OPEN_EVENT, onOther)
    }
  }, [open, id])

  function toggle() {
    const next = !open
    if (next) {
      window.dispatchEvent(new CustomEvent(OPEN_EVENT, { detail: { id } }))
    }
    setOpen(next)
  }

  return (
    <span className="block-help" ref={rootRef}>
      <button
        type="button"
        className="block-help-btn"
        aria-label="About this block"
        aria-expanded={open}
        aria-controls={open ? `block-help-${id}` : undefined}
        onClick={toggle}
      >
        ?
      </button>
      {open && (
        <div
          id={`block-help-${id}`}
          className="block-help-popover"
          role="dialog"
          aria-label="Block help"
        >
          <p>{body}</p>
        </div>
      )}
    </span>
  )
}
