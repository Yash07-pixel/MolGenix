import './ui.css'

function Card({ as = 'section', className = '', children, ...props }) {
  const Component = as

  return (
    <Component className={`mgx-card ${className}`.trim()} {...props}>
      {children}
    </Component>
  )
}

export default Card
