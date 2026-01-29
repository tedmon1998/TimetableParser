import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './ScriptRunner.css';

interface ScriptStatus {
  running: boolean;
  progress: number;
  message: string;
  error: string | null;
}

const ScriptRunner: React.FC = () => {
  const [parseStatus, setParseStatus] = useState<ScriptStatus>({
    running: false,
    progress: 0,
    message: '',
    error: null
  });
  const [cleanStatus, setCleanStatus] = useState<ScriptStatus>({
    running: false,
    progress: 0,
    message: '',
    error: null
  });
  const [processTimetableStatus, setProcessTimetableStatus] = useState<ScriptStatus>({
    running: false,
    progress: 0,
    message: '',
    error: null
  });

  const API_BASE = import.meta.env.VITE_API_URL || '/api';

  useEffect(() => {
    const interval = setInterval(() => {
      if (parseStatus.running) {
        fetchStatus('parse_timetable', setParseStatus);
      }
      if (cleanStatus.running) {
        fetchStatus('clean_audiences', setCleanStatus);
      }
      if (processTimetableStatus.running) {
        fetchStatus('process_timetable', setProcessTimetableStatus);
      }
    }, 500);

    return () => clearInterval(interval);
  }, [parseStatus.running, cleanStatus.running, processTimetableStatus.running]);

  const fetchStatus = async (scriptName: string, setStatus: React.Dispatch<React.SetStateAction<ScriptStatus>>) => {
    try {
      const response = await axios.get(`${API_BASE}/status/${scriptName}`);
      setStatus(response.data);
    } catch (error) {
      console.error(`Error fetching status for ${scriptName}:`, error);
    }
  };

  const runScript = async (scriptName: 'parse_timetable' | 'clean_audiences' | 'process_timetable') => {
    const setStatus = scriptName === 'parse_timetable' ? setParseStatus
      : scriptName === 'clean_audiences' ? setCleanStatus
      : setProcessTimetableStatus;
    
    setStatus({
      running: true,
      progress: 0,
      message: 'Запуск...',
      error: null
    });

    const runUrl = scriptName === 'process_timetable' ? `${API_BASE}/run/process_timetable` : `${API_BASE}/run/${scriptName}`;
    try {
      await axios.post(runUrl);
      // Начинаем опрос статуса
      const statusInterval = setInterval(async () => {
        try {
          const response = await axios.get(`${API_BASE}/status/${scriptName}`);
          const status = response.data;
          setStatus(status);
          
          if (!status.running) {
            clearInterval(statusInterval);
          }
        } catch (error) {
          console.error(`Error fetching status:`, error);
          clearInterval(statusInterval);
        }
      }, 500);
    } catch (error: any) {
      setStatus({
        running: false,
        progress: 0,
        message: 'Ошибка при запуске скрипта',
        error: error.response?.data?.error || error.message
      });
    }
  };

  return (
    <div className="script-runner">
      <div className="card">
        <h2>Парсинг расписания (parse_timetable_excel.py)</h2>
        <p className="description">
          Парсит Excel файлы из папки input/timetable и создает timetable_processed.csv/xlsx
        </p>
        <button
          className="button"
          onClick={() => runScript('parse_timetable')}
          disabled={parseStatus.running}
        >
          {parseStatus.running ? 'Выполняется...' : 'Запустить парсинг'}
        </button>
        
        {parseStatus.running && (
          <div className="progress-container">
            <div className="progress-bar">
              <div
                className="progress-bar-fill"
                style={{ width: `${parseStatus.progress}%` }}
              >
                {parseStatus.progress}%
              </div>
            </div>
            <p className="progress-message">{parseStatus.message}</p>
          </div>
        )}
        
        {parseStatus.error && (
          <div className="message error">
            <strong>Ошибка:</strong> {parseStatus.error}
          </div>
        )}
        
        {!parseStatus.running && parseStatus.progress === 100 && !parseStatus.error && (
          <div className="message success">
            {parseStatus.message || 'Скрипт выполнен успешно!'}
          </div>
        )}
      </div>

      <div className="card">
        <h2>Очистка аудиторий (clean_audiences.py)</h2>
        <p className="description">
          Обрабатывает timetable_processed.csv, очищает аудитории и обновляет базу данных
        </p>
        <button
          className="button"
          onClick={() => runScript('clean_audiences')}
          disabled={cleanStatus.running}
        >
          {cleanStatus.running ? 'Выполняется...' : 'Запустить очистку'}
        </button>
        
        {cleanStatus.running && (
          <div className="progress-container">
            <div className="progress-bar">
              <div
                className="progress-bar-fill"
                style={{ width: `${cleanStatus.progress}%` }}
              >
                {cleanStatus.progress}%
              </div>
            </div>
            <p className="progress-message">{cleanStatus.message}</p>
          </div>
        )}
        
        {cleanStatus.error && (
          <div className="message error">
            <strong>Ошибка:</strong> {cleanStatus.error}
          </div>
        )}
        
        {!cleanStatus.running && cleanStatus.progress === 100 && !cleanStatus.error && (
          <div className="message success">
            {cleanStatus.message || 'Скрипт выполнен успешно! База данных обновлена.'}
          </div>
        )}
      </div>

      <div className="card">
        <h2>Занятость преподавателей (process_timetable.py)</h2>
        <p className="description">
          Парсит файл занятости преподавателей из input, формирует timetable_teacher.csv и загружает в БД
        </p>
        <button
          className="button"
          onClick={() => runScript('process_timetable')}
          disabled={processTimetableStatus.running}
        >
          {processTimetableStatus.running ? 'Выполняется...' : 'Запустить парсинг занятости'}
        </button>
        {processTimetableStatus.running && (
          <div className="progress-container">
            <div className="progress-bar">
              <div
                className="progress-bar-fill"
                style={{ width: `${processTimetableStatus.progress}%` }}
              >
                {processTimetableStatus.progress}%
              </div>
            </div>
            <p className="progress-message">{processTimetableStatus.message}</p>
          </div>
        )}
        {processTimetableStatus.error && (
          <div className="message error">
            <strong>Ошибка:</strong> {processTimetableStatus.error}
          </div>
        )}
        {!processTimetableStatus.running && processTimetableStatus.progress === 100 && !processTimetableStatus.error && (
          <div className="message success">
            {processTimetableStatus.message || 'Парсинг занятости завершён. База обновлена.'}
          </div>
        )}
      </div>
    </div>
  );
};

export default ScriptRunner;
