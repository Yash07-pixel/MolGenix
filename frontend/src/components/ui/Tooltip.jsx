import './ui.css'

function Tooltip({ content, children, className = '' }) {
  return (
    <span className={`mgx-tooltip ${className}`.trim()}>
      <span className="mgx-tooltip__trigger" tabIndex={0}>
        {children}
      </span>
      <span className="mgx-tooltip__content" role="tooltip">
        {content}
      </span>
    </span>
  )
}

export default Tooltip
