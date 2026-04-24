import './ui.css'

function Spinner({ size = 16, className = '' }) {
  return (
    <span
      className={`mgx-spinner ${className}`.trim()}
      style={{ width: size, height: size }}
      aria-hidden="true"
    />
  )
}

export default Spinner
