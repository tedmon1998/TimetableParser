import React, { useState, useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import './App.css';
import ScriptRunner from './components/ScriptRunner';
import DatabaseView from './components/DatabaseView';
import TeachersView from './components/TeachersView';
import DisciplinesView from './components/DisciplinesView';
import DisciplineMatchView from './components/DisciplineMatchView';
import ScheduleView from './components/ScheduleView';
import InfoFilesView from './components/InfoFilesView';
import logoImage from '../assets/SurSU.png';

// Создаем QueryClient с настройками для оптимизации
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false, // Не обновлять при фокусе окна
      retry: 1, // Повторить только 1 раз при ошибке
      staleTime: 10000, // Данные считаются свежими 10 секунд
      gcTime: 60000, // Хранить в кеше 60 секунд (было cacheTime)
      refetchOnMount: true, // Обновлять при монтировании
      refetchOnReconnect: true, // Обновлять при переподключении
    },
  },
});

function App() {
  type TabType = 'scripts' | 'database' | 'teachers' | 'disciplines' | 'discipline-match' | 'schedule' | 'info-files';
  const getInitialTab = (): TabType => {
    const params = new URLSearchParams(window.location.search);
    const tab = params.get('tab');
    return (tab === 'scripts' || tab === 'database' || tab === 'teachers' || tab === 'disciplines' || tab === 'discipline-match' || tab === 'schedule' || tab === 'info-files') ? tab : 'scripts';
  };

  const [activeTab, setActiveTab] = useState<TabType>(getInitialTab);

  // Устанавливаем параметр tab в URL при первой загрузке, если его нет
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (!params.get('tab')) {
      params.set('tab', activeTab);
      window.history.replaceState({}, '', `${window.location.pathname}?${params.toString()}`);
    }
  }, []);

  // Обновляем URL при изменении вкладки
  const handleTabChange = (tab: TabType) => {
    setActiveTab(tab);
    const params = new URLSearchParams(window.location.search);
    params.set('tab', tab);
    window.history.pushState({}, '', `${window.location.pathname}?${params.toString()}`);
  };

  // Слушаем изменения в URL (например, при нажатии назад/вперед)
  useEffect(() => {
    const handlePopState = () => {
      const tab = getInitialTab();
      setActiveTab(tab);
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <div className="App">
        <header className="App-header">
          <div className="App-header-content">
            <img src={logoImage} alt="SurSU Logo" className="App-logo" />
            <h1>Парсер расписания</h1>
          </div>
          <nav className="App-nav">
            <button
              className={activeTab === 'scripts' ? 'active' : ''}
              onClick={() => handleTabChange('scripts')}
            >
              Запуск скриптов
            </button>
            <button
              className={activeTab === 'database' ? 'active' : ''}
              onClick={() => handleTabChange('database')}
            >
              База данных
            </button>
            <button
              className={activeTab === 'teachers' ? 'active' : ''}
              onClick={() => handleTabChange('teachers')}
            >
              Преподаватели
            </button>
            <button
              className={activeTab === 'disciplines' ? 'active' : ''}
              onClick={() => handleTabChange('disciplines')}
            >
              Дисциплины
            </button>
            <button
              className={activeTab === 'discipline-match' ? 'active' : ''}
              onClick={() => handleTabChange('discipline-match')}
            >
              Сопоставление дисциплин
            </button>
            <button
              className={activeTab === 'schedule' ? 'active' : ''}
              onClick={() => handleTabChange('schedule')}
            >
              Расписание
            </button>
            <button
              className={activeTab === 'info-files' ? 'active' : ''}
              onClick={() => handleTabChange('info-files')}
            >
              Настройки парсера
            </button>
          </nav>
        </header>
        <main className="App-main">
          {activeTab === 'scripts' && <ScriptRunner />}
          {activeTab === 'database' && <DatabaseView />}
          {activeTab === 'teachers' && <TeachersView />}
          {activeTab === 'disciplines' && <DisciplinesView />}
          {activeTab === 'discipline-match' && <DisciplineMatchView />}
          {activeTab === 'schedule' && <ScheduleView />}
          {activeTab === 'info-files' && <InfoFilesView />}
        </main>
      </div>
    </QueryClientProvider>
  );
}

export default App;
