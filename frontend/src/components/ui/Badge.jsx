import './ui.css'

function Badge({ children, variant = 'neutral', className = '' }) {
  return (
    <span className={`mgx-badge mgx-badge--${variant} ${className}`.trim()}>
      {children}
    </span>
  )
}

export default Badge
