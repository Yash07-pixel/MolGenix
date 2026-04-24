import { AnimatePresence, motion } from 'framer-motion'

function Toast({ toasts, dismissToast }) {
  const MotionDiv = motion.div

  return (
    <div className="toast-container" aria-live="polite" aria-atomic="true">
      <AnimatePresence>
        {toasts.map((toast) => (
          <MotionDiv
            key={toast.id}
            className={`toast toast--${toast.type}`}
            initial={{ x: 20, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 20, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <button
              type="button"
              className="toast__dismiss"
              onClick={() => dismissToast(toast.id)}
              aria-label="Dismiss notification"
            >
              x
            </button>
            <p>{toast.message}</p>
          </MotionDiv>
        ))}
      </AnimatePresence>
    </div>
  )
}

export default Toast
