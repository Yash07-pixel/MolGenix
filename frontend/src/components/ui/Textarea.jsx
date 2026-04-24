import './ui.css'

function Textarea({ className = '', ...props }) {
  return <textarea className={`mgx-textarea ${className}`.trim()} {...props} />
}

export default Textarea
