import React, { useState, useEffect } from 'react';
import { api, TaskStatus } from '../api';
import './TaskManager.css';

const TaskManager: React.FC = () => {
  const [status, setStatus] = useState<any>(null);
  const [tasks, setTasks] = useState<{ [key: string]: TaskStatus }>({});

  useEffect(() => {
    loadStatus();
    const interval = setInterval(() => {
      loadStatus();
      loadTaskStatuses();
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  const loadStatus = async () => {
    try {
      const response = await api.getStatus();
      setStatus(response.data);
    } catch (error) {
      console.error('Error loading status:', error);
    }
  };

  const loadTaskStatuses = async () => {
    const taskNames = ['download', 'parse', 'normalize'];
    const taskStatuses: { [key: string]: TaskStatus } = {};
    
    for (const taskName of taskNames) {
      try {
        const response = await api.getTaskStatus(taskName);
        taskStatuses[taskName] = response.data;
      } catch (error) {
        console.error(`Error loading task status ${taskName}:`, error);
      }
    }
    
    setTasks(taskStatuses);
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

  return (
    <div className="task-manager">
      <div className="card">
        <h2>Статистика</h2>
        {status && (
          <div className="stats">
            <div className="stat-item">
              <div className="stat-label">PDF файлов</div>
              <div className="stat-value">{status.pdfs_count}</div>
            </div>
            <div className="stat-item">
              <div className="stat-label">JSON файлов</div>
              <div className="stat-value">{status.jsons_count}</div>
            </div>
            <div className="stat-item">
              <div className="stat-label">Нормализованных</div>
              <div className="stat-value">{status.parsed_count}</div>
            </div>
          </div>
        )}
      </div>

      <div className="card">
        <h2>Управление задачами</h2>
        <div className="tasks">
          <div className="task-card">
            <h3>Скачивание расписаний</h3>
            <p>Скачать все расписания с сайта СурГУ</p>
            <button
              className="btn"
              onClick={handleStartDownload}
              disabled={tasks.download?.running}
            >
              {tasks.download?.running ? 'Выполняется...' : 'Запустить'}
            </button>
            {tasks.download && (
              <div className="task-status">
                {tasks.download.running && (
                  <div className="progress-bar">
                    <div
                      className="progress-fill"
                      style={{ width: `${tasks.download.progress}%` }}
                    />
                  </div>
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
            <button
              className="btn"
              onClick={handleStartParse}
              disabled={tasks.parse?.running}
            >
              {tasks.parse?.running ? 'Выполняется...' : 'Запустить'}
            </button>
            {tasks.parse && (
              <div className="task-status">
                {tasks.parse.running && (
                  <div className="progress-bar">
                    <div
                      className="progress-fill"
                      style={{ width: `${tasks.parse.progress}%` }}
                    />
                  </div>
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
            <button
              className="btn"
              onClick={handleStartNormalize}
              disabled={tasks.normalize?.running}
            >
              {tasks.normalize?.running ? 'Выполняется...' : 'Запустить'}
            </button>
            {tasks.normalize && (
              <div className="task-status">
                {tasks.normalize.running && (
                  <div className="progress-bar">
                    <div
                      className="progress-fill"
                      style={{ width: `${tasks.normalize.progress}%` }}
                    />
                  </div>
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

