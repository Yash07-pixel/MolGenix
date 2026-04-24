import { AnimatePresence, motion } from 'framer-motion'
import { BrowserRouter, Route, Routes, useLocation } from 'react-router-dom'
import Navbar from './components/layout/Navbar'
import AppErrorBoundary from './components/AppErrorBoundary'
import { ToastProvider } from './hooks/useToast'
import LandingPage from './pages/LandingPage'
import SearchPage from './pages/SearchPage'
import TargetPage from './pages/TargetPage'
import MoleculesPage from './pages/MoleculesPage'
import ReportPage from './pages/ReportPage'
import NotFoundPage from './pages/NotFoundPage'

function App() {
  return (
    <AppErrorBoundary>
      <ToastProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </ToastProvider>
    </AppErrorBoundary>
  )
}

function AppRoutes() {
  const location = useLocation()
  const MotionDiv = motion.div

  return (
    <div className="app-shell">
      <Navbar />
      <main className="app-main">
        <AnimatePresence mode="wait">
          <MotionDiv
            key={location.pathname}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
          >
            <Routes location={location}>
              <Route path="/" element={<LandingPage />} />
              <Route path="/search" element={<SearchPage />} />
              <Route path="/target/:targetId" element={<TargetPage />} />
              <Route path="/molecules/:targetId" element={<MoleculesPage />} />
              <Route path="/report/:targetId" element={<ReportPage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </MotionDiv>
        </AnimatePresence>
      </main>
    </div>
  )
}

export default App
