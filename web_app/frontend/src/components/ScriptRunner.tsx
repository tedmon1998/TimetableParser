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
  const [parseAspiStatus, setParseAspiStatus] = useState<ScriptStatus>({
    running: false,
    progress: 0,
    message: '',
    error: null
  });
  const [normalizeAspiStatus, setNormalizeAspiStatus] = useState<ScriptStatus>({
    running: false,
    progress: 0,
    message: '',
    error: null
  });
  const [loadAspiToDbStatus, setLoadAspiToDbStatus] = useState<ScriptStatus>({
    running: false,
    progress: 0,
    message: '',
    error: null
  });
  const [mergeAspiToIntermediateStatus, setMergeAspiToIntermediateStatus] = useState<ScriptStatus>({
    running: false,
    progress: 0,
    message: '',
    error: null
  });

  type ScriptRunnerTab = 'bachelor_master' | 'aspi';

  const getInitialSubtab = (): ScriptRunnerTab => {
    const params = new URLSearchParams(window.location.search);
    const subtab = params.get('subtab');
    return subtab === 'aspi' ? 'aspi' : 'bachelor_master';
  };
  const [activeTab, setActiveTabState] = useState<ScriptRunnerTab>(getInitialSubtab);

  const setActiveTab = (tab: ScriptRunnerTab) => {
    setActiveTabState(tab);
    const params = new URLSearchParams(window.location.search);
    params.set('subtab', tab);
    window.history.replaceState({}, '', `${window.location.pathname}?${params.toString()}`);
  };

  useEffect(() => {
    const handlePopState = () => setActiveTabState(getInitialSubtab());
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  // При первом заходе на «Запуск скриптов» дописываем subtab в URL, чтобы при обновлении не сбрасывалось
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (!params.has('subtab')) {
      params.set('subtab', activeTab);
      window.history.replaceState({}, '', `${window.location.pathname}?${params.toString()}`);
    }
  }, []);

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
      if (parseAspiStatus.running) {
        fetchStatus('parse_aspi', setParseAspiStatus);
      }
      if (normalizeAspiStatus.running) {
        fetchStatus('normalize_aspi', setNormalizeAspiStatus);
      }
      if (loadAspiToDbStatus.running) {
        fetchStatus('load_aspi_to_db', setLoadAspiToDbStatus);
      }
      if (mergeAspiToIntermediateStatus.running) {
        fetchStatus('merge_aspi_to_intermediate', setMergeAspiToIntermediateStatus);
      }
    }, 500);

    return () => clearInterval(interval);
  }, [parseStatus.running, cleanStatus.running, loadTimetableToDbStatus.running, mergeTimetableStatus.running, processTimetableStatus.running, parseAspiStatus.running, normalizeAspiStatus.running, loadAspiToDbStatus.running, mergeAspiToIntermediateStatus.running]);

  const fetchStatus = async (scriptName: string, setStatus: React.Dispatch<React.SetStateAction<ScriptStatus>>) => {
    try {
      const response = await axios.get(`${API_BASE}/status/${scriptName}`);
      setStatus(response.data);
    } catch (error) {
      console.error(`Error fetching status for ${scriptName}:`, error);
    }
  };

  const runScript = (scriptName: 'parse_timetable' | 'clean_audiences' | 'load_timetable_to_db' | 'merge_timetable' | 'process_timetable' | 'parse_aspi' | 'normalize_aspi' | 'load_aspi_to_db' | 'merge_aspi_to_intermediate'): Promise<ScriptStatus> => {
    const setStatus = scriptName === 'parse_timetable' ? setParseStatus
      : scriptName === 'clean_audiences' ? setCleanStatus
        : scriptName === 'load_timetable_to_db' ? setLoadTimetableToDbStatus
          : scriptName === 'merge_timetable' ? setMergeTimetableStatus
            : scriptName === 'process_timetable' ? setProcessTimetableStatus
              : scriptName === 'parse_aspi' ? setParseAspiStatus
                : scriptName === 'normalize_aspi' ? setNormalizeAspiStatus
                  : scriptName === 'load_aspi_to_db' ? setLoadAspiToDbStatus
                    : setMergeAspiToIntermediateStatus;

    setStatus({
      running: true,
      progress: 0,
      message: 'Запуск...',
      error: null
    });

    const runUrl = scriptName === 'process_timetable' ? `${API_BASE}/run/process_timetable`
      : scriptName === 'load_timetable_to_db' ? `${API_BASE}/run/load_timetable_to_db`
        : scriptName === 'parse_aspi' ? `${API_BASE}/run/parse_aspi`
          : scriptName === 'normalize_aspi' ? `${API_BASE}/run/normalize_aspi`
            : scriptName === 'load_aspi_to_db' ? `${API_BASE}/run/load_aspi_to_db`
              : scriptName === 'merge_aspi_to_intermediate' ? `${API_BASE}/run/merge_aspi_to_intermediate`
                : `${API_BASE}/run/${scriptName}`;

    return axios.post(runUrl)
      .then(() => {
        return new Promise<ScriptStatus>((resolve, reject) => {
          const statusInterval = setInterval(async () => {
            try {
              const response = await axios.get(`${API_BASE}/status/${scriptName}`);
              const status: ScriptStatus = response.data;
              setStatus(status);
              if (!status.running) {
                clearInterval(statusInterval);
                resolve(status);
              }
            } catch (error) {
              clearInterval(statusInterval);
              reject(error);
            }
          }, 500);
        });
      })
      .catch((error: any) => {
        const errMsg = error.response?.data?.error || error.message;
        setStatus({
          running: false,
          progress: 0,
          message: 'Ошибка при запуске скрипта',
          error: errMsg
        });
        return Promise.reject(error);
      });
  };

  const [pipelineRunning, setPipelineRunning] = useState(false);
  const runAllPipeline = async () => {
    if (pipelineRunning) return;
    setPipelineRunning(true);
    try {
      await runScript('parse_timetable');
      await runScript('clean_audiences');
      await runScript('load_timetable_to_db');
    } catch {
      // Ошибка уже отображена в статусе шага
    } finally {
      setPipelineRunning(false);
    }
  };

  const [pipelineAspiRunning, setPipelineAspiRunning] = useState(false);
  const runAllAspiPipeline = async () => {
    if (pipelineAspiRunning) return;
    setPipelineAspiRunning(true);
    try {
      await runScript('parse_aspi');
      await runScript('normalize_aspi');
      await runScript('load_aspi_to_db');
      // Добавление к intermediate — только по отдельному нажатию «Добавить к intermediate»
    } catch {
      // Ошибка уже отображена в статусе шага
    } finally {
      setPipelineAspiRunning(false);
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
      <div className="script-runner-tabs">
        <button
          type="button"
          className={`script-runner-tab ${activeTab === 'bachelor_master' ? 'active' : ''}`}
          onClick={() => setActiveTab('bachelor_master')}
        >
          Бакалавры + магистры
        </button>
        <button
          type="button"
          className={`script-runner-tab ${activeTab === 'aspi' ? 'active' : ''}`}
          onClick={() => setActiveTab('aspi')}
        >
          Аспиранты
        </button>
      </div>

      {activeTab === 'bachelor_master' && (
        <>
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

      <div className="card pipeline-card">
        <h2>Парсинг → Обработка → Загрузка в БД</h2>
        <p className="description">
          Парсинг Excel из input/timetable → очистка аудиторий и дисциплин → загрузка в таблицу timetable_cleaned. Можно запускать шаги по отдельности или всё по очереди.
        </p>
        <div className="pipeline-actions">
          <button
            className="button"
            onClick={() => runScript('parse_timetable')}
            disabled={parseStatus.running || pipelineRunning}
          >
            {parseStatus.running ? 'Выполняется...' : 'Запуск парсинга'}
          </button>
          <button
            className="button"
            onClick={() => runScript('clean_audiences')}
            disabled={cleanStatus.running || pipelineRunning}
          >
            {cleanStatus.running ? 'Выполняется...' : 'Запуск обработки'}
          </button>
          <button
            className="button"
            onClick={() => runScript('load_timetable_to_db')}
            disabled={loadTimetableToDbStatus.running || pipelineRunning}
          >
            {loadTimetableToDbStatus.running ? 'Выполняется...' : 'Добавить в БД'}
          </button>
          <button
            className="button button-primary"
            onClick={runAllPipeline}
            disabled={pipelineRunning || parseStatus.running || cleanStatus.running || loadTimetableToDbStatus.running}
          >
            {pipelineRunning ? 'Выполняется цепочка...' : 'Запустить всё по очереди'}
          </button>
        </div>
        <div className="pipeline-progress-list">
          <div className="pipeline-step">
            <span className="pipeline-step-label">1. Парсинг</span>
            <div className="progress-container">
              <div className="progress-bar">
                <div
                  className="progress-bar-fill"
                  style={{ width: `${parseStatus.progress}%` }}
                >
                  {parseStatus.progress}%
                </div>
              </div>
              <p className="progress-message">{parseStatus.message || (parseStatus.progress === 100 && !parseStatus.error ? 'Готово' : '')}</p>
            </div>
            {parseStatus.error && <div className="message error">{parseStatus.error}</div>}
          </div>
          <div className="pipeline-step">
            <span className="pipeline-step-label">2. Обработка</span>
            <div className="progress-container">
              <div className="progress-bar">
                <div
                  className="progress-bar-fill"
                  style={{ width: `${cleanStatus.progress}%` }}
                >
                  {cleanStatus.progress}%
                </div>
              </div>
              <p className="progress-message">{cleanStatus.message || (cleanStatus.progress === 100 && !cleanStatus.error ? 'Готово' : '')}</p>
            </div>
            {cleanStatus.error && <div className="message error">{cleanStatus.error}</div>}
          </div>
          <div className="pipeline-step">
            <span className="pipeline-step-label">3. Добавить в БД</span>
            <div className="progress-container">
              <div className="progress-bar">
                <div
                  className="progress-bar-fill"
                  style={{ width: `${loadTimetableToDbStatus.progress}%` }}
                >
                  {loadTimetableToDbStatus.progress}%
                </div>
              </div>
              <p className="progress-message">{loadTimetableToDbStatus.message || (loadTimetableToDbStatus.progress === 100 && !loadTimetableToDbStatus.error ? 'Готово' : '')}</p>
            </div>
            {loadTimetableToDbStatus.error && <div className="message error">{loadTimetableToDbStatus.error}</div>}
          </div>
        </div>
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
        </>
      )}

      {activeTab === 'aspi' && (
      <div className="card pipeline-card">
        <h2>Парсер расписания аспирантов (parse_aspi.py)</h2>
        <p className="description">
          Парсит .docx из папки aspi/aspi и сохраняет JSON в aspi/output (по файлам и сводный _all.json). Поля: группа, научная специальность, год обучения, день недели, пара, дисциплина, ФИО, предмет, неделя.
        </p>
        <div className="pipeline-actions">
          <button
            className="button"
            onClick={() => runScript('parse_aspi')}
            disabled={parseAspiStatus.running || normalizeAspiStatus.running || loadAspiToDbStatus.running || mergeAspiToIntermediateStatus.running || pipelineAspiRunning}
          >
            {parseAspiStatus.running ? 'Выполняется...' : 'Запустить парсер аспирантов'}
          </button>
          <button
            className="button"
            onClick={() => runScript('normalize_aspi')}
            disabled={normalizeAspiStatus.running || parseAspiStatus.running || loadAspiToDbStatus.running || mergeAspiToIntermediateStatus.running || pipelineAspiRunning}
          >
            {normalizeAspiStatus.running ? 'Выполняется...' : 'Нормализация'}
          </button>
          <button
            className="button"
            onClick={() => runScript('load_aspi_to_db')}
            disabled={loadAspiToDbStatus.running || parseAspiStatus.running || normalizeAspiStatus.running || mergeAspiToIntermediateStatus.running || pipelineAspiRunning}
          >
            {loadAspiToDbStatus.running ? 'Выполняется...' : 'Добавить в БД (timetable_aspi)'}
          </button>
          <button
            className="button"
            onClick={() => runScript('merge_aspi_to_intermediate')}
            disabled={mergeAspiToIntermediateStatus.running || parseAspiStatus.running || normalizeAspiStatus.running || loadAspiToDbStatus.running || pipelineAspiRunning}
          >
            {mergeAspiToIntermediateStatus.running ? 'Выполняется...' : 'Добавить к intermediate'}
          </button>
          <button
            className="button button-primary"
            onClick={runAllAspiPipeline}
            disabled={pipelineAspiRunning || parseAspiStatus.running || normalizeAspiStatus.running || loadAspiToDbStatus.running || mergeAspiToIntermediateStatus.running}
          >
            {pipelineAspiRunning ? 'Выполняется цепочка...' : 'Запустить всё по очереди'}
          </button>
        </div>
        <p className="description" style={{ marginTop: 0, fontSize: '0.9rem', color: '#666' }}>
          Нормализация: полные ФИО из справочника, дни (понедельник, вторник…), ключи как у бакалавров, дисциплины без ЭОиДОТ/Ауд./Каб (выносятся в audience). Парсер → нормализация → «Добавить в БД» (timetable_aspi) → «Добавить к intermediate» (intermediate_timetable).
        </p>
        {(parseAspiStatus.running || normalizeAspiStatus.running || loadAspiToDbStatus.running || mergeAspiToIntermediateStatus.running || pipelineAspiRunning) && (
          <div className="progress-container">
            <div className="progress-bar">
              <div
                className="progress-bar-fill"
                style={{ width: `${parseAspiStatus.running ? parseAspiStatus.progress : normalizeAspiStatus.running ? normalizeAspiStatus.progress : loadAspiToDbStatus.running ? loadAspiToDbStatus.progress : mergeAspiToIntermediateStatus.progress}%` }}
              >
                {parseAspiStatus.running ? parseAspiStatus.progress : normalizeAspiStatus.running ? normalizeAspiStatus.progress : loadAspiToDbStatus.running ? loadAspiToDbStatus.progress : mergeAspiToIntermediateStatus.progress}%
              </div>
            </div>
            <p className="progress-message">
              {parseAspiStatus.running ? parseAspiStatus.message : normalizeAspiStatus.running ? normalizeAspiStatus.message : loadAspiToDbStatus.running ? loadAspiToDbStatus.message : mergeAspiToIntermediateStatus.message}
            </p>
          </div>
        )}
        {(parseAspiStatus.error || normalizeAspiStatus.error || loadAspiToDbStatus.error || mergeAspiToIntermediateStatus.error) && (
          <div className="message error">
            <strong>Ошибка:</strong> {parseAspiStatus.error || normalizeAspiStatus.error || loadAspiToDbStatus.error || mergeAspiToIntermediateStatus.error}
          </div>
        )}
        {!parseAspiStatus.running && !normalizeAspiStatus.running && !loadAspiToDbStatus.running && !mergeAspiToIntermediateStatus.running && parseAspiStatus.progress === 100 && !parseAspiStatus.error && (
          <div className="message success">
            {parseAspiStatus.message || 'Парсинг завершён. Результаты в aspi/output/.'}
          </div>
        )}
        {!parseAspiStatus.running && !normalizeAspiStatus.running && !loadAspiToDbStatus.running && !mergeAspiToIntermediateStatus.running && normalizeAspiStatus.progress === 100 && !normalizeAspiStatus.error && (
          <div className="message success">
            {normalizeAspiStatus.message || 'Нормализация завершена. Файлы в aspi/output/ обновлены.'}
          </div>
        )}
        {!parseAspiStatus.running && !normalizeAspiStatus.running && !loadAspiToDbStatus.running && !mergeAspiToIntermediateStatus.running && loadAspiToDbStatus.progress === 100 && !loadAspiToDbStatus.error && (
          <div className="message success">
            {loadAspiToDbStatus.message || 'Данные загружены в таблицу timetable_aspi.'}
          </div>
        )}
        {!parseAspiStatus.running && !normalizeAspiStatus.running && !loadAspiToDbStatus.running && !mergeAspiToIntermediateStatus.running && mergeAspiToIntermediateStatus.progress === 100 && !mergeAspiToIntermediateStatus.error && (
          <div className="message success">
            {mergeAspiToIntermediateStatus.message || 'Расписание аспирантов добавлено в intermediate_timetable.'}
          </div>
        )}
      </div>
      )}

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
