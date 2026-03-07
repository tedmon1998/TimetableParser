import React, { useState, useEffect, useMemo, useRef } from 'react';
import axios from 'axios';
import * as XLSX from 'xlsx';
import './ScriptRunner.css';

interface ScriptStatus {
  running: boolean;
  progress: number;
  message: string;
  error: string | null;
  missing_fio?: string[];
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
  const [parseSpoStatus, setParseSpoStatus] = useState<ScriptStatus>({
    running: false,
    progress: 0,
    message: '',
    error: null
  });
  const [loadSpoToDbStatus, setLoadSpoToDbStatus] = useState<ScriptStatus>({
    running: false,
    progress: 0,
    message: '',
    error: null
  });
  const [mergeSpoToIntermediateStatus, setMergeSpoToIntermediateStatus] = useState<ScriptStatus>({
    running: false,
    progress: 0,
    message: '',
    error: null
  });
  const [migrateOldToNewStatus, setMigrateOldToNewStatus] = useState<ScriptStatus>({
    running: false,
    progress: 0,
    message: '',
    error: null
  });
  const [updateGroupDepartmentsStatus, setUpdateGroupDepartmentsStatus] = useState<ScriptStatus>({
    running: false,
    progress: 0,
    message: '',
    error: null
  });
  type SemesterInfo = { id: number; name: string; date_start?: string; date_end?: string };
  const [semesters, setSemesters] = useState<SemesterInfo[]>([]);
  const [migrateSemesterId, setMigrateSemesterId] = useState<number>(1);
  const [migrateClean, setMigrateClean] = useState(false);
  const [migrateDedupe, setMigrateDedupe] = useState(false);
  const [migrateStrict, setMigrateStrict] = useState(false);

  const [jsonPaste, setJsonPaste] = useState('');
  const [tableData, setTableData] = useState<Record<string, unknown>[] | null>(null);
  const [tableError, setTableError] = useState<string | null>(null);
  const [droppedFileName, setDroppedFileName] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [showIdColumns, setShowIdColumns] = useState(true);
  const [tableGlobalFilter, setTableGlobalFilter] = useState('');
  const [tableColumnFilters, setTableColumnFilters] = useState<Record<string, string>>({});

  const [unresolvedFioItems, setUnresolvedFioItems] = useState<string[]>([]);
  const [unresolvedParseItems, setUnresolvedParseItems] = useState<Array<{ type: string; file: string; specialty?: string; discipline?: string; day: string; para: string }>>([]);
  const [aspiReplacements, setAspiReplacements] = useState<Record<string, string>>({});
  const [aspiApplyLoading, setAspiApplyLoading] = useState(false);
  const [aspiApplyError, setAspiApplyError] = useState<string | null>(null);
  const [aspiUnresolvedModalOpen, setAspiUnresolvedModalOpen] = useState(false);
  const [aspiUnresolvedParseModalOpen, setAspiUnresolvedParseModalOpen] = useState(false);
  const [aspiErrorModalMessage, setAspiErrorModalMessage] = useState<string | null>(null);

  const [missingTeachersModalOpen, setMissingTeachersModalOpen] = useState(false);
  const [missingTeachersList, setMissingTeachersList] = useState<string[]>([]);

  const aspiAnyError =
    parseAspiStatus.error ||
    normalizeAspiStatus.error ||
    loadAspiToDbStatus.error ||
    mergeAspiToIntermediateStatus.error ||
    aspiApplyError ||
    null;

  type ScriptRunnerTab = 'bachelor_master' | 'aspi' | 'spo' | 'migration';

  const getInitialSubtab = (): ScriptRunnerTab => {
    const params = new URLSearchParams(window.location.search);
    const subtab = params.get('subtab');
    if (subtab === 'aspi') return 'aspi';
    if (subtab === 'spo') return 'spo';
    if (subtab === 'migration') return 'migration';
    return 'bachelor_master';
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

  const formatSemesterLabel = (s: SemesterInfo): string => {
    if (s.date_start && s.date_end) {
      const startYear = new Date(s.date_start).getFullYear();
      const endYear = new Date(s.date_end).getFullYear();
      if (!Number.isNaN(startYear) && !Number.isNaN(endYear)) {
        return `${s.name} (${startYear}–${endYear})`;
      }
    }
    return s.name;
  };

  const fetchUnresolvedFio = React.useCallback(async () => {
    try {
      const res = await axios.get<{ items?: string[] }>(`${API_BASE}/aspi/unresolved`);
      setUnresolvedFioItems(res.data?.items ?? []);
    } catch {
      setUnresolvedFioItems([]);
    }
  }, [API_BASE]);

  const fetchUnresolvedParse = React.useCallback(async () => {
    try {
      const res = await axios.get<{ items?: Array<{ type: string; file: string; specialty?: string; discipline?: string; day: string; para: string }> }>(`${API_BASE}/aspi/unresolved-parse`);
      setUnresolvedParseItems(res.data?.items ?? []);
    } catch {
      setUnresolvedParseItems([]);
    }
  }, [API_BASE]);

  useEffect(() => {
    if (activeTab === 'aspi') {
      fetchUnresolvedFio();
      fetchUnresolvedParse();
    }
  }, [activeTab, fetchUnresolvedFio, fetchUnresolvedParse]);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await axios.get<SemesterInfo[]>(`${API_BASE}/semesters`);
        const list = res.data ?? [];
        setSemesters(list);
        if (list.length > 0) {
          setMigrateSemesterId((prev) => (list.some((s) => s.id === prev) ? prev : list[0].id));
        }
      } catch {
        setSemesters([]);
      }
    };
    load();
  }, [API_BASE]);

  useEffect(() => {
    if (aspiUnresolvedModalOpen) fetchUnresolvedFio();
  }, [aspiUnresolvedModalOpen, fetchUnresolvedFio]);

  useEffect(() => {
    if (aspiUnresolvedParseModalOpen) fetchUnresolvedParse();
  }, [aspiUnresolvedParseModalOpen, fetchUnresolvedParse]);

  useEffect(() => {
    const err = parseAspiStatus.error || normalizeAspiStatus.error || loadAspiToDbStatus.error || mergeAspiToIntermediateStatus.error || null;
    if (err && activeTab === 'aspi') setAspiErrorModalMessage(err);
  }, [parseAspiStatus.error, normalizeAspiStatus.error, loadAspiToDbStatus.error, mergeAspiToIntermediateStatus.error, activeTab]);

  useEffect(() => {
    if (activeTab === 'aspi' && !normalizeAspiStatus.running && normalizeAspiStatus.progress === 100) {
      fetchUnresolvedFio();
    }
  }, [activeTab, normalizeAspiStatus.running, normalizeAspiStatus.progress, fetchUnresolvedFio]);

  useEffect(() => {
    if (activeTab === 'aspi' && !parseAspiStatus.running && parseAspiStatus.progress === 100) {
      fetchUnresolvedParse();
    }
  }, [activeTab, parseAspiStatus.running, parseAspiStatus.progress, fetchUnresolvedParse]);

  const handleAspiApplyReplacements = React.useCallback(async () => {
    const replacements: Record<string, string> = {};
    unresolvedFioItems.forEach((short) => {
      const to = (aspiReplacements[short] ?? '').trim();
      if (to) replacements[short] = to;
    });
    if (Object.keys(replacements).length === 0) {
      setAspiApplyError('Укажите «Заменить на» хотя бы для одного ФИО.');
      return;
    }
    setAspiApplyError(null);
    setAspiApplyLoading(true);
    try {
      const res = await axios.post<{ items?: string[]; message?: string; error?: string }>(
        `${API_BASE}/aspi/apply-fio-replacements`,
        { replacements }
      );
      if (res.data?.error) {
        setAspiApplyError(res.data.error);
        setAspiErrorModalMessage(res.data.error);
      } else {
        const newItems = res.data?.items ?? [];
        setUnresolvedFioItems(newItems);
        setAspiReplacements((prev) => {
          const next = { ...prev };
          Object.keys(replacements).forEach((k) => delete next[k]);
          return next;
        });
        if (newItems.length === 0) setAspiUnresolvedModalOpen(false);
      }
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } }; message?: string })?.response?.data?.error
        || (err as { message?: string })?.message
        || 'Ошибка дообработки';
      setAspiApplyError(String(msg));
      setAspiErrorModalMessage(String(msg));
    } finally {
      setAspiApplyLoading(false);
    }
  }, [API_BASE, unresolvedFioItems, aspiReplacements]);

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
      if (parseSpoStatus.running) {
        fetchStatus('parse_spo', setParseSpoStatus);
      }
      if (loadSpoToDbStatus.running) {
        fetchStatus('load_spo_to_db', setLoadSpoToDbStatus);
      }
      if (mergeSpoToIntermediateStatus.running) {
        fetchStatus('merge_spo_to_intermediate', setMergeSpoToIntermediateStatus);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [parseStatus.running, cleanStatus.running, loadTimetableToDbStatus.running, mergeTimetableStatus.running, processTimetableStatus.running, parseAspiStatus.running, normalizeAspiStatus.running, loadAspiToDbStatus.running, mergeAspiToIntermediateStatus.running, parseSpoStatus.running, loadSpoToDbStatus.running, mergeSpoToIntermediateStatus.running]);

  const fetchStatus = async (scriptName: string, setStatus: React.Dispatch<React.SetStateAction<ScriptStatus>>) => {
    try {
      const response = await axios.get(`${API_BASE}/status/${scriptName}`);
      setStatus(response.data);
    } catch (error) {
      console.error(`Error fetching status for ${scriptName}:`, error);
    }
  };

  const runMigrationScript = React.useCallback(async (options?: { cleanOverrideOnly?: boolean }): Promise<ScriptStatus> => {
    const cleanOverrideOnly = options?.cleanOverrideOnly ?? false;
    setMigrateOldToNewStatus({ running: true, progress: 0, message: 'Запуск...', error: null });
    try {
      await axios.post(`${API_BASE}/run/migrate_old_to_new`, {
        semester_id: migrateSemesterId,
        clean: !cleanOverrideOnly && migrateClean,
        dedupe: migrateDedupe,
        strict: migrateStrict,
        clean_override_only: cleanOverrideOnly,
      });
    } catch (err: any) {
      const msg = err.response?.data?.error ?? err.message ?? 'Ошибка запроса';
      setMigrateOldToNewStatus({ running: false, progress: 0, message: '', error: msg });
      return { running: false, progress: 0, message: '', error: msg };
    }
    return new Promise<ScriptStatus>((resolve) => {
      const statusInterval = setInterval(async () => {
        try {
          const response = await axios.get(`${API_BASE}/status/migrate_old_to_new`);
          const status: ScriptStatus = response.data;
          setMigrateOldToNewStatus(status);
          if (!status.running) {
            clearInterval(statusInterval);
            resolve(status); 
          }
        } catch {
          clearInterval(statusInterval);
          resolve(migrateOldToNewStatus);
        }
      }, 5000);
    });
  }, [API_BASE, migrateSemesterId, migrateClean, migrateDedupe, migrateStrict]);

  const runUpdateGroupDepartments = async () => {
    setUpdateGroupDepartmentsStatus({ running: true, progress: 0, message: 'Запуск...', error: null });
    try {
      await axios.post(`${API_BASE}/run/update_group_departments`);
    } catch (err: any) {
      const msg = err.response?.data?.error ?? err.message ?? 'Ошибка запроса';
      setUpdateGroupDepartmentsStatus({ running: false, progress: 0, message: '', error: msg });
      return;
    }
    const statusInterval = setInterval(async () => {
      try {
        const response = await axios.get(`${API_BASE}/status/update_group_departments`);
        const status: ScriptStatus = response.data;
        setUpdateGroupDepartmentsStatus(status);
        if (!status.running) clearInterval(statusInterval);
      } catch {
        clearInterval(statusInterval);
      }
    }, 2000);
  };

  const parseJsonToTable = (raw: string): Record<string, unknown>[] | null => {
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return parsed as Record<string, unknown>[];
      if (parsed && typeof parsed === 'object') return [parsed as Record<string, unknown>];
      return null;
    } catch {
      return null;
    }
  };

  /** Рекурсивно разворачивает вложенные объекты в плоские ключи с префиксом (group_direction_name и т.д.) */
  const flattenObject = (obj: Record<string, unknown>, prefix = ''): Record<string, unknown> => {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(obj)) {
      const key = prefix ? `${prefix}_${k}` : k;
      if (v !== null && typeof v === 'object' && !Array.isArray(v) && !(v instanceof Date)) {
        Object.assign(out, flattenObject(v as Record<string, unknown>, key));
      } else {
        out[key] = v;
      }
    }
    return out;
  };

  /** Если данные в формате { group, items, semester_id }, разворачивает в одну строку на элемент items с плоскими полями */
  const normalizeTableData = (data: Record<string, unknown>[]): Record<string, unknown>[] => {
    if (data.length !== 1) return data;
    const root = data[0];
    const items = root.items;
    const group = root.group;
    if (!Array.isArray(items) || !group || typeof group !== 'object') return data;
    const flatGroup = flattenObject(group as Record<string, unknown>, 'group');
    return items.map((item: Record<string, unknown>) => {
      const flatItem = flattenObject(item);
      return {
        ...flatGroup,
        ...flatItem,
        ...(root.semester_id !== undefined && { semester_id: root.semester_id }),
      };
    });
  };

  const showPastedJson = () => {
    setTableError(null);
    setDroppedFileName(null);
    const trimmed = jsonPaste.trim();
    if (!trimmed) {
      setTableData(null);
      return;
    }
    let data = parseJsonToTable(trimmed);
    if (data) {
      data = normalizeTableData(data);
      setTableData(data);
    } else {
      setTableError('Неверный JSON. Ожидается массив объектов или один объект.');
      setTableData(null);
    }
  };

  const handleMigrationFile = (file: File) => {
    setTableError(null);
    setDroppedFileName(file.name);
    const isJson = file.name.toLowerCase().endsWith('.json');
    const isExcel = /\.(xlsx|xls)$/i.test(file.name);
    const reader = new FileReader();
    if (isJson) {
      reader.onload = () => {
        const text = reader.result as string;
        let data = parseJsonToTable(text);
        if (data) {
          data = normalizeTableData(data);
          setTableData(data);
        } else {
          setTableError('В файле не найден валидный JSON (массив объектов или объект).');
          setTableData(null);
        }
      };
      reader.readAsText(file, 'UTF-8');
    } else if (isExcel) {
      reader.onload = () => {
        try {
          const data = reader.result;
          if (!data || !(data instanceof ArrayBuffer)) return;
          const wb = XLSX.read(data, { type: 'array' });
          const ws = wb.Sheets[wb.SheetNames[0]];
          const rows = (XLSX.utils as unknown as { sheet_to_json: (ws: unknown) => Record<string, unknown>[] }).sheet_to_json(ws);
          setTableData(rows);
        } catch (e) {
          setTableError('Не удалось прочитать Excel: ' + (e instanceof Error ? e.message : String(e)));
          setTableData(null);
        }
      };
      reader.readAsArrayBuffer(file);
    } else {
      setTableError('Поддерживаются только файлы .json, .xlsx, .xls');
      setTableData(null);
    }
  };

  const onMigrationDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer?.files?.[0];
    if (file) handleMigrationFile(file);
  };

  const onMigrationDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };
  const onMigrationDragLeave = () => setDragOver(false);

  const downloadMigrationExcel = () => {
    if (!tableData || tableData.length === 0) return;
    const cols = migrationDisplayedColumns;
    const rows = tableData.map((row) => {
      const out: Record<string, unknown> = {};
      cols.forEach((col) => { out[col] = row[col]; });
      return out;
    });
    const utils = XLSX.utils as unknown as { json_to_sheet: (data: Record<string, unknown>[]) => unknown; book_new: () => unknown; book_append_sheet: (wb: unknown, ws: unknown, name: string) => void };
    const ws = utils.json_to_sheet(rows);
    const wb = utils.book_new();
    utils.book_append_sheet(wb, ws, 'Data');
    const name = droppedFileName ? droppedFileName.replace(/\.[^.]+$/, '') + '_export.xlsx' : 'export.xlsx';
    (XLSX as unknown as { writeFile: (wb: unknown, filename: string) => void }).writeFile(wb, name);
  };

  const migrationTableColumns = tableData?.length
    ? Array.from(new Set(tableData.flatMap((row) => Object.keys(row)))).sort()
    : [];

  const migrationDisplayedColumns = useMemo(
    () =>
      showIdColumns
        ? migrationTableColumns
        : migrationTableColumns.filter((col) => col === 'id' || !col.endsWith('_id')),
    [migrationTableColumns, showIdColumns]
  );

  const migrationCellValue = (val: unknown): string => {
    if (val == null) return '';
    if (typeof val === 'object') return JSON.stringify(val);
    return String(val);
  };

  type MigrationSort = { field: string; direction: 'asc' | 'desc' } | null;
  const [migrationSort, setMigrationSort] = useState<MigrationSort>(null);

  const filteredTableData = useMemo(() => {
    if (!tableData) return null;
    let rows = tableData;
    const global = tableGlobalFilter.trim().toLowerCase();
    if (global) {
      rows = rows.filter((row) =>
        migrationDisplayedColumns.some((col) =>
          migrationCellValue(row[col]).toLowerCase().includes(global)
        )
      );
    }
    const activeColumnFilters = Object.entries(tableColumnFilters).filter(
      ([, v]) => v.trim() !== ''
    );
    if (activeColumnFilters.length) {
      rows = rows.filter((row) =>
        activeColumnFilters.every(([col, value]) =>
          migrationCellValue(row[col]).toLowerCase().includes(value.trim().toLowerCase())
        )
      );
    }
    if (migrationSort) {
      const { field, direction } = migrationSort;
      const sign = direction === 'asc' ? 1 : -1;
      rows = [...rows].sort((a, b) => {
        const av = migrationCellValue(a[field]);
        const bv = migrationCellValue(b[field]);
        return av.localeCompare(bv, 'ru') * sign;
      });
    }
    return rows;
  }, [tableData, tableGlobalFilter, tableColumnFilters, migrationDisplayedColumns, migrationSort]);

  const runScript = (scriptName: 'parse_timetable' | 'clean_audiences' | 'load_timetable_to_db' | 'merge_timetable' | 'process_timetable' | 'parse_aspi' | 'normalize_aspi' | 'load_aspi_to_db' | 'merge_aspi_to_intermediate' | 'parse_spo' | 'load_spo_to_db' | 'merge_spo_to_intermediate'): Promise<ScriptStatus> => {
    const setStatus = scriptName === 'parse_timetable' ? setParseStatus
      : scriptName === 'clean_audiences' ? setCleanStatus
        : scriptName === 'load_timetable_to_db' ? setLoadTimetableToDbStatus
          : scriptName === 'merge_timetable' ? setMergeTimetableStatus
            : scriptName === 'process_timetable' ? setProcessTimetableStatus
              : scriptName === 'parse_aspi' ? setParseAspiStatus
                : scriptName === 'normalize_aspi' ? setNormalizeAspiStatus
                  : scriptName === 'load_aspi_to_db' ? setLoadAspiToDbStatus
                    : scriptName === 'merge_aspi_to_intermediate' ? setMergeAspiToIntermediateStatus
                      : scriptName === 'parse_spo' ? setParseSpoStatus
                        : scriptName === 'load_spo_to_db' ? setLoadSpoToDbStatus
                          : setMergeSpoToIntermediateStatus;

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
                : scriptName === 'parse_spo' ? `${API_BASE}/run/parse_spo`
                  : scriptName === 'load_spo_to_db' ? `${API_BASE}/run/load_spo_to_db`
                  : scriptName === 'merge_spo_to_intermediate' ? `${API_BASE}/run/merge_spo_to_intermediate`
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
                if (scriptName === 'process_timetable' && (status.missing_fio?.length ?? 0) > 0) {
                  setMissingTeachersList(status.missing_fio ?? []);
                  setMissingTeachersModalOpen(true);
                }
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

  const [pipelineSpoRunning, setPipelineSpoRunning] = useState(false);
  const runAllSpoPipeline = async () => {
    if (pipelineSpoRunning) return;
    setPipelineSpoRunning(true);
    try {
      await runScript('parse_spo');
      await runScript('load_spo_to_db');
    } catch {
      // Ошибка уже отображена в статусе шага
    } finally {
      setPipelineSpoRunning(false);
    }
  };

  const pipelineSpoDisabled = parseSpoStatus.running || loadSpoToDbStatus.running || mergeSpoToIntermediateStatus.running || pipelineSpoRunning;

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
        <button
          type="button"
          className={`script-runner-tab ${activeTab === 'spo' ? 'active' : ''}`}
          onClick={() => setActiveTab('spo')}
        >
          СПО (колледж)
        </button>
        <button
          type="button"
          className={`script-runner-tab ${activeTab === 'migration' ? 'active' : ''}`}
          onClick={() => setActiveTab('migration')}
        >
          Миграция в новую архитектуру
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

      {missingTeachersModalOpen && (
        <div className="aspi-unresolved-overlay" onClick={() => setMissingTeachersModalOpen(false)}>
          <div className="aspi-unresolved-modal" onClick={(e) => e.stopPropagation()}>
            <div className="aspi-unresolved-modal-header">
              <h3>Нераспознанные ФИО (занятость преподавателей)</h3>
              <button type="button" className="aspi-unresolved-close" onClick={() => setMissingTeachersModalOpen(false)} aria-label="Закрыть">×</button>
            </div>
            <p className="aspi-unresolved-hint">Эти ФИО не найдены в справочнике (info/teacher_all.json). Список сохранён в error/missing_teachers.json.</p>
            <div className="aspi-unresolved-table-wrap">
              <ul className="missing-teachers-list">
                {missingTeachersList.map((fio, idx) => (
                  <li key={idx}>{fio}</li>
                ))}
              </ul>
            </div>
            <div className="aspi-unresolved-modal-footer">
              <button type="button" className="button button-primary" onClick={() => setMissingTeachersModalOpen(false)}>Закрыть</button>
            </div>
          </div>
        </div>
      )}
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

        <button
          type="button"
          className="button aspi-unresolved-trigger"
          onClick={() => {
            setAspiApplyError(null);
            setAspiErrorModalMessage(null);
            setAspiUnresolvedModalOpen(true);
          }}
        >
          {unresolvedFioItems.length > 0
            ? `Нераспознанные ФИО (${unresolvedFioItems.length}) — исправить`
            : 'Нераспознанные ФИО (загрузить список)'}
        </button>
        <button
          type="button"
          style={{marginLeft: '10px'}}
          className="button aspi-unresolved-trigger"
          onClick={() => {
            setAspiUnresolvedParseModalOpen(true);
            fetchUnresolvedParse();
          }}
        >
          {unresolvedParseItems.length > 0
            ? `Нераспознанные записи парсинга (${unresolvedParseItems.length})`
            : 'Нераспознанные записи парсинга (загрузить список)'}
        </button>
        {aspiAnyError && (
          <button
            type="button"
            className="button aspi-error-trigger"
            onClick={() => setAspiErrorModalMessage(aspiAnyError)}
          >
            Показать ошибку
          </button>
        )}
      </div>
      )}

      {activeTab === 'spo' && (
      <div className="card pipeline-card">
        <h2>Парсер расписания СПО (spo/parse_spo.py)</h2>
        <p className="description">
          Положите Excel-файлы (.xlsx) в папку <code>spo/spo/</code> и запустите парсер. Результат сохраняется в <code>spo/output/_all.json</code>.
          Структура: курс в заголовке, время в отдельной колонке, подгруппы по колонкам (П1/П2/П3 или «бригада 1/2/3»),
          для каждой пары 3 строки: ФИО → дисциплина → аудитория.
        </p>
        <div className="pipeline-actions">
          <button
            className="button"
            onClick={() => runScript('parse_spo')}
            disabled={pipelineSpoDisabled}
          >
            {parseSpoStatus.running ? 'Выполняется...' : 'Запустить парсер СПО'}
          </button>
          <button
            className="button"
            onClick={() => runScript('load_spo_to_db')}
            disabled={pipelineSpoDisabled}
          >
            {loadSpoToDbStatus.running ? 'Выполняется...' : 'Добавить в БД (timetable_spo)'}
          </button>
          <button
            className="button"
            onClick={() => runScript('merge_spo_to_intermediate')}
            disabled={pipelineSpoDisabled}
          >
            {mergeSpoToIntermediateStatus.running ? 'Выполняется...' : 'Добавить к intermediate'}
          </button>
          <button
            className="button button-primary"
            onClick={runAllSpoPipeline}
            disabled={pipelineSpoDisabled}
          >
            {pipelineSpoRunning ? 'Выполняется цепочка...' : 'Запустить всё по очереди'}
          </button>
        </div>
        {(parseSpoStatus.running || loadSpoToDbStatus.running || mergeSpoToIntermediateStatus.running || pipelineSpoRunning) && (
          <div className="progress-container">
            <div className="progress-bar">
              <div
                className="progress-bar-fill"
                style={{ width: `${parseSpoStatus.running ? parseSpoStatus.progress : loadSpoToDbStatus.progress}%` }}
              >
                {parseSpoStatus.running ? parseSpoStatus.progress : loadSpoToDbStatus.progress}%
              </div>
            </div>
            <p className="progress-message progress-message--short">
              {parseSpoStatus.running ? parseSpoStatus.message : loadSpoToDbStatus.running ? loadSpoToDbStatus.message : mergeSpoToIntermediateStatus.message}
            </p>
          </div>
        )}
        {(parseSpoStatus.error || loadSpoToDbStatus.error || mergeSpoToIntermediateStatus.error) && (
          <div className="message error">
            <strong>Ошибка:</strong> {parseSpoStatus.error || loadSpoToDbStatus.error || mergeSpoToIntermediateStatus.error}
          </div>
        )}
        {!parseSpoStatus.running && !loadSpoToDbStatus.running && parseSpoStatus.progress === 100 && !parseSpoStatus.error && (
          <div className="message success">
            {parseSpoStatus.message || 'Парсинг завершён. Результаты в spo/output/_all.json.'}
          </div>
        )}
        {!parseSpoStatus.running && !loadSpoToDbStatus.running && loadSpoToDbStatus.progress === 100 && !loadSpoToDbStatus.error && (
          <div className="message success">
            {loadSpoToDbStatus.message || 'Данные загружены в таблицу timetable_spo.'}
          </div>
        )}
        {!mergeSpoToIntermediateStatus.running && mergeSpoToIntermediateStatus.progress === 100 && !mergeSpoToIntermediateStatus.error && (
          <div className="message success">
            {mergeSpoToIntermediateStatus.message || 'Расписание СПО добавлено в intermediate_timetable.'}
          </div>
        )}
      </div>
      )}

      {activeTab === 'migration' && (
      <>
      <div className="card">
        <h2>Миграция БД (schedule → новая схема)</h2>
        <p className="description">
          Скрипт db_migration_old_db_to_new.py: перенос данных из таблицы schedule в student_group, schedule_override и обновление teacher.is_external. Справочники (teacher, subject, room, institute, direction, timeslot) не создаются — только поиск по существующим.
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center', marginBottom: '1rem' }}>
          <label>
            Семестр:{' '}
            <select
              value={migrateSemesterId}
              onChange={(e) => setMigrateSemesterId(Number(e.target.value))}
              disabled={migrateOldToNewStatus.running}
            >
              {semesters.length === 0 ? <option value={1}>ID: 1</option> : null}
              {semesters.map((s) => (
                <option key={s.id} value={s.id}>{formatSemesterLabel(s)}</option>
              ))}
            </select>
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <input type="checkbox" checked={migrateClean} onChange={(e) => setMigrateClean(e.target.checked)} disabled={migrateOldToNewStatus.running} />
            Очистить перед миграцией (schedule_override, student_group)
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <input type="checkbox" checked={migrateDedupe} onChange={(e) => setMigrateDedupe(e.target.checked)} disabled={migrateOldToNewStatus.running} />
            Убрать дубликаты
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <input type="checkbox" checked={migrateStrict} onChange={(e) => setMigrateStrict(e.target.checked)} disabled={migrateOldToNewStatus.running} />
            Строгий режим (ошибка при отсутствии timeslot)
          </label>
        </div>
        <button
          className="button"
          onClick={() => runMigrationScript()}
          disabled={migrateOldToNewStatus.running}
        >
          {migrateOldToNewStatus.running ? 'Выполняется...' : 'Запустить миграцию'}
        </button>
        <button
          className="button"
          style={{ marginLeft: '0.75rem' }}
          onClick={() => runMigrationScript({ cleanOverrideOnly: true })}
          disabled={migrateOldToNewStatus.running}
        >
          {migrateOldToNewStatus.running ? 'Выполняется...' : 'Только schedule_override (очистить и мигрировать)'}
        </button>
        {migrateOldToNewStatus.running && (
          <div className="progress-container" style={{ marginTop: '0.5rem' }}>
            <div className="progress-bar">
              <div className="progress-bar-fill" style={{ width: `${migrateOldToNewStatus.progress}%` }}>
                {migrateOldToNewStatus.progress}%
              </div>
            </div>
            <p className="progress-message">{migrateOldToNewStatus.message}</p>
          </div>
        )}
        {migrateOldToNewStatus.error && (
          <div className="message error" style={{ marginTop: '0.5rem' }}>
            <strong>Ошибка:</strong> {migrateOldToNewStatus.error}
          </div>
        )}
        {!migrateOldToNewStatus.running && migrateOldToNewStatus.progress === 100 && !migrateOldToNewStatus.error && (
          <div className="message success" style={{ marginTop: '0.5rem' }}>
            {migrateOldToNewStatus.message || 'Миграция завершена.'}
          </div>
        )}
      </div>

      <div className="card">
        <h2>Кафедры групп из файла занятости</h2>
        <p className="description">
          Берёт группы и кафедры из файла <code>input/Zanyatost prepodavateley_ vesenniy semestr 2025-2026-13-02-26.xlsx</code> (или другого файла по маске) и обновляет в таблице <code>student_group</code> поле <code>department_id</code> (идентификатор кафедры).
        </p>
        <button
          className="button"
          onClick={() => runUpdateGroupDepartments()}
          disabled={updateGroupDepartmentsStatus.running}
        >
          {updateGroupDepartmentsStatus.running ? 'Выполняется...' : 'Обновить кафедры групп'}
        </button>
        {updateGroupDepartmentsStatus.running && (
          <div className="progress-container" style={{ marginTop: '0.5rem' }}>
            <div className="progress-bar">
              <div className="progress-bar-fill" style={{ width: `${updateGroupDepartmentsStatus.progress}%` }}>
                {updateGroupDepartmentsStatus.progress}%
              </div>
            </div>
            <p className="progress-message">{updateGroupDepartmentsStatus.message}</p>
          </div>
        )}
        {updateGroupDepartmentsStatus.error && (
          <div className="message error" style={{ marginTop: '0.5rem' }}>
            <strong>Ошибка:</strong> {updateGroupDepartmentsStatus.error}
          </div>
        )}
        {!updateGroupDepartmentsStatus.running && updateGroupDepartmentsStatus.progress === 100 && !updateGroupDepartmentsStatus.error && (
          <div className="message success" style={{ marginTop: '0.5rem' }}>
            {updateGroupDepartmentsStatus.message || 'Кафедры групп обновлены.'}
          </div>
        )}
      </div>

      <div className="card migration-json-card">
        <h2>Просмотр JSON / Excel как таблица</h2>
        <p className="description">
          Вставьте JSON (массив объектов) или перетащите сюда файл .json или .xlsx — данные отобразятся в виде таблицы (столбцы = ключи, строки = записи). Можно скачать результат в Excel в том же формате.
        </p>
        <div className="migration-json-row">
          <div className="migration-json-inputs">
            <textarea
              className="migration-json-textarea"
              placeholder='Вставьте JSON, например: [{"id": 1, "name": "..."}, ...]'
              value={jsonPaste}
              onChange={(e) => setJsonPaste(e.target.value)}
              rows={4}
            />
            <button type="button" className="button" onClick={showPastedJson}>
              Показать таблицу
            </button>
          </div>
          <input
            type="file"
            accept=".json,.xlsx,.xls"
            className="migration-file-input"
            id="migration-file-input"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleMigrationFile(f);
              e.target.value = '';
            }}
          />
          <label htmlFor="migration-file-input" className="migration-drop-label">
            <div
              className={`migration-drop-zone ${dragOver ? 'drag-over' : ''}`}
              onDrop={onMigrationDrop}
              onDragOver={onMigrationDragOver}
              onDragLeave={onMigrationDragLeave}
            >
              или перетащите сюда файл .json или .xlsx (или нажмите для выбора)
            </div>
          </label>
        </div>

        {tableError && (
          <div className="message error" style={{ marginTop: '1rem' }}>{tableError}</div>
        )}
        {droppedFileName && tableData && (
          <p className="description" style={{ marginTop: '0.5rem', marginBottom: 0 }}>
            Загружен файл: <strong>{droppedFileName}</strong>. Показано на сайте ниже.
          </p>
        )}
        {filteredTableData && filteredTableData.length > 0 && (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', flex: '1 1 220px' }}>
                <span style={{ whiteSpace: 'nowrap' }}>Поиск по таблице:</span>
                <input
                  type="text"
                  className="group-search-input"
                  style={{ maxWidth: '260px' }}
                  placeholder="Фильтр по всем колонкам"
                  value={tableGlobalFilter}
                  onChange={(e) => setTableGlobalFilter(e.target.value)}
                />
              </label>
              <label className="migration-table-toggle" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <input
                  type="checkbox"
                  checked={showIdColumns}
                  onChange={(e) => setShowIdColumns(e.target.checked)}
                />
                Показывать колонки с id (group_id, room_id и т.д.; основная id всегда видна)
              </label>
            </div>
            <div className="migration-table-wrap">
              <table className="migration-table">
                <thead>
                  <tr>
                    {migrationDisplayedColumns.map((col) => (
                      <th key={col}>{col}</th>
                    ))}
                  </tr>
                  <tr>
                    {migrationDisplayedColumns.map((col) => (
                      <th key={col}>
                        <input
                          type="text"
                          placeholder="фильтр"
                          value={tableColumnFilters[col] ?? ''}
                          onChange={(e) =>
                            setTableColumnFilters((prev) => ({ ...prev, [col]: e.target.value }))
                          }
                          style={{ width: '100%', boxSizing: 'border-box', fontSize: '0.75rem' }}
                        />
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredTableData.map((row, idx) => (
                    <tr key={idx}>
                      {migrationDisplayedColumns.map((col) => (
                        <td key={col}>{migrationCellValue(row[col])}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <button type="button" className="button button-primary" onClick={downloadMigrationExcel} style={{ marginTop: '0.75rem' }}>
              {droppedFileName ? 'Скачать Excel (в том же формате)' : 'Скачать Excel'}
            </button>
          </>
        )}
        {tableData && (!filteredTableData || filteredTableData.length === 0) && !tableError && (
          <p className="description" style={{ marginTop: '1rem' }}>Нет данных для отображения (пустой массив).</p>
        )}
      </div>
      </>
      )}

      {aspiErrorModalMessage && (
        <div className="aspi-unresolved-overlay" onClick={() => setAspiErrorModalMessage(null)}>
          <div className="aspi-error-modal" onClick={(e) => e.stopPropagation()}>
            <div className="aspi-unresolved-modal-header">
              <h3>Ошибка</h3>
              <button type="button" className="aspi-unresolved-close" onClick={() => setAspiErrorModalMessage(null)} aria-label="Закрыть">×</button>
            </div>
            <div className="aspi-error-body">
              <pre className="aspi-error-text">{aspiErrorModalMessage}</pre>
            </div>
            <div className="aspi-unresolved-modal-footer">
              <button type="button" className="button" onClick={() => { setAspiErrorModalMessage(null); setAspiUnresolvedModalOpen(true); }}>
                Открыть нераспознанные ФИО
              </button>
              <button type="button" className="button button-primary" onClick={() => setAspiErrorModalMessage(null)}>
                Закрыть
              </button>
            </div>
          </div>
        </div>
      )}

      {aspiUnresolvedParseModalOpen && (
        <div className="aspi-unresolved-overlay" onClick={() => setAspiUnresolvedParseModalOpen(false)}>
          <div className="aspi-unresolved-modal" onClick={(e) => e.stopPropagation()}>
            <div className="aspi-unresolved-modal-header">
              <h3>Нераспознанные записи парсинга</h3>
              <button type="button" className="aspi-unresolved-close" onClick={() => setAspiUnresolvedParseModalOpen(false)} aria-label="Закрыть">×</button>
            </div>
            <p className="aspi-unresolved-hint">Записи для ручной проверки: группа не извлечена из специальности или дисциплина похожа на обрыв. Проверьте в исходном .docx и при необходимости исправьте данные вручную.</p>
            <div className="aspi-unresolved-table-wrap">
              <table className="aspi-unresolved-table">
                <thead>
                  <tr>
                    <th>Тип</th>
                    <th>Файл</th>
                    <th>Специальность / Дисциплина</th>
                    <th>День</th>
                    <th>Пара</th>
                  </tr>
                </thead>
                <tbody>
                  {unresolvedParseItems.map((item, idx) => (
                    <tr key={idx}>
                      <td>{item.type === 'group_not_extracted' ? 'Группа не извлечена' : 'Обрыв дисциплины'}</td>
                      <td>{item.file}</td>
                      <td className="aspi-unresolved-fio-cell">{(item.specialty ?? item.discipline) ?? '—'}</td>
                      <td>{item.day}</td>
                      <td>{item.para}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {unresolvedParseItems.length === 0 && <p className="aspi-unresolved-hint">Нет записей для проверки или загрузите список после парсинга.</p>}
            <div className="aspi-unresolved-modal-footer">
              <button type="button" className="button button-primary" onClick={() => setAspiUnresolvedParseModalOpen(false)}>Закрыть</button>
            </div>
          </div>
        </div>
      )}

      {aspiUnresolvedModalOpen && (
        <div className="aspi-unresolved-overlay" onClick={() => setAspiUnresolvedModalOpen(false)}>
          <div className="aspi-unresolved-modal" onClick={(e) => e.stopPropagation()}>
            <div className="aspi-unresolved-modal-header">
              <h3>Нераспознанные ФИО</h3>
              <button type="button" className="aspi-unresolved-close" onClick={() => setAspiUnresolvedModalOpen(false)} aria-label="Закрыть">×</button>
            </div>
            <p className="aspi-unresolved-hint">Укажите правильный вариант для замены и нажмите «Запустить дообработку».</p>
            <div className="aspi-unresolved-table-wrap">
              <table className="aspi-unresolved-table">
                <thead>
                  <tr>
                    <th>Найдено (неверно)</th>
                    <th>Правильный вариант</th>
                  </tr>
                </thead>
                <tbody>
                  {unresolvedFioItems.map((short) => (
                    <tr key={short}>
                      <td className="aspi-unresolved-fio-cell">{short}</td>
                      <td>
                        <input
                          type="text"
                          className="aspi-unresolved-replace"
                          placeholder="Введите полное ФИО"
                          value={aspiReplacements[short] ?? ''}
                          onChange={(e) => setAspiReplacements((prev) => ({ ...prev, [short]: e.target.value }))}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {aspiApplyError && <div className="message error">{aspiApplyError}</div>}
            <div className="aspi-unresolved-modal-footer">
              <button
                type="button"
                className="button button-primary"
                onClick={handleAspiApplyReplacements}
                disabled={aspiApplyLoading}
              >
                {aspiApplyLoading ? 'Дообработка...' : 'Запустить дообработку'}
              </button>
            </div>
          </div>
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
