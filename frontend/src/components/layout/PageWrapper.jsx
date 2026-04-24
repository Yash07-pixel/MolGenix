function PageWrapper({ children, className = '' }) {
  return <div className={`page-wrapper ${className}`.trim()}>{children}</div>
}

export default PageWrapper
