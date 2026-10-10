import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import DocumentsPage from './pages/DocumentsPage'
import './index.css'
import './documents.css'
createRoot(document.getElementById('root')).render(<StrictMode><DocumentsPage /></StrictMode>)
