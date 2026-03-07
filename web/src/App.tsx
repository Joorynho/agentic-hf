import React from 'react'
import { WebSocketProvider } from './contexts/WebSocketContext'
import { ThreeDCanvas } from './components/ThreeDCanvas'
import { DataPanel } from './components/DataPanel'
import './App.css'

function App() {
  return (
    <WebSocketProvider wsUrl={`ws://${window.location.hostname}:8000/ws`}>
      <div className="app">
        <div className="grid grid-cols-3 h-full gap-0">
          {/* Main viewport (2/3 width) */}
          <div className="col-span-2 relative overflow-hidden">
            <ThreeDCanvas />
          </div>

          {/* Data panel (1/3 width) */}
          <div className="col-span-1 border-l border-border-color overflow-hidden max-h-screen flex flex-col">
            <DataPanel />
          </div>
        </div>
      </div>
    </WebSocketProvider>
  )
}

export default App
