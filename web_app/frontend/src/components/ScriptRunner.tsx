import React, { useState, useEffect } from 'react';
import axios from 'axios';
import * as XLSX from 'xlsx';
import './ScriptRunner.css';

interface ScriptStatus {
  running: boolean;
  progress: number;
  message: string;
  error: string | null;
}

interface GroupSourceResult {
  file_path: string;
  file_name: string;
  sheet_name: string;
  sheet_index: number;
}

const ScriptRunner: React.FC = () => {
  const [groupSearchQuery, setGroupSearchQuery] = useState('');
  const [groupSearchResults, setGroupSearchResults] = useState<GroupSourceResult[]>([]);
  const [groupSearchLoading, setGroupSearchLoading] = useState(false);
  const [groupSearchError, setGroupSearchError] = useState<string | null>(null);

  const [excelViewerOpen, setExcelViewerOpen] = useState(false);
  const [excelViewerLoading, setExcelViewerLoading] = useState(false);
  const [excelViewerError, setExcelViewerError] = useState<string | null>(null);
  const [excelViewerHtml, setExcelViewerHtml] = useState<string>('');
  const [excelViewerTitle, setExcelViewerTitle] = useState<string>('');

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
  const [loadTimetableToDbStatus, setLoadTimetableToDbStatus] = useState<ScriptStatus>({
    running: false,
    progress: 0,
    message: '',
    error: null
  });
  const [mergeTimetableStatus, setMergeTimetableStatus] = useState<ScriptStatus>({
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
      if (loadTimetableToDbStatus.running) {
        fetchStatus('load_timetable_to_db', setLoadTimetableToDbStatus);
      }
      if (mergeTimetableStatus.running) {
        fetchStatus('merge_timetable', setMergeTimetableStatus);
      }
      if (processTimetableStatus.running) {
        fetchStatus('process_timetable', setProcessTimetableStatus);
      }
    }, 500);

    return () => clearInterval(interval);
  }, [parseStatus.running, cleanStatus.running, loadTimetableToDbStatus.running, mergeTimetableStatus.running, processTimetableStatus.running]);

  const fetchStatus = async (scriptName: string, setStatus: React.Dispatch<React.SetStateAction<ScriptStatus>>) => {
    try {
      const response = await axios.get(`${API_BASE}/status/${scriptName}`);
      setStatus(response.data);
    } catch (error) {
      console.error(`Error fetching status for ${scriptName}:`, error);
    }
  };

  const runScript = async (scriptName: 'parse_timetable' | 'clean_audiences' | 'load_timetable_to_db' | 'merge_timetable' | 'process_timetable') => {
    const setStatus = scriptName === 'parse_timetable' ? setParseStatus
      : scriptName === 'clean_audiences' ? setCleanStatus
        : scriptName === 'load_timetable_to_db' ? setLoadTimetableToDbStatus
          : scriptName === 'merge_timetable' ? setMergeTimetableStatus
            : setProcessTimetableStatus;

    setStatus({
      running: true,
      progress: 0,
      message: 'Запуск...',
      error: null
    });

    const runUrl = scriptName === 'process_timetable' ? `${API_BASE}/run/process_timetable`
      : scriptName === 'load_timetable_to_db' ? `${API_BASE}/run/load_timetable_to_db`
        : `${API_BASE}/run/${scriptName}`;
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

  const handleGroupSearch = async () => {
    const q = groupSearchQuery.trim();
    if (!q) return;
    setGroupSearchLoading(true);
    setGroupSearchError(null);
    setGroupSearchResults([]);
    try {
      const response = await axios.get(`${API_BASE}/group-source`, { params: { group: q } });
      setGroupSearchResults(response.data.results || []);
      if (!(response.data.results?.length)) {
        setGroupSearchError('Группа не найдена ни в одном файле.');
      }
    } catch (err: any) {
      setGroupSearchError(err.response?.data?.error || err.message || 'Ошибка поиска');
      setGroupSearchResults([]);
    } finally {
      setGroupSearchLoading(false);
    }
  };

  const fileDownloadUrl = (filePath: string) => {
    const base = API_BASE.replace(/\/$/, '');
    return `${base}/files/timetable/${encodeURIComponent(filePath)}`;
  };

  const openExcelViewer = async (r: GroupSourceResult) => {
    setExcelViewerOpen(true);
    setExcelViewerLoading(true);
    setExcelViewerError(null);
    setExcelViewerHtml('');
    setExcelViewerTitle(`${r.file_name} — лист ${r.sheet_index} (${r.sheet_name})`);
    try {
      const url = fileDownloadUrl(r.file_path);
      const response = await axios.get(url, { responseType: 'arraybuffer' });
      const data = new Uint8Array(response.data);
      const wb = XLSX.read(data, { type: 'array' });
      const sheetIndex = Math.max(0, Math.min(r.sheet_index - 1, wb.SheetNames.length - 1));
      const sheetName = wb.SheetNames[sheetIndex];
      const ws = wb.Sheets[sheetName];
      const html = XLSX.utils.sheet_to_html(ws, { id: 'excel-sheet-table', editable: false });
      setExcelViewerHtml(html);
    } catch (err: any) {
      setExcelViewerError(err.response?.data?.error || err.message || 'Не удалось загрузить файл');
    } finally {
      setExcelViewerLoading(false);
    }
  };

  return (
    <div className="script-runner">
      <div className="card group-search-card">
        <h2>Поиск по номеру группы</h2>
        <p className="description">
          Введите номер группы (например, 606-22). Результат: файл и лист, где встречается группа. По ссылке можно скачать файл и открыть его на указанном листе.
        </p>
        <div className="group-search-row">
          <input
            type="text"
            className="group-search-input"
            placeholder="Номер группы (606-22, 501-33...)"
            value={groupSearchQuery}
            onChange={(e) => setGroupSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleGroupSearch()}
          />
          <button
            type="button"
            className="button"
            onClick={handleGroupSearch}
            disabled={groupSearchLoading}
          >
            {groupSearchLoading ? 'Поиск...' : 'Поиск'}
          </button>
        </div>
        {groupSearchError && (
          <div className="message error" style={{ marginTop: '1rem' }}>
            {groupSearchError}
          </div>
        )}
        {groupSearchResults.length > 0 && (
          <ul className="group-search-results">
            {groupSearchResults.map((r, i) => (
              <li key={`${r.file_path}-${r.sheet_index}-${i}`} className="group-search-result-item">
                <span className="group-search-result-text">
                  <strong>{r.file_name}</strong> — лист {r.sheet_index} ({r.sheet_name})
                </span>
                <span className="group-search-result-actions">
                  <button
                    type="button"
                    className="button button-small"
                    onClick={() => openExcelViewer(r)}
                  >
                    Открыть на сайте
                  </button>
                  <a
                    href={fileDownloadUrl(r.file_path)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group-search-result-link"
                  >
                    Скачать
                  </a>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

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
        <h2>Обработка расписания (clean_audiences.py)</h2>
        <p className="description">
          Обрабатывает timetable_processed.csv/xlsx: очищает аудитории, дисциплины. Результат — timetable_processed_cleaned. В БД не загружает.
        </p>
        <button
          className="button"
          onClick={() => runScript('clean_audiences')}
          disabled={cleanStatus.running}
        >
          {cleanStatus.running ? 'Выполняется...' : 'Запустить обработку'}
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
            {cleanStatus.message || 'Обработка завершена успешно!'}
          </div>
        )}
      </div>

      <div className="card">
        <h2>Добавить расписание в БД</h2>
        <p className="description">
          Загружает timetable_processed_cleaned.csv в таблицу timetable_cleaned. Сначала выполните «Обработка расписания».
        </p>
        <button
          className="button"
          onClick={() => runScript('load_timetable_to_db')}
          disabled={loadTimetableToDbStatus.running}
        >
          {loadTimetableToDbStatus.running ? 'Выполняется...' : 'Добавить в БД'}
        </button>

        {loadTimetableToDbStatus.running && (
          <div className="progress-container">
            <div className="progress-bar">
              <div
                className="progress-bar-fill"
                style={{ width: `${loadTimetableToDbStatus.progress}%` }}
              >
                {loadTimetableToDbStatus.progress}%
              </div>
            </div>
            <p className="progress-message">{loadTimetableToDbStatus.message}</p>
          </div>
        )}

        {loadTimetableToDbStatus.error && (
          <div className="message error">
            <strong>Ошибка:</strong> {loadTimetableToDbStatus.error}
          </div>
        )}

        {!loadTimetableToDbStatus.running && loadTimetableToDbStatus.progress === 100 && !loadTimetableToDbStatus.error && (
          <div className="message success">
            {loadTimetableToDbStatus.message || 'Данные загружены в БД.'}
          </div>
        )}
      </div>

      <div className="card">
        <h2>Слияние расписания (intermediate_timetable)</h2>
        <p className="description">
          Объединяет таблицы timetable_cleaned и timetable_teacher по паре, дню, группе и аудитории. Результат — таблица «Промежуточное расписание».
        </p>
        <button
          className="button"
          onClick={() => runScript('merge_timetable')}
          disabled={mergeTimetableStatus.running}
        >
          {mergeTimetableStatus.running ? 'Выполняется...' : 'Выполнить слияние'}
        </button>
        {mergeTimetableStatus.running && (
          <div className="progress-container">
            <div className="progress-bar">
              <div
                className="progress-bar-fill"
                style={{ width: `${mergeTimetableStatus.progress}%` }}
              >
                {mergeTimetableStatus.progress}%
              </div>
            </div>
            <p className="progress-message">{mergeTimetableStatus.message}</p>
          </div>
        )}
        {mergeTimetableStatus.error && (
          <div className="message error">
            <strong>Ошибка:</strong> {mergeTimetableStatus.error}
          </div>
        )}
        {!mergeTimetableStatus.running && mergeTimetableStatus.progress === 100 && !mergeTimetableStatus.error && (
          <div className="message success">
            {mergeTimetableStatus.message || 'Слияние завершено.'}
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

      {excelViewerOpen && (
        <div className="excel-viewer-overlay" onClick={() => setExcelViewerOpen(false)}>
          <div className="excel-viewer-modal" onClick={(e) => e.stopPropagation()}>
            <div className="excel-viewer-header">
              <h3 className="excel-viewer-title">{excelViewerTitle}</h3>
              <button type="button" className="excel-viewer-close" onClick={() => setExcelViewerOpen(false)} aria-label="Закрыть">
                ×
              </button>
            </div>
            <div className="excel-viewer-body">
              {excelViewerLoading && <p className="excel-viewer-loading">Загрузка листа…</p>}
              {excelViewerError && <p className="message error">{excelViewerError}</p>}
              {!excelViewerLoading && excelViewerHtml && (
                <div className="excel-viewer-table-wrap" dangerouslySetInnerHTML={{ __html: excelViewerHtml }} />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ScriptRunner;
