import React from 'react';
import './App.css';
import ProjectionSystem from './components/ProjectionSystem';
import { ThemeProvider } from './context/ThemeContext';

function App() {
  return (
    <ThemeProvider>
      <div className="App">
        <ProjectionSystem />
      </div>
    </ThemeProvider>
  );
}

export default App;
