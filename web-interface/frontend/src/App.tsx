import React, { useState } from 'react';
import './App.css';
import FileViewer from './components/FileViewer';
import TaskManager from './components/TaskManager';
import AbbreviationsEditor from './components/AbbreviationsEditor';

type Tab = 'files' | 'tasks' | 'abbreviations';

function App() {
  const [activeTab, setActiveTab] = useState<Tab>('files');

  return (
    <div className="App">
      <header className="App-header">
        <h1>Расписания СурГУ</h1>
        <nav className="App-nav">
          <button
            className={activeTab === 'files' ? 'active' : ''}
            onClick={() => setActiveTab('files')}
          >
            Файлы
          </button>
          <button
            className={activeTab === 'tasks' ? 'active' : ''}
            onClick={() => setActiveTab('tasks')}
          >
            Управление
          </button>
          <button
            className={activeTab === 'abbreviations' ? 'active' : ''}
            onClick={() => setActiveTab('abbreviations')}
          >
            Сокращения
          </button>
        </nav>
      </header>
      <main className="App-main">
        {activeTab === 'files' && <FileViewer />}
        {activeTab === 'tasks' && <TaskManager />}
        {activeTab === 'abbreviations' && <AbbreviationsEditor />}
      </main>
    </div>
  );
}

export default App;

