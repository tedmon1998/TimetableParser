import React, { useState, useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import './App.css';
import ScriptRunner from './components/ScriptRunner';
import DatabaseView from './components/DatabaseView';
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
  // Восстанавливаем активную вкладку из URL при загрузке
  const getInitialTab = (): 'scripts' | 'database' => {
    const params = new URLSearchParams(window.location.search);
    const tab = params.get('tab');
    return (tab === 'scripts' || tab === 'database') ? tab : 'scripts';
  };

  const [activeTab, setActiveTab] = useState<'scripts' | 'database'>(getInitialTab);

  // Устанавливаем параметр tab в URL при первой загрузке, если его нет
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (!params.get('tab')) {
      params.set('tab', activeTab);
      window.history.replaceState({}, '', `${window.location.pathname}?${params.toString()}`);
    }
  }, []);

  // Обновляем URL при изменении вкладки
  const handleTabChange = (tab: 'scripts' | 'database') => {
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
          </nav>
        </header>
        <main className="App-main">
          {activeTab === 'scripts' && <ScriptRunner />}
          {activeTab === 'database' && <DatabaseView />}
        </main>
      </div>
    </QueryClientProvider>
  );
}

export default App;
