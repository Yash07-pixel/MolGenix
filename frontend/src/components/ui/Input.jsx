import './ui.css'

function Input({ className = '', ...props }) {
  return <input className={`mgx-input ${className}`.trim()} {...props} />
}

export default Input
