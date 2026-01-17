import React, { useState, useEffect } from 'react';
import { api, TaskStatus } from '../api';
import './TaskManager.css';

const TaskManager: React.FC = () => {
  const [status, setStatus] = useState<any>(null);
  const [tasks, setTasks] = useState<{ [key: string]: TaskStatus }>({});

  useEffect(() => {
    loadStatus();
    loadTaskStatuses();
    
    // Опрашиваем статус с адаптивным интервалом
    let intervalId: NodeJS.Timeout;
    let isMounted = true;
    
    const poll = async () => {
      if (!isMounted) return;
      
      await loadStatus();
      const taskStatuses = await loadTaskStatuses();
      
      // Проверяем, есть ли запущенные задачи из ответа API
      const hasRunningTasks = taskStatuses && Object.values(taskStatuses).some((task: TaskStatus) => task?.running);
      
      if (hasRunningTasks) {
        // Если есть запущенные задачи - опрашиваем чаще (2 секунды)
        intervalId = setTimeout(poll, 2000);
      } else {
        // Если нет запущенных задач - опрашиваем реже (5 секунд)
        intervalId = setTimeout(poll, 5000);
      }
    };
    
    // Начинаем опрос через 2 секунды
    intervalId = setTimeout(poll, 2000);
    
    return () => {
      isMounted = false;
      if (intervalId) clearTimeout(intervalId);
    };
  }, []); // Убираем зависимость от tasks, чтобы избежать бесконечного цикла

  const loadStatus = async () => {
    try {
      const response = await api.getStatus();
      setStatus(response.data);
    } catch (error) {
      console.error('Error loading status:', error);
    }
  };

  const loadTaskStatuses = async (): Promise<{ [key: string]: TaskStatus } | null> => {
    const taskNames = ['download', 'parse', 'normalize'];
    const taskStatuses: { [key: string]: TaskStatus } = {};
    
    for (const taskName of taskNames) {
      try {
        const response = await api.getTaskStatus(taskName);
        taskStatuses[taskName] = response.data;
      } catch (error) {
        console.error(`Error loading task status ${taskName}:`, error);
        return null;
      }
    }
    
    setTasks(taskStatuses);
    return taskStatuses;
  };

  const handleStartDownload = async () => {
    try {
      await api.startDownload();
      loadStatus();
    } catch (error) {
      console.error('Error starting download:', error);
      alert('Ошибка при запуске скачивания');
    }
  };

  const handleStartParse = async () => {
    try {
      await api.startParse();
      loadStatus();
    } catch (error) {
      console.error('Error starting parse:', error);
      alert('Ошибка при запуске парсинга');
    }
  };

  const handleStartNormalize = async () => {
    try {
      await api.startNormalize();
      loadStatus();
    } catch (error) {
      console.error('Error starting normalize:', error);
      alert('Ошибка при запуске нормализации');
    }
  };

  const handleStopDownload = async () => {
    try {
      await api.stopTask('download');
      loadStatus();
      loadTaskStatuses();
    } catch (error) {
      console.error('Error stopping download:', error);
      alert('Ошибка при остановке скачивания');
    }
  };

  const handleStopParse = async () => {
    try {
      await api.stopTask('parse');
      loadStatus();
      loadTaskStatuses();
    } catch (error) {
      console.error('Error stopping parse:', error);
      alert('Ошибка при остановке парсинга');
    }
  };

  const handleStopNormalize = async () => {
    try {
      await api.stopTask('normalize');
      loadStatus();
      loadTaskStatuses();
    } catch (error) {
      console.error('Error stopping normalize:', error);
      alert('Ошибка при остановке нормализации');
    }
  };

  return (
    <div className="task-manager">
      <div className="card">
        <h2>Статистика</h2>
        {status ? (
          <div className="stats">
            <div className="stat-item">
              <div className="stat-label">PDF файлов</div>
              <div className="stat-value">{status.pdfs_count || 0}</div>
            </div>
            <div className="stat-item">
              <div className="stat-label">JSON файлов</div>
              <div className="stat-value">{status.jsons_count || 0}</div>
            </div>
            <div className="stat-item">
              <div className="stat-label">Нормализованных</div>
              <div className="stat-value">{status.parsed_count || 0}</div>
            </div>
          </div>
        ) : (
          <div>Загрузка...</div>
        )}
      </div>

      <div className="card">
        <h2>Управление задачами</h2>
        <div className="tasks">
          <div className="task-card">
            <h3>Скачивание расписаний</h3>
            <p>Скачать все расписания с сайта СурГУ</p>
            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                className="btn"
                onClick={handleStartDownload}
                disabled={tasks.download?.running}
              >
                {tasks.download?.running ? 'Выполняется...' : 'Запустить'}
              </button>
              {tasks.download?.running && (
                <button
                  className="btn"
                  onClick={handleStopDownload}
                  style={{ backgroundColor: '#dc3545', color: 'white' }}
                >
                  Остановить
                </button>
              )}
            </div>
            {tasks.download && (
              <div className="task-status">
                {tasks.download.running && (
                  <>
                    <div className="progress-bar">
                      <div
                        className="progress-fill"
                        style={{ width: `${tasks.download.progress}%` }}
                      />
                    </div>
                    <div className="progress-text">
                      {tasks.download.progress}%
                    </div>
                  </>
                )}
                {tasks.download.message && (
                  <div className="task-message">{tasks.download.message}</div>
                )}
              </div>
            )}
          </div>

          <div className="task-card">
            <h3>Парсинг PDF</h3>
            <p>Распарсить все PDF файлы в JSON</p>
            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                className="btn"
                onClick={handleStartParse}
                disabled={tasks.parse?.running}
              >
                {tasks.parse?.running ? 'Выполняется...' : 'Запустить'}
              </button>
              {tasks.parse?.running && (
                <button
                  className="btn"
                  onClick={handleStopParse}
                  style={{ backgroundColor: '#dc3545', color: 'white' }}
                >
                  Остановить
                </button>
              )}
            </div>
            {tasks.parse && (
              <div className="task-status">
                {tasks.parse.running && (
                  <>
                    <div className="progress-bar">
                      <div
                        className="progress-fill"
                        style={{ width: `${tasks.parse.progress}%` }}
                      />
                    </div>
                    <div className="progress-text">
                      {tasks.parse.progress}%
                    </div>
                  </>
                )}
                {tasks.parse.message && (
                  <div className="task-message">{tasks.parse.message}</div>
                )}
              </div>
            )}
          </div>

          <div className="task-card">
            <h3>Нормализация</h3>
            <p>Нормализовать названия дисциплин</p>
            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                className="btn"
                onClick={handleStartNormalize}
                disabled={tasks.normalize?.running}
              >
                {tasks.normalize?.running ? 'Выполняется...' : 'Запустить'}
              </button>
              {tasks.normalize?.running && (
                <button
                  className="btn"
                  onClick={handleStopNormalize}
                  style={{ backgroundColor: '#dc3545', color: 'white' }}
                >
                  Остановить
                </button>
              )}
            </div>
            {tasks.normalize && (
              <div className="task-status">
                {tasks.normalize.running && (
                  <>
                    <div className="progress-bar">
                      <div
                        className="progress-fill"
                        style={{ width: `${tasks.normalize.progress}%` }}
                      />
                    </div>
                    <div className="progress-text">
                      {tasks.normalize.progress}%
                    </div>
                  </>
                )}
                {tasks.normalize.message && (
                  <div className="task-message">{tasks.normalize.message}</div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default TaskManager;

