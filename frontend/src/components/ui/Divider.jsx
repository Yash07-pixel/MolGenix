import './ui.css'

function Divider({ className = '' }) {
  return <hr className={`mgx-divider ${className}`.trim()} />
}

export default Divider
