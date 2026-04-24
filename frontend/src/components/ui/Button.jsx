import Spinner from './Spinner'
import './ui.css'

function Button({
  children,
  className = '',
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  type = 'button',
  ...props
}) {
  return (
    <button
      type={type}
      className={`mgx-button mgx-button--${variant} mgx-button--${size} ${className}`.trim()}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <Spinner size={16} /> : null}
      <span>{children}</span>
    </button>
  )
}

export default Button
