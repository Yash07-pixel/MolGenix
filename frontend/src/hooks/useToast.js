import { createContext, createElement, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import Toast from '../components/Toast'

const ToastContext = createContext(null)

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const dismissToast = useCallback((id) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const showToast = useCallback((message, type = 'info') => {
    const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`
    setToasts((current) => [...current, { id, message, type }])
    return id
  }, [])

  useEffect(() => {
    if (!toasts.length) {
      return undefined
    }

    const timers = toasts.map((toast) =>
      window.setTimeout(() => {
        dismissToast(toast.id)
      }, 4000),
    )

    return () => {
      timers.forEach((timer) => window.clearTimeout(timer))
    }
  }, [dismissToast, toasts])

  const value = useMemo(
    () => ({
      showToast,
      dismissToast,
    }),
    [dismissToast, showToast],
  )

  return createElement(
    ToastContext.Provider,
    { value },
    children,
    createElement(Toast, { toasts, dismissToast }),
  )
}

export function useToast() {
  const context = useContext(ToastContext)

  if (!context) {
    throw new Error('useToast must be used within a ToastProvider')
  }

  return context
}
