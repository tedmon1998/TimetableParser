import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import axios from 'axios';
import * as XLSX from 'xlsx';
import './ScriptRunner.css';
import './DatabaseView.css';

interface ScriptStatus {
  running: boolean;
  progress: number;
  message: string;
  error: string | null;
  missing_fio?: string[];
  /** Полный лог миграции (консоль + при успехе — отчёт schedule -> override) */
  output_log?: string;
  /** Строки отчёта для таблицы (как просмотр расписания в БД) */
  report_rows?: Record<string, unknown>[];
  /** На сервере есть output/migration_report_web.txt — листать через /api/migration_report_lines */
  full_report_available?: boolean;
}

/** Колонки таблицы миграции (совпадают с ключами JSON из db_migration_old_db_to_new.py) */
const MIGRATION_REPORT_COLUMNS: { key: string; label: string }[] = [
  { key: 'day_of_week', label: 'День' },
  { key: 'pair_number', label: 'Пара' },
  { key: 'subject_name', label: 'Предмет' },
  { key: 'audience', label: 'Аудитория' },
  { key: 'group_name', label: 'Группа' },
  { key: 'week_type', label: 'Неделя' },
  { key: 'fio', label: 'ФИО' },
  { key: 'subgroup', label: 'п/г' },
  { key: 'course', label: 'Курс' },
  { key: 'schedule_id', label: 'ID schedule' },
  { key: 'schedule_override_id', label: 'ID override' },
  { key: 'lecture_type', label: 'Тип' },
  { key: 'duration_pairs', label: 'Длит. пар' },
  { key: 'institute', label: 'Институт' },
  { key: 'direction', label: 'Направление' },
  { key: 'department', label: 'Кафедра' },
  { key: 'subject_id', label: 'subject_id' },
  { key: 'teacher_id', label: 'teacher_id' },
  { key: 'teacher_fio_db', label: 'ФИО в teacher' },
  { key: 'teacher_reason', label: 'Совп. ФИО' },
  { key: 'subject_reason', label: 'Совп. предмет' },
  { key: 'ov_group_id', label: 'ov group_id' },
  { key: 'ov_weekday', label: 'ov день' },
  { key: 'ov_week_type', label: 'ov неделя' },
  { key: 'ov_class_type', label: 'ov тип' },
  { key: 'ov_timeslot_no', label: 'ov пара' },
  { key: 'ov_subgroup_count', label: 'ov число п/г' },
  { key: 'ov_subgroup_no', label: 'ov п/г (no)' },
  { key: 'ov_subject_id', label: 'ov subject_id' },
  { key: 'ov_teacher_id', label: 'ov teacher_id' },
  { key: 'sot_will_link', label: 'Связь s_o_t' },
];

/** Видимы по умолчанию (остальные — через меню «Колонки») */
const MIGRATION_REPORT_DEFAULT_VISIBLE_KEYS = new Set([
  'day_of_week',
  'pair_number',
  'subject_name',
  'audience',
  'group_name',
  'week_type',
  'fio',
  'subgroup',
  'course',
]);

const MIGRATION_REPORT_PAGE_SIZE = 50;

/** Размер «страницы» при запросе фрагмента .txt отчёта с сервера */
const MIGRATION_TEXT_REPORT_CHUNK = 120;

const MIGRATION_REPORT_VISIBLE_LS_KEY = 'migration_report_visible_columns_v2';
const MIGRATION_REPORT_COL_WIDTHS_LS_KEY = 'migration_report_column_widths';

function readMigrationReportColWidths(): Record<string, number> {
  try {
    const s = localStorage.getItem(MIGRATION_REPORT_COL_WIDTHS_LS_KEY);
    if (!s) return {};
    const p = JSON.parse(s) as Record<string, unknown>;
    if (!p || typeof p !== 'object') return {};
    const out: Record<string, number> = {};
    for (const [k, v] of Object.entries(p)) {
      if (typeof v === 'number' && Number.isFinite(v) && v >= 60 && v <= 600) out[k] = v;
    }
    return out;
  } catch {
    return {};
  }
}

function readMigrationReportVisible(): Record<string, boolean> {
  try {
    const s = localStorage.getItem(MIGRATION_REPORT_VISIBLE_LS_KEY);
    if (s) {
      const p = JSON.parse(s) as Record<string, boolean>;
      if (p && typeof p === 'object') {
        const out: Record<string, boolean> = {};
        MIGRATION_REPORT_COLUMNS.forEach(({ key }) => {
          out[key] = p[key] !== false;
        });
        return out;
      }
    }
  } catch (_) {
    /* ignore */
  }
  return MIGRATION_REPORT_COLUMNS.reduce<Record<string, boolean>>(
    (acc, { key }) => ({ ...acc, [key]: MIGRATION_REPORT_DEFAULT_VISIBLE_KEYS.has(key) }),
    {}
  );
}

/** Разделы модалки «Подробнее»: откуда (schedule) и куда (override / teacher) */
const MIGRATION_DETAIL_SECTIONS: { title: string; keys: { key: string; label: string }[] }[] = [
  {
    title: 'Откуда: строка в таблице schedule',
    keys: [
      { key: 'schedule_id', label: 'id строки' },
      { key: 'day_of_week', label: 'День недели' },
      { key: 'pair_number', label: 'Пара' },
      { key: 'subject_name', label: 'Предмет' },
      { key: 'lecture_type', label: 'Тип занятия' },
      { key: 'audience', label: 'Аудитория' },
      { key: 'duration_pairs', label: 'Длительность (пар)' },
      { key: 'group_name', label: 'Группа' },
      { key: 'week_type', label: 'Неделя' },
      { key: 'fio', label: 'ФИО (schedule.fio — для сопоставления с teacher)' },
      { key: 'subgroup', label: 'Подгруппа (schedule.subgroup)' },
      { key: 'institute', label: 'Институт' },
      { key: 'course', label: 'Курс' },
      { key: 'direction', label: 'Направление' },
      { key: 'department', label: 'Кафедра' },
    ],
  },
  {
    title: 'Куда: таблица schedule_override (вставленная запись)',
    keys: [
      { key: 'schedule_override_id', label: 'id новой записи (schedule_override.id)' },
      { key: 'ov_group_id', label: 'group_id' },
      { key: 'ov_weekday', label: 'weekday' },
      { key: 'ov_week_type', label: 'week_type' },
      { key: 'ov_class_type', label: 'class_type' },
      { key: 'ov_timeslot_no', label: 'timeslot_no' },
      {
        key: 'ov_subgroup_no',
        label: 'subgroup_no (номер п/г в schedule_override; из schedule.subgroup)',
      },
      {
        key: 'ov_subgroup_count',
        label:
          'subgroup_count (из num_subgroups; если задан номер п/г — не ниже max(номер, 2))',
      },
      { key: 'ov_subject_id', label: 'subject_id' },
      { key: 'ov_teacher_id', label: 'teacher_id (если есть в схеме override)' },
    ],
  },
  {
    title: 'Связь schedule_override_teacher',
    keys: [{ key: 'sot_will_link', label: 'Будет связь override ↔ teacher' }],
  },
  {
    title: 'Сопоставление: справочники teacher и subject',
    keys: [
      { key: 'subject_id', label: 'subject_id (по subject_name)' },
      { key: 'teacher_id', label: 'teacher_id (по schedule.fio)' },
      { key: 'teacher_fio_db', label: 'ФИО в таблице teacher' },
      { key: 'teacher_reason', label: 'Как найдено ФИО' },
      { key: 'subject_reason', label: 'Как найден предмет' },
    ],
  },
];

const MIGRATION_ACTIONS_COL_GRID = 'minmax(108px, 132px)';

/** Несколько уровней сортировки (как в DatabaseView: Shift+клик — следующий ключ) */
type MigrationReportSortEntry = { key: string; dir: 'asc' | 'desc' };

/** Календарный порядок, как в API БД (CASE day_of_week …): пн = 1 … вс = 7 */
const RU_WEEKDAY_ORDER: Record<string, number> = {
  понедельник: 1,
  вторник: 2,
  среда: 3,
  четверг: 4,
  пятница: 5,
  суббота: 6,
  воскресенье: 7,
};

function weekdayNumericOrder(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) {
    const n = Math.trunc(v);
    if (n >= 1 && n <= 7) return n;
  }
  if (typeof v === 'string') {
    const t = v.trim();
    if (t === '') return null;
    const asNum = Number(t);
    if (Number.isFinite(asNum)) {
      const n = Math.trunc(asNum);
      if (n >= 1 && n <= 7) return n;
    }
  }
  return null;
}

/** Сравнение дня недели: не по алфавиту (там «вторник» раньше «понедельника»), а по неделе */
function compareDayOfWeekValues(a: unknown, b: unknown): number {
  const na = weekdayNumericOrder(a);
  const nb = weekdayNumericOrder(b);
  if (na != null && nb != null && na !== nb) return na - nb;
  if (na != null && nb == null) return -1;
  if (na == null && nb != null) return 1;

  const sa = a == null ? '' : String(a).trim().toLowerCase();
  const sb = b == null ? '' : String(b).trim().toLowerCase();
  const ia = RU_WEEKDAY_ORDER[sa] ?? 100;
  const ib = RU_WEEKDAY_ORDER[sb] ?? 100;
  if (ia !== ib) return ia - ib;
  return sa.localeCompare(sb, 'ru', { numeric: true });
}

function formatMigrationDetailValue(v: unknown): string {
  if (v == null || v === '') return '—';
  if (typeof v === 'boolean') return v ? 'да' : 'нет';
  return String(v);
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
  /** Полный отчёт в output_log (файл на сервере + текст в интерфейсе) */
  const [migrateIncludeFullReport, setMigrateIncludeFullReport] = useState(true);
  const [migrateLogSample, setMigrateLogSample] = useState(0);
  const [migrateLogAllTeachers, setMigrateLogAllTeachers] = useState(false);
  const [migrateLogExpanded, setMigrateLogExpanded] = useState(true);
  const [migrationReportFilter, setMigrationReportFilter] = useState('');
  const [migrationReportSortColumns, setMigrationReportSortColumns] = useState<MigrationReportSortEntry[]>([
    { key: 'schedule_override_id', dir: 'asc' },
  ]);
  const [migrationReportVisible, setMigrationReportVisible] = useState<Record<string, boolean>>(readMigrationReportVisible);
  const [migrationReportColumnFilters, setMigrationReportColumnFilters] = useState<Record<string, string>>({});
  const [migrationReportPage, setMigrationReportPage] = useState(1);
  const [showMigrationColumnsMenu, setShowMigrationColumnsMenu] = useState(false);
  const migrationColumnsMenuRef = useRef<HTMLDivElement>(null);
  const migrationResizeStartX = useRef(0);
  const migrationResizeStartWidth = useRef(0);
  const [migrationDetailRow, setMigrationDetailRow] = useState<Record<string, unknown> | null>(null);
  const [migrationTextReportStart, setMigrationTextReportStart] = useState(0);
  const [migrationTextReportLines, setMigrationTextReportLines] = useState<string[]>([]);
  const [migrationTextReportHasMore, setMigrationTextReportHasMore] = useState(false);
  const [migrationTextReportLoading, setMigrationTextReportLoading] = useState(false);
  const [migrationTextReportError, setMigrationTextReportError] = useState<string | null>(null);
  const [migrationReportColWidths, setMigrationReportColWidths] = useState<Record<string, number>>(readMigrationReportColWidths);
  const [migrationReportResizingKey, setMigrationReportResizingKey] = useState<string | null>(null);
  const [expandedMigrationReportCell, setExpandedMigrationReportCell] = useState<{
    id: string;
    width: number;
    direction: 'left' | 'right';
  } | null>(null);

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

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        showMigrationColumnsMenu &&
        migrationColumnsMenuRef.current &&
        !migrationColumnsMenuRef.current.contains(e.target as Node)
      ) {
        setShowMigrationColumnsMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showMigrationColumnsMenu]);

  useEffect(() => {
    if (!migrationDetailRow) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMigrationDetailRow(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [migrationDetailRow]);

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
      if (migrateOldToNewStatus.running) {
        fetchStatus('migrate_old_to_new', setMigrateOldToNewStatus);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [parseStatus.running, cleanStatus.running, loadTimetableToDbStatus.running, mergeTimetableStatus.running, processTimetableStatus.running, parseAspiStatus.running, normalizeAspiStatus.running, loadAspiToDbStatus.running, mergeAspiToIntermediateStatus.running, parseSpoStatus.running, loadSpoToDbStatus.running, mergeSpoToIntermediateStatus.running, migrateOldToNewStatus.running]);

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
    setMigrationDetailRow(null);
    setMigrationReportPage(1);
    setMigrationTextReportStart(0);
    setMigrationTextReportLines([]);
    setMigrationTextReportHasMore(false);
    setMigrationTextReportError(null);
    setMigrateOldToNewStatus({
      running: true,
      progress: 0,
      message: 'Запуск...',
      error: null,
      output_log: '',
      report_rows: [],
      full_report_available: false,
    });
    try {
      await axios.post(`${API_BASE}/run/migrate_old_to_new`, {
        semester_id: migrateSemesterId,
        clean: !cleanOverrideOnly && migrateClean,
        dedupe: migrateDedupe,
        strict: migrateStrict,
        clean_override_only: cleanOverrideOnly,
        include_full_report: migrateIncludeFullReport,
        log_sample: migrateLogSample,
        log_all_teachers: migrateLogAllTeachers,
      });
    } catch (err: any) {
      const msg = err.response?.data?.error ?? err.message ?? 'Ошибка запроса';
      setMigrateOldToNewStatus({
        running: false,
        progress: 0,
        message: '',
        error: msg,
        output_log: '',
        report_rows: [],
        full_report_available: false,
      });
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
      }, 1500);
    });
  }, [
    API_BASE,
    migrateSemesterId,
    migrateClean,
    migrateDedupe,
    migrateStrict,
    migrateIncludeFullReport,
    migrateLogSample,
    migrateLogAllTeachers,
  ]);

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
        const rawA = a[field];
        const rawB = b[field];
        const av = migrationCellValue(rawA);
        const bv = migrationCellValue(rawB);
        const useWeekOrder = field === 'day_of_week' || field === 'ov_weekday';
        const cmp = useWeekOrder ? compareDayOfWeekValues(rawA, rawB) : av.localeCompare(bv, 'ru', { numeric: true });
        return cmp * sign;
      });
    }
    return rows;
  }, [tableData, tableGlobalFilter, tableColumnFilters, migrationDisplayedColumns, migrationSort]);

  const visibleMigrationReportColumns = useMemo(
    () => MIGRATION_REPORT_COLUMNS.filter((c) => migrationReportVisible[c.key] !== false),
    [migrationReportVisible]
  );

  const migrationReportGridTemplate = useMemo(() => {
    if (visibleMigrationReportColumns.length === 0) return '1fr';
    const parts = visibleMigrationReportColumns.map(({ key }) => {
      const w = migrationReportColWidths[key];
      if (typeof w === 'number' && w >= 60) return `${Math.min(600, w)}px`;
      return 'minmax(104px, 1fr)';
    });
    return `${MIGRATION_ACTIONS_COL_GRID} ${parts.join(' ')}`;
  }, [visibleMigrationReportColumns, migrationReportColWidths]);

  const migrationReportRows = useMemo(() => {
    const rows = migrateOldToNewStatus.report_rows;
    if (!rows?.length) return [];
    const q = migrationReportFilter.trim().toLowerCase();
    let list = rows;
    if (q) {
      list = list.filter((row) =>
        MIGRATION_REPORT_COLUMNS.some((col) => {
          const v = row[col.key];
          if (v == null || v === '') return false;
          return String(v).toLowerCase().includes(q);
        })
      );
    }
    const colFilters = Object.entries(migrationReportColumnFilters).filter(([, v]) => v.trim() !== '');
    if (colFilters.length) {
      list = list.filter((row) =>
        colFilters.every(([colKey, needle]) => {
          const needleL = needle.trim().toLowerCase();
          if (!needleL) return true;
          return String(row[colKey] ?? '').toLowerCase().includes(needleL);
        })
      );
    }
    if (migrationReportSortColumns.length > 0) {
      list = [...list].sort((a, b) => {
        for (const { key, dir } of migrationReportSortColumns) {
          const av = a[key];
          const bv = b[key];
          const as = av == null ? '' : String(av);
          const bs = bv == null ? '' : String(bv);
          const useWeekOrder = key === 'day_of_week' || key === 'ov_weekday';
          const cmp = useWeekOrder
            ? compareDayOfWeekValues(av, bv)
            : as.localeCompare(bs, 'ru', { numeric: true });
          if (cmp !== 0) return dir === 'asc' ? cmp : -cmp;
        }
        return 0;
      });
    }
    return list;
  }, [
    migrateOldToNewStatus.report_rows,
    migrationReportFilter,
    migrationReportColumnFilters,
    migrationReportSortColumns,
  ]);

  const migrationReportTotalPages = Math.max(
    1,
    Math.ceil(migrationReportRows.length / MIGRATION_REPORT_PAGE_SIZE)
  );

  const migrationReportRowsPaged = useMemo(() => {
    const start = (migrationReportPage - 1) * MIGRATION_REPORT_PAGE_SIZE;
    return migrationReportRows.slice(start, start + MIGRATION_REPORT_PAGE_SIZE);
  }, [migrationReportRows, migrationReportPage]);

  useEffect(() => {
    setMigrationReportPage((p) => Math.min(p, migrationReportTotalPages));
  }, [migrationReportTotalPages]);

  useEffect(() => {
    setMigrationReportPage(1);
  }, [migrationReportFilter, migrationReportColumnFilters, migrationReportSortColumns]);

  const migrationReportHasActiveFilters =
    migrationReportFilter.trim() !== '' ||
    Object.values(migrationReportColumnFilters).some((v) => v.trim() !== '');

  const toggleMigrationReportColumn = (key: string) => {
    setMigrationReportVisible((prev) => {
      const wasVisible = prev[key] !== false;
      const next = { ...prev, [key]: !wasVisible };
      try {
        localStorage.setItem(MIGRATION_REPORT_VISIBLE_LS_KEY, JSON.stringify(next));
      } catch (_) {
        /* ignore */
      }
      return next;
    });
  };

  const clearMigrationReportFilters = () => {
    setMigrationReportColumnFilters({});
    setMigrationReportFilter('');
  };

  /** Обычный клик — один столбец; Shift+клик — добавить уровень (как в DatabaseView). */
  const handleMigrationReportSort = (key: string, shiftKey: boolean) => {
    setMigrationReportSortColumns((prev) => {
      const idx = prev.findIndex((s) => s.key === key);
      if (shiftKey) {
        if (idx >= 0) {
          const next = [...prev];
          next[idx] = { ...next[idx], dir: next[idx].dir === 'asc' ? 'desc' : 'asc' };
          return next;
        }
        return [...prev, { key, dir: 'asc' as const }];
      }
      if (idx === 0 && prev.length === 1) {
        return [{ key, dir: prev[0].dir === 'asc' ? 'desc' : 'asc' }];
      }
      return [{ key, dir: 'asc' as const }];
    });
  };

  const copyMigrationReportCell = (val: unknown) => {
    const text = val == null ? '' : String(val);
    void navigator.clipboard.writeText(text);
  };

  const calculateMigrationReportCellWidth = useCallback((cellElement: HTMLElement, contentElement: HTMLElement) => {
    const tempElement = document.createElement('div');
    const computedStyle = window.getComputedStyle(contentElement);
    tempElement.style.cssText = `
      position: absolute;
      visibility: hidden;
      white-space: nowrap;
      font-family: ${computedStyle.fontFamily};
      font-size: ${computedStyle.fontSize};
      font-weight: ${computedStyle.fontWeight};
      font-style: ${computedStyle.fontStyle};
      letter-spacing: ${computedStyle.letterSpacing};
      padding: 0.75rem;
      box-sizing: border-box;
    `;
    tempElement.textContent = contentElement.textContent || '';
    document.body.appendChild(tempElement);
    const scrollWidth = tempElement.scrollWidth;
    const padding = 1.5 * 16;
    const contentWidth = scrollWidth + padding;
    const maxWidth = Math.min(window.innerWidth * 0.8, 800);
    const finalWidth = Math.min(contentWidth, maxWidth);
    const cellRect = cellElement.getBoundingClientRect();
    const spaceRight = window.innerWidth - cellRect.right;
    const direction = spaceRight >= finalWidth ? 'right' : 'left';
    document.body.removeChild(tempElement);
    return { width: finalWidth, direction };
  }, []);

  const handleMigrationReportCellMouseEnter = useCallback(
    (e: React.MouseEvent<HTMLDivElement>, cellId: string) => {
      const cellElement = e.currentTarget;
      const contentElement = cellElement.querySelector('.cell-content') as HTMLElement | null;
      if (!contentElement) return;
      const isOverflowing = contentElement.scrollWidth > contentElement.clientWidth;
      if (isOverflowing) {
        const { width, direction } = calculateMigrationReportCellWidth(cellElement, contentElement);
        setExpandedMigrationReportCell({ id: cellId, width, direction });
      }
    },
    [calculateMigrationReportCellWidth]
  );

  const handleMigrationReportCellMouseLeave = useCallback(() => {
    setExpandedMigrationReportCell(null);
  }, []);

  const handleMigrationReportResizeStart = useCallback(
    (e: React.MouseEvent, columnKey: string) => {
      e.preventDefault();
      e.stopPropagation();
      setMigrationReportResizingKey(columnKey);
      migrationResizeStartX.current = e.clientX;
      const cell = (e.target as HTMLElement).closest('.grid-table-cell');
      const actualWidth = cell ? cell.getBoundingClientRect().width : migrationReportColWidths[columnKey] ?? 120;
      migrationResizeStartWidth.current = actualWidth;
    },
    [migrationReportColWidths]
  );

  useEffect(() => {
    if (migrationReportResizingKey === null) return;
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';
    const key = migrationReportResizingKey;
    const onMove = (e: MouseEvent) => {
      const delta = e.clientX - migrationResizeStartX.current;
      const newW = Math.max(60, Math.min(600, migrationResizeStartWidth.current + delta));
      setMigrationReportColWidths((prev) => ({ ...prev, [key]: newW }));
    };
    const onUp = () => setMigrationReportResizingKey(null);
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
  }, [migrationReportResizingKey]);

  useEffect(() => {
    if (migrationReportResizingKey !== null) return;
    try {
      localStorage.setItem(MIGRATION_REPORT_COL_WIDTHS_LS_KEY, JSON.stringify(migrationReportColWidths));
    } catch {
      /* ignore */
    }
  }, [migrationReportColWidths, migrationReportResizingKey]);

  const loadMigrationTextReport = React.useCallback(
    async (startLine: number) => {
      setMigrationTextReportLoading(true);
      setMigrationTextReportError(null);
      try {
        const res = await axios.get<{
          lines: string[];
          has_more: boolean;
          start_line: number;
          limit: number;
        }>(`${API_BASE}/migration_report_lines`, {
          params: { start_line: startLine, limit: MIGRATION_TEXT_REPORT_CHUNK },
        });
        setMigrationTextReportStart(res.data.start_line);
        setMigrationTextReportLines(res.data.lines ?? []);
        setMigrationTextReportHasMore(Boolean(res.data.has_more));
      } catch (err: unknown) {
        const msg =
          (err as { response?: { data?: { error?: string } }; message?: string })?.response?.data?.error
          ?? (err as { message?: string })?.message
          ?? 'Ошибка загрузки фрагмента отчёта';
        setMigrationTextReportError(String(msg));
        setMigrationTextReportLines([]);
        setMigrationTextReportHasMore(false);
      } finally {
        setMigrationTextReportLoading(false);
      }
    },
    [API_BASE]
  );

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
        <p className="description" style={{ marginTop: '0.5rem', marginBottom: '0.75rem' }}>
          <strong>Отчёт:</strong> таблица ниже строится из <code>output/migration_report_web.json</code>. Развёрнутый текст (все колонки <code>schedule</code>, вставка в{' '}
          <code>schedule_override</code> / <code>schedule_override_teacher</code>, сопоставление <code>teacher</code> по <code>schedule.fio</code>;{' '}
          <code>timetable_teacher</code> не используется) пишется в <code>output/migration_report_web.txt</code> и в интерфейсе открывается{' '}
          <strong>постранично</strong>, без заливки мегабайтов в журнал.
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center', marginBottom: '0.75rem' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <input
              type="checkbox"
              checked={migrateIncludeFullReport}
              onChange={(e) => setMigrateIncludeFullReport(e.target.checked)}
              disabled={migrateOldToNewStatus.running}
            />
            Сформировать полные файлы отчёта (.txt + .json) и таблицу
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <input
              type="checkbox"
              checked={migrateLogAllTeachers}
              onChange={(e) => setMigrateLogAllTeachers(e.target.checked)}
              disabled={migrateOldToNewStatus.running}
            />
            Дублировать в консоль каждую строку (stderr, тяжёлый лог)
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            log-sample в консоль:
            <input
              type="number"
              min={0}
              max={100000}
              value={migrateLogSample}
              onChange={(e) => setMigrateLogSample(Number(e.target.value) || 0)}
              disabled={migrateOldToNewStatus.running}
              style={{ width: '5rem' }}
            />
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

        {(migrateOldToNewStatus.report_rows?.length ?? 0) > 0 && (
          <div className="table-container" style={{ marginTop: '1.25rem' }}>
            <h3 className="migration-report-heading" style={{ margin: '0 0 0.5rem 0', fontSize: '1.1rem' }}>
              Записи отчёта миграции
            </h3>
            {migrateOldToNewStatus.report_rows && migrateOldToNewStatus.report_rows.length > 0 && (
              <p className="records-count" style={{ marginBottom: '0.5rem' }}>
                Найдено записей: <strong>{migrationReportRows.length}</strong>
                {migrationReportHasActiveFilters && (
                  <> (из {migrateOldToNewStatus.report_rows.length} с учётом фильтров)</>
                )}
                {migrationReportRows.length > 0 && (
                  <>
                    {' '}
                    · страница <strong>{migrationReportPage}</strong> из <strong>{migrationReportTotalPages}</strong> (
                    {MIGRATION_REPORT_PAGE_SIZE} строк)
                  </>
                )}
              </p>
            )}
            <div className="filter-controls" style={{ marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'flex-start' }}>
              <div className="filter-hint">
                💡 Клик по ячейке — копировать; наведение на обрезанный текст раскрывает ячейку. Граница заголовка справа — ширина колонки (как в «Записи в базе данных»).
              </div>
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', flex: '1 1 220px' }}>
                <span style={{ whiteSpace: 'nowrap' }}>Поиск по всем колонкам:</span>
                <input
                  type="text"
                  className="group-search-input"
                  value={migrationReportFilter}
                  onChange={(e) => setMigrationReportFilter(e.target.value)}
                  placeholder="Общий фильтр"
                  autoComplete="off"
                />
              </label>
              <div className="columns-menu-wrapper" ref={migrationColumnsMenuRef}>
                <button
                  type="button"
                  className="button columns-toggle"
                  onClick={() => setShowMigrationColumnsMenu((v) => !v)}
                  title="Показать или скрыть колонки"
                >
                  Колонки
                </button>
                {showMigrationColumnsMenu && (
                  <div className="columns-dropdown">
                    <div className="columns-dropdown-title">Видимость колонок (отчёт миграции)</div>
                    {MIGRATION_REPORT_COLUMNS.map(({ key, label }) => (
                      <label key={key} className="columns-dropdown-item">
                        <input
                          type="checkbox"
                          checked={migrationReportVisible[key] !== false}
                          onChange={() => toggleMigrationReportColumn(key)}
                        />
                        <span>{label}</span>
                      </label>
                    ))}
                    <div className="columns-dropdown-divider" />
                    <button
                      type="button"
                      className="columns-dropdown-action"
                      onClick={() => {
                        setMigrationReportColWidths({});
                        try {
                          localStorage.removeItem(MIGRATION_REPORT_COL_WIDTHS_LS_KEY);
                        } catch {
                          /* ignore */
                        }
                        setShowMigrationColumnsMenu(false);
                      }}
                    >
                      Сбросить ширины колонок
                    </button>
                    <button
                      type="button"
                      className="columns-dropdown-action"
                      onClick={() => {
                        clearMigrationReportFilters();
                        setShowMigrationColumnsMenu(false);
                      }}
                    >
                      Очистить фильтры
                    </button>
                  </div>
                )}
              </div>
            </div>
            {visibleMigrationReportColumns.length === 0 && (
              <p className="message error" style={{ marginBottom: '0.75rem' }}>
                Включите хотя бы одну колонку в меню «Колонки».
              </p>
            )}
            {migrationReportRows.length === 0 && migrationReportHasActiveFilters && (
              <p className="description" style={{ marginBottom: '0.75rem' }}>
                Нет строк по текущим фильтрам.
              </p>
            )}
            {visibleMigrationReportColumns.length > 0 && migrationReportRows.length > 0 && (
              <div
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: '0.5rem',
                  alignItems: 'center',
                  marginBottom: '0.75rem',
                }}
              >
                <button
                  type="button"
                  className="button"
                  style={{ padding: '0.25rem 0.65rem', fontSize: '0.85rem' }}
                  disabled={migrationReportPage <= 1}
                  onClick={() => setMigrationReportPage((p) => Math.max(1, p - 1))}
                >
                  ← Предыдущая
                </button>
                <button
                  type="button"
                  className="button"
                  style={{ padding: '0.25rem 0.65rem', fontSize: '0.85rem' }}
                  disabled={migrationReportPage >= migrationReportTotalPages}
                  onClick={() => setMigrationReportPage((p) => Math.min(migrationReportTotalPages, p + 1))}
                >
                  Следующая →
                </button>
              </div>
            )}
            {visibleMigrationReportColumns.length > 0 && (
              <div className="grid-table">
                <div
                  className="grid-table-header"
                  style={{ display: 'grid', width: '100%', gridTemplateColumns: migrationReportGridTemplate }}
                >
                  <div className="grid-table-cell header-cell-resizable">
                    <div className="header-label">Действия</div>
                    <input
                      type="text"
                      className="header-filter-input"
                      value=""
                      disabled
                      placeholder="—"
                      title="Столбец не фильтруется"
                    />
                  </div>
                  {visibleMigrationReportColumns.map(({ key, label }) => {
                    const sortIdx = migrationReportSortColumns.findIndex((s) => s.key === key);
                    const entry = sortIdx >= 0 ? migrationReportSortColumns[sortIdx] : null;
                    return (
                      <div key={key} className="grid-table-cell header-cell-resizable">
                        <button
                          type="button"
                          className="header-label header-sortable"
                          style={{
                            border: 'none',
                            background: 'none',
                            font: 'inherit',
                            cursor: 'pointer',
                            textAlign: 'left',
                            width: '100%',
                            padding: 0,
                          }}
                          onClick={(e) => handleMigrationReportSort(key, e.shiftKey)}
                          title="Клик — сортировка по столбцу. Shift+клик — добавить уровень сортировки."
                        >
                          {label}
                          <span className="sort-arrows" style={{ marginLeft: '0.25rem' }}>
                            <span className={`sort-arrow ${entry?.dir === 'asc' ? 'active' : ''}`}>▲</span>
                            <span className={`sort-arrow ${entry?.dir === 'desc' ? 'active' : ''}`}>▼</span>
                            {sortIdx >= 0 && migrationReportSortColumns.length > 1 && (
                              <span className="sort-order-badge">{sortIdx + 1}</span>
                            )}
                          </span>
                        </button>
                        <input
                          type="text"
                          className="header-filter-input"
                          value={migrationReportColumnFilters[key] ?? ''}
                          onChange={(e) =>
                            setMigrationReportColumnFilters((prev) => ({
                              ...prev,
                              [key]: e.target.value,
                            }))
                          }
                          onClick={(e) => e.stopPropagation()}
                          onMouseDown={(e) => e.stopPropagation()}
                          onKeyDown={(e) => e.stopPropagation()}
                          placeholder={`Фильтр: ${label}`}
                          title={`Поиск по колонке «${label}»`}
                          autoComplete="off"
                        />
                        <div
                          className="column-resize-handle"
                          onMouseDown={(e) => handleMigrationReportResizeStart(e, key)}
                          title="Изменить ширину"
                        />
                      </div>
                    );
                  })}
                </div>
                <div className="grid-table-body">
                  {migrationReportRowsPaged.map((row, rowIdx) => {
                    const globalIdx = (migrationReportPage - 1) * MIGRATION_REPORT_PAGE_SIZE + rowIdx;
                    return (
                    <div
                      key={`mr-${globalIdx}-${row.schedule_id ?? ''}-${row.schedule_override_id ?? ''}`}
                      className="grid-table-row"
                      style={{ display: 'grid', width: '100%', gridTemplateColumns: migrationReportGridTemplate }}
                    >
                      <div className="grid-table-cell migration-report-actions-cell">
                        <button
                          type="button"
                          className="button migration-detail-open-btn"
                          onClick={(e) => {
                            e.stopPropagation();
                            setMigrationDetailRow(row);
                          }}
                        >
                          Подробнее
                        </button>
                      </div>
                      {visibleMigrationReportColumns.map(({ key }) => {
                        const uniqueCellId = `mr-${globalIdx}-${key}`;
                        const isExpanded = expandedMigrationReportCell?.id === uniqueCellId;
                        const expandDirection = expandedMigrationReportCell?.direction || 'right';
                        const expandWidth = expandedMigrationReportCell?.width || 0;
                        const displayText = row[key] == null || row[key] === '' ? '—' : String(row[key]);
                        return (
                          <div
                            key={key}
                            className="grid-table-cell expandable-cell"
                            title="Клик — копировать. Наведите, чтобы раскрыть длинный текст."
                            onMouseEnter={(e) => handleMigrationReportCellMouseEnter(e, uniqueCellId)}
                            onMouseLeave={handleMigrationReportCellMouseLeave}
                            onClick={() => copyMigrationReportCell(row[key])}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                copyMigrationReportCell(row[key]);
                              }
                            }}
                            role="button"
                            tabIndex={0}
                          >
                            <div
                              className="cell-content"
                              data-expanded={isExpanded}
                              data-direction={expandDirection}
                              style={
                                isExpanded
                                  ? {
                                      width: `${expandWidth}px`,
                                      minWidth: `${expandWidth}px`,
                                      ...(expandDirection === 'left'
                                        ? { right: 0, left: 'auto' }
                                        : { left: 0, right: 'auto' }),
                                    }
                                  : {}
                              }
                            >
                              {displayText}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {migrationDetailRow && (
          <div className="aspi-unresolved-overlay" onClick={() => setMigrationDetailRow(null)}>
            <div className="aspi-unresolved-modal migration-detail-modal" onClick={(e) => e.stopPropagation()}>
              <div className="aspi-unresolved-modal-header">
                <h3>Куда и откуда мигрировали</h3>
                <button
                  type="button"
                  className="aspi-unresolved-close"
                  onClick={() => setMigrationDetailRow(null)}
                  aria-label="Закрыть"
                >
                  ×
                </button>
              </div>
              <div className="migration-detail-modal-body">
                <p className="migration-detail-lead">
                  Источник — строка в <code>schedule</code> (ниже поля как в отчёте). Цель — новая запись в{' '}
                  <code>schedule_override</code> с id <strong>{formatMigrationDetailValue(migrationDetailRow.schedule_override_id)}</strong>
                  ; при необходимости строка в <code>schedule_override_teacher</code> (связь с <code>teacher</code>).
                  Таблица <code>timetable_teacher</code> в миграции не используется.
                </p>
                {MIGRATION_DETAIL_SECTIONS.map((section) => (
                  <section key={section.title} className="migration-detail-section">
                    <h4 className="migration-detail-section-title">{section.title}</h4>
                    <table className="migration-detail-table">
                      <tbody>
                        {section.keys.map(({ key, label }) => (
                          <tr key={key}>
                            <th scope="row">{label}</th>
                            <td>{formatMigrationDetailValue(migrationDetailRow[key])}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </section>
                ))}
              </div>
              <div className="aspi-unresolved-modal-footer">
                <button type="button" className="button button-primary" onClick={() => setMigrationDetailRow(null)}>
                  Закрыть
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="migration-console-wrap" style={{ marginTop: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.35rem' }}>
            <strong>Журнал консоли</strong>
            <button
              type="button"
              className="button"
              style={{ padding: '0.25rem 0.6rem', fontSize: '0.85rem' }}
              onClick={() => setMigrateLogExpanded((v) => !v)}
            >
              {migrateLogExpanded ? 'Свернуть' : 'Развернуть'}
            </button>
          </div>
          <pre
            className={`migration-console-log${migrateLogExpanded ? '' : ' migration-console-log--collapsed'}`}
            aria-label="Журнал миграции"
          >
            {migrateOldToNewStatus.running && !migrateOldToNewStatus.output_log
              ? 'Выполняется миграция…\n'
              : migrateOldToNewStatus.output_log
                || (migrateOldToNewStatus.error ? '' : 'Запустите миграцию — здесь будет вывод скрипта (без огромного текстового отчёта).')}
          </pre>
        </div>

        {migrateOldToNewStatus.full_report_available && (
          <div className="migration-text-report-wrap" style={{ marginTop: '1rem' }}>
            <strong>Текстовый отчёт (файл на сервере)</strong>
            <p className="description" style={{ margin: '0.35rem 0 0.5rem' }}>
              Полный отчёт в <code>output/migration_report_web.txt</code> — подгружается по фрагментам, чтобы не перегружать браузер.
              Строки {migrationTextReportStart + 1}–{migrationTextReportStart + migrationTextReportLines.length}
              {migrationTextReportHasMore ? ' (есть продолжение)' : migrationTextReportLines.length > 0 ? ' (конец файла)' : ''}.
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.5rem' }}>
              <button
                type="button"
                className="button"
                style={{ padding: '0.25rem 0.65rem', fontSize: '0.85rem' }}
                disabled={migrationTextReportLoading || migrationTextReportStart <= 0}
                onClick={() =>
                  void loadMigrationTextReport(Math.max(0, migrationTextReportStart - MIGRATION_TEXT_REPORT_CHUNK))
                }
              >
                ← Ранее
              </button>
              <button
                type="button"
                className="button"
                style={{ padding: '0.25rem 0.65rem', fontSize: '0.85rem' }}
                disabled={migrationTextReportLoading || !migrationTextReportHasMore}
                onClick={() =>
                  void loadMigrationTextReport(migrationTextReportStart + migrationTextReportLines.length)
                }
              >
                Далее →
              </button>
              <button
                type="button"
                className="button button-primary"
                style={{ padding: '0.25rem 0.65rem', fontSize: '0.85rem' }}
                disabled={migrationTextReportLoading}
                onClick={() => void loadMigrationTextReport(0)}
              >
                С начала
              </button>
            </div>
            {migrationTextReportError && (
              <div className="message error" style={{ marginBottom: '0.5rem' }}>
                {migrationTextReportError}
              </div>
            )}
            {migrationTextReportLoading && <p className="description">Загрузка…</p>}
            {!migrationTextReportLoading && migrationTextReportLines.length === 0 && !migrationTextReportError && (
              <p className="description">Нажмите «С начала», чтобы загрузить первый фрагмент.</p>
            )}
            {migrationTextReportLines.length > 0 && (
              <pre
                className="migration-console-log"
                style={{ maxHeight: 'min(22rem, 55vh)' }}
                aria-label="Фрагмент текстового отчёта миграции"
              >
                {migrationTextReportLines.join('\n')}
              </pre>
            )}
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
