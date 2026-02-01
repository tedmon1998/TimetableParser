import React, { useState, useEffect, useMemo, useRef, useCallback, useLayoutEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { useDebounce } from '../hooks/useDebounce';
import Toast from './Toast';
import './DatabaseView.css';

interface DatabaseStats {
  total: number;
  by_day: Array<{ day_of_week: string; count: number }>;
  by_type: Array<{ lecture_type: string; count: number }>;
  last_update: string | null;
}

interface DatabaseRecord {
  id: number;
  day_of_week: string | null;
  pair_number: number | null;
  subject_name: string | null;
  lecture_type: string | null;
  audience: string | null;
  fio: string | null;
  teacher: string | null;
  group_name: string | null;
  week_type: string | null;
  subgroup?: number | null;
  institute?: string | null;
  course?: string | null;
  direction?: string | null;
  department?: string | null;
  is_external?: boolean | null;
  is_remote?: boolean | null;
  num_subgroups?: number | null;
  [key: string]: any;
}

interface Filters {
  day_of_week: string;
  pair_number: string;
  subject_name: string;
  lecture_type: string;
  audience: string;
  fio: string;
  teacher: string;
  group_name: string;
  subgroup: string;
  week_type: string;
  institute: string;
  course: string;
  direction: string;
  profile: string;
  has_error: string;
  week_error: string;
  audience_error: string;
}

// Порядок и метки колонок таблицы (ключ поля → подпись). Подгруппа и Курс по умолчанию скрыты.
const COLUMN_KEYS = ['id', 'day_of_week', 'pair_number', 'subject_name', 'lecture_type', 'audience', 'fio', 'group_name', 'subgroup', 'course', 'institute', 'direction', 'profile', 'week_type'] as const;
type ColumnKey = typeof COLUMN_KEYS[number];
const COLUMN_LABELS: Record<ColumnKey, string> = {
  id: 'ID',
  day_of_week: 'День',
  pair_number: 'Пара',
  subject_name: 'Предмет',
  lecture_type: 'Тип',
  audience: 'Ауд.',
  fio: 'Преподаватель',
  group_name: 'Группа',
  subgroup: 'п/г',
  course: 'Курс',
  institute: 'Институт',
  direction: 'Направление',
  profile: 'Профиль',
  week_type: 'Неделя'
};
const COLUMN_PLACEHOLDERS: Partial<Record<ColumnKey, string>> = {
  id: 'ID (не фильтруется)',
  day_of_week: 'Фильтр по дню недели (понедельник, вторник...)',
  pair_number: 'Фильтр по номеру пары (1, 2, 3...)',
  subject_name: 'Фильтр по предмету (Математика, Физика...)',
  lecture_type: 'Фильтр по типу занятия (лекция, практика...)',
  audience: 'Фильтр по аудитории (У804, А539...)',
  fio: 'Фильтр по преподавателю (Иванов И.И...)',
  group_name: 'Фильтр по группе (606-22, 606-21...)',
  subgroup: 'Фильтр по подгруппе (1, 2...)',
  course: 'Фильтр по курсу (1, 2, 3...)',
  institute: 'Фильтр по институту',
  direction: 'Фильтр по направлению',
  profile: 'Фильтр по профилю',
  week_type: 'Фильтр по типу недели (числитель, знаменатель...)'
};

export type DbTableType = 'timetable_cleaned' | 'timetable_teacher' | 'intermediate_timetable';

// Колонки промежуточного расписания: данные из timetable_cleaned + fio из timetable_teacher + флаги ошибок + старое имя дисциплины
const INTERMEDIATE_COLUMN_KEYS = ['id', 'day_of_week', 'pair_number', 'subject_name', 'discipline_original', 'lecture_type', 'audience', 'group_name', 'week_type', 'subgroup', 'institute', 'course', 'direction', 'department', 'fio', 'week_error', 'audience_error'] as const;
const INTERMEDIATE_LABELS: Record<string, string> = {
  id: 'ID',
  day_of_week: 'День',
  pair_number: 'Пара',
  subject_name: 'Предмет',
  discipline_original: 'Дисциплина (было)',
  lecture_type: 'Тип',
  audience: 'Ауд.',
  group_name: 'Группа',
  week_type: 'Неделя',
  subgroup: 'п/г',
  institute: 'Институт',
  course: 'Курс',
  direction: 'Направление',
  department: 'Кафедра',
  fio: 'Преподаватель (занятость)',
  week_error: 'Ошибка недели',
  audience_error: 'Ошибка аудитории'
};

// Список колонок для каждой вкладки (те, которые можно показывать/скрывать)
const COLUMNS_FOR_TABLE: Record<DbTableType, readonly string[]> = {
  timetable_cleaned: COLUMN_KEYS.filter(k => k !== 'fio'),
  timetable_teacher: COLUMN_KEYS.filter(k => k !== 'subject_name' && k !== 'lecture_type'),
  intermediate_timetable: [...INTERMEDIATE_COLUMN_KEYS]
};
// По умолчанию скрытые колонки для каждой вкладки
const HIDDEN_BY_DEFAULT_BY_TABLE: Record<DbTableType, string[]> = {
  timetable_cleaned: ['subgroup', 'course', 'profile', 'direction', 'institute'],
  timetable_teacher: ['subgroup', 'course', 'profile', 'direction', 'institute'],
  intermediate_timetable: ['subgroup', 'course', 'direction', 'institute']
};

function getDefaultVisibleForTable(table: DbTableType): Record<string, boolean> {
  const keys = COLUMNS_FOR_TABLE[table];
  const hiddenDefault = HIDDEN_BY_DEFAULT_BY_TABLE[table];
  return keys.reduce<Record<string, boolean>>((acc, k) => ({
    ...acc,
    [k]: !hiddenDefault.includes(k)
  }), {});
}

const DatabaseView: React.FC = () => {
  const [currentPage, setCurrentPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [activeTable, setActiveTable] = useState<DbTableType>('timetable_cleaned');
  const [filters, setFilters] = useState<Filters>({
    day_of_week: '',
    pair_number: '',
    subject_name: '',
    lecture_type: '',
    audience: '',
    fio: '',
    teacher: '',
    group_name: '',
    subgroup: '',
    week_type: '',
    institute: '',
    course: '',
    direction: '',
    profile: '',
    has_error: '',
    week_error: '',
    audience_error: ''
  });
  const [showStats, setShowStats] = useState(false);
  const [isInitialized, setIsInitialized] = useState(false);

  // Состояние для сортировки (несколько столбцов: первый — основной)
  type SortEntry = { field: string; direction: 'asc' | 'desc' };
  const [sortColumns, setSortColumns] = useState<SortEntry[]>([]);

  // Refs для input полей фильтров для сохранения фокуса
  const filterRefs = useRef<{ [key: string]: HTMLInputElement | null }>({});

  // Сохраняем состояние фокуса для восстановления после перерендера
  const focusedFieldRef = useRef<string | null>(null);
  const cursorPositionRef = useRef<{ [key: string]: number }>({});

  // Состояние для раскрытых ячеек
  const [expandedCell, setExpandedCell] = useState<{
    id: string;
    width: number;
    direction: 'left' | 'right';
  } | null>(null);

  // Состояние для редактирования записей
  const [editingRecordId, setEditingRecordId] = useState<number | null>(null);
  const [editedValues, setEditedValues] = useState<Partial<DatabaseRecord>>({});
  const [originalValues, setOriginalValues] = useState<Partial<DatabaseRecord>>({});
  const [copiedCellId, setCopiedCellId] = useState<string | null>(null);

  // Состояние для toast уведомлений
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);

  // Состояние для контекстного меню
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    recordId: number;
    position: 'before' | 'after';
  } | null>(null);

  // Контекстное меню по ячейке (для intermediate: «Правильное»)
  const [cellContextMenu, setCellContextMenu] = useState<{
    x: number;
    y: number;
    recordId: number;
    field: 'week_type' | 'audience';
  } | null>(null);

  // Ширины колонок (id, день, пара, предмет, тип, аудитория, преподаватель, группа, подгруппа, курс, институт, направление, профиль, неделя)
  const DEFAULT_COLUMN_WIDTHS = [100, 120, 80, 200, 120, 120, 200, 120, 90, 80, 150, 180, 150, 120];
  const COLUMN_WIDTHS_KEY = 'timetable_db_column_widths';
  const [columnWidths, setColumnWidths] = useState<number[]>(() => {
    try {
      const saved = localStorage.getItem(COLUMN_WIDTHS_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as number[];
        if (Array.isArray(parsed) && parsed.length === COLUMN_KEYS.length) return parsed;
      }
    } catch (_) { }
    return [...DEFAULT_COLUMN_WIDTHS];
  });
  const [resizingCol, setResizingCol] = useState<number | null>(null);
  const resizeStartX = useRef(0);
  const resizeStartWidth = useRef(0);

  // Видимость колонок по вкладкам (сохраняем в localStorage отдельно для каждой вкладки)
  const VISIBLE_COLUMNS_BY_TABLE_KEY = 'timetable_db_visible_columns_by_table';
  const [visibleColumnsByTable, setVisibleColumnsByTable] = useState<Record<DbTableType, Record<string, boolean>>>(() => {
    try {
      const saved = localStorage.getItem(VISIBLE_COLUMNS_BY_TABLE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as Record<string, Record<string, boolean>>;
        const out = {} as Record<DbTableType, Record<string, boolean>>;
        (['timetable_cleaned', 'timetable_teacher', 'intermediate_timetable'] as DbTableType[]).forEach(table => {
          const def = getDefaultVisibleForTable(table);
          const keys = COLUMNS_FOR_TABLE[table];
          out[table] = keys.reduce<Record<string, boolean>>((acc, k) => ({
            ...acc,
            [k]: parsed[table]?.[k] !== undefined ? parsed[table][k] !== false : def[k]
          }), {});
        });
        return out;
      }
    } catch (_) { }
    return {
      timetable_cleaned: getDefaultVisibleForTable('timetable_cleaned'),
      timetable_teacher: getDefaultVisibleForTable('timetable_teacher'),
      intermediate_timetable: getDefaultVisibleForTable('intermediate_timetable')
    };
  });
  const visibleColumnKeys = useMemo(
    () => COLUMNS_FOR_TABLE[activeTable].filter(k => visibleColumnsByTable[activeTable]?.[k] !== false),
    [activeTable, visibleColumnsByTable]
  );

  const getColumnLabel = useCallback((key: string): string => {
    if (activeTable === 'intermediate_timetable') return INTERMEDIATE_LABELS[key] || key;
    return COLUMN_LABELS[key as ColumnKey] || key;
  }, [activeTable]);

  const toggleColumnVisibility = useCallback((key: string) => {
    setVisibleColumnsByTable(prev => {
      const table = activeTable;
      const nextTable = { ...prev[table], [key]: !prev[table]?.[key] };
      const next = { ...prev, [table]: nextTable };
      try {
        localStorage.setItem(VISIBLE_COLUMNS_BY_TABLE_KEY, JSON.stringify(next));
      } catch (_) { }
      return next;
    });
  }, [activeTable]);
  const [showColumnsMenu, setShowColumnsMenu] = useState(false);
  const columnsMenuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (showColumnsMenu && columnsMenuRef.current && !columnsMenuRef.current.contains(e.target as Node)) {
        setShowColumnsMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showColumnsMenu]);

  const resetColumnWidths = useCallback(() => {
    setColumnWidths([...DEFAULT_COLUMN_WIDTHS]);
    try {
      localStorage.removeItem(COLUMN_WIDTHS_KEY);
    } catch (_) { }
  }, []);

  // При добавлении/удалении колонки (переключение видимости) — сброс ширин по умолчанию
  const prevVisibleKeysRef = useRef(visibleColumnKeys.join(','));
  const isFirstVisibleKeysRef = useRef(true);
  useEffect(() => {
    const key = visibleColumnKeys.join(',');
    if (isFirstVisibleKeysRef.current) {
      isFirstVisibleKeysRef.current = false;
      prevVisibleKeysRef.current = key;
      return;
    }
    if (prevVisibleKeysRef.current !== key) {
      prevVisibleKeysRef.current = key;
      setColumnWidths([...DEFAULT_COLUMN_WIDTHS]);
      try {
        localStorage.removeItem(COLUMN_WIDTHS_KEY);
      } catch (_) { }
    }
  }, [visibleColumnKeys]);

  // Используем useDebounce для оптимизации запросов (800мс задержка)
  const debouncedFilters = useDebounce<Filters>(filters, 800);

  const API_BASE = import.meta.env.VITE_API_URL || '/api';
  const queryClient = useQueryClient();

  // Восстанавливаем состояние из URL при загрузке
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);

    const tableParam = params.get('table');
    if (tableParam === 'timetable_teacher' || tableParam === 'timetable_cleaned' || tableParam === 'intermediate_timetable') {
      setActiveTable(tableParam);
    }

    // Восстанавливаем фильтры
    const restoredFilters: Filters = {
      day_of_week: params.get('day_of_week') || '',
      pair_number: params.get('pair_number') || '',
      subject_name: params.get('subject_name') || '',
      lecture_type: params.get('lecture_type') || '',
      audience: params.get('audience') || '',
      fio: params.get('fio') || '',
      teacher: params.get('teacher') || '',
      group_name: params.get('group_name') || '',
      subgroup: params.get('subgroup') || '',
      week_type: params.get('week_type') || '',
      institute: params.get('institute') || '',
      course: params.get('course') || '',
      direction: params.get('direction') || '',
      profile: params.get('profile') || '',
      has_error: params.get('has_error') || '',
      week_error: params.get('week_error') || '',
      audience_error: params.get('audience_error') || ''
    };
    setFilters(restoredFilters);

    // Восстанавливаем страницу
    const page = parseInt(params.get('page') || '1', 10);
    if (page > 0) {
      setCurrentPage(page);
    }

    // Восстанавливаем состояние показа статистики
    setShowStats(params.get('showStats') === 'true');

    // Восстанавливаем сортировку (несколько столбцов через запятую)
    const sortBy = params.get('sort_by');
    const sortOrder = params.get('sort_order');
    if (sortBy) {
      const fields = sortBy.split(',').map(s => s.trim()).filter(Boolean);
      const orders = (sortOrder || '').split(',').map(s => (s.trim().toLowerCase() === 'desc' ? 'desc' : 'asc'));
      const restored: SortEntry[] = fields.map((f, i) => ({ field: f, direction: orders[i] ?? 'asc' }));
      setSortColumns(restored.length ? restored : []);
    }

    setIsInitialized(true);
  }, []);

  // Обновляем URL при изменении состояния
  const updateURL = (updates: Record<string, string | number | boolean>) => {
    const params = new URLSearchParams(window.location.search);

    Object.entries(updates).forEach(([key, value]) => {
      if (value === '' || value === false || value === 0) {
        params.delete(key);
      } else {
        params.set(key, String(value));
      }
    });

    window.history.pushState({}, '', `${window.location.pathname}?${params.toString()}`);
  };

  // Обновляем URL при переключении таблицы
  const setTable = useCallback((table: DbTableType) => {
    setActiveTable(table);
    setCurrentPage(1);
    updateURL({ table, page: 1 });
  }, [updateURL]);

  // Обновляем URL при изменении фильтров (с debounce, только после инициализации)
  useEffect(() => {
    if (!isInitialized) return;

    const timeoutId = setTimeout(() => {
      Object.entries(filters).forEach(([key, value]) => {
        updateURL({ [key]: value });
      });
    }, 300); // Задержка 300мс для уменьшения количества обновлений URL

    return () => clearTimeout(timeoutId);
  }, [filters, isInitialized]);

  // Обновляем URL при изменении страницы (только после инициализации)
  useEffect(() => {
    if (!isInitialized) return;
    updateURL({ page: currentPage });
  }, [currentPage, isInitialized]);

  // Синхронизируем activeTable в URL
  useEffect(() => {
    if (!isInitialized) return;
    updateURL({ table: activeTable });
  }, [activeTable, isInitialized]);

  // Обновляем URL при изменении состояния показа статистики (только после инициализации)
  useEffect(() => {
    if (!isInitialized) return;
    updateURL({ showStats });
  }, [showStats, isInitialized]);

  // Синхронизируем сортировку с URL
  useEffect(() => {
    if (!isInitialized) return;
    if (sortColumns.length === 0) {
      updateURL({ sort_by: '', sort_order: '' });
    } else {
      updateURL({
        sort_by: sortColumns.map(s => s.field).join(','),
        sort_order: sortColumns.map(s => s.direction).join(',')
      });
    }
  }, [sortColumns, isInitialized]);

  // Слушаем изменения в URL (например, при нажатии назад/вперед)
  useEffect(() => {
    const handlePopState = () => {
      const params = new URLSearchParams(window.location.search);
      const tableParam = params.get('table');
      if (tableParam === 'timetable_teacher' || tableParam === 'timetable_cleaned' || tableParam === 'intermediate_timetable') {
        setActiveTable(tableParam);
      }
      const restoredFilters: Filters = {
        day_of_week: params.get('day_of_week') || '',
        pair_number: params.get('pair_number') || '',
        subject_name: params.get('subject_name') || '',
        lecture_type: params.get('lecture_type') || '',
        audience: params.get('audience') || '',
        fio: params.get('fio') || '',
        teacher: params.get('teacher') || '',
        group_name: params.get('group_name') || '',
        subgroup: params.get('subgroup') || '',
        week_type: params.get('week_type') || '',
        institute: params.get('institute') || '',
        course: params.get('course') || '',
        direction: params.get('direction') || '',
        profile: params.get('profile') || '',
        has_error: params.get('has_error') || '',
        week_error: params.get('week_error') || '',
        audience_error: params.get('audience_error') || ''
      };
      setFilters(restoredFilters);

      const page = parseInt(params.get('page') || '1', 10);
      if (page > 0) {
        setCurrentPage(page);
      }

      setShowStats(params.get('showStats') === 'true');

      const sortBy = params.get('sort_by');
      const sortOrder = params.get('sort_order');
      if (sortBy) {
        const fields = sortBy.split(',').map(s => s.trim()).filter(Boolean);
        const orders = (sortOrder || '').split(',').map(s => (s.trim().toLowerCase() === 'desc' ? 'desc' : 'asc'));
        setSortColumns(fields.map((f, i) => ({ field: f, direction: (orders[i] ?? 'asc') as 'asc' | 'desc' })));
      } else {
        setSortColumns([]);
      }
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  // Убрали логику закрытия фильтров - они теперь всегда видны

  // Маппинг названий колонок на поля базы данных для сортировки (для intermediate — по ключу поля)
  const columnToSortField: Record<string, string> = useMemo(() => {
    const base: Record<string, string> = {
      'ID': 'id',
      'День': 'day_of_week',
      'Пара': 'pair_number',
      'Предмет': 'subject_name',
      'Тип': 'lecture_type',
      'Аудитория': 'audience',
      'Ауд.': 'audience',
      'Преподаватель': 'fio',
      'Группа': 'group_name',
      'Подгруппа': 'subgroup',
      'п/г': 'subgroup',
      'Курс': 'course',
      'Институт': 'institute',
      'Направление': 'direction',
      'Профиль': 'profile',
      'Неделя': 'week_type'
    };
    if (activeTable === 'intermediate_timetable') {
      INTERMEDIATE_COLUMN_KEYS.forEach(k => { base[INTERMEDIATE_LABELS[k] || k] = k; });
    }
    return base;
  }, [activeTable]);

  // Мемоизируем параметры запроса для оптимизации (используем debounced фильтры)
  const recordsQueryParams = useMemo(() => {
    const params: any = { page: currentPage, limit: 20, table: activeTable };
    Object.keys(debouncedFilters).forEach(key => {
      if (debouncedFilters[key as keyof Filters]) {
        params[key] = debouncedFilters[key as keyof Filters];
      }
    });
    if (sortColumns.length > 0) {
      params.sort_by = sortColumns.map(s => s.field).join(',');
      params.sort_order = sortColumns.map(s => s.direction).join(',');
    }
    return params;
  }, [currentPage, debouncedFilters, sortColumns, activeTable, columnToSortField]);

  // Обработчик клика на заголовок для сортировки. Обычный клик — основной столбец (или смена направления). Shift+клик — добавить как следующий уровень.
  const handleSort = useCallback((column: string, shiftKey: boolean) => {
    const sortField = columnToSortField[column];
    if (!sortField) return;

    setSortColumns(prev => {
      const idx = prev.findIndex(s => s.field === sortField);
      if (shiftKey) {
        // Shift+клик: добавить в конец или переключить направление, если уже есть
        if (idx >= 0) {
          const next = [...prev];
          next[idx] = { ...next[idx], direction: next[idx].direction === 'asc' ? 'desc' : 'asc' };
          return next;
        }
        return [...prev, { field: sortField, direction: 'asc' as const }];
      }
      // Обычный клик: сделать этот столбец единственным (или переключить направление, если он один)
      if (idx === 0 && prev.length === 1) {
        return [{ field: sortField, direction: prev[0].direction === 'asc' ? 'desc' : 'asc' }];
      }
      return [{ field: sortField, direction: 'asc' as const }];
    });
    setCurrentPage(1);
  }, [columnToSortField]);

  // Запрос статистики с React Query (с учётом выбранной таблицы)
  const { data: stats, isLoading: statsLoading } = useQuery<DatabaseStats>({
    queryKey: ['db-stats', activeTable],
    queryFn: async () => {
      const response = await axios.get(`${API_BASE}/db/stats`, { params: { table: activeTable } });
      return response.data;
    },
    refetchInterval: 60000,
  });

  // Запрос записей с React Query (params уже содержат table: activeTable)
  const { data: recordsData, isLoading: recordsLoading, error: recordsError } = useQuery({
    queryKey: ['db-records', recordsQueryParams],
    queryFn: async () => {
      const response = await axios.get(`${API_BASE}/db/records`, { params: recordsQueryParams });
      return response.data;
    },
    staleTime: 10000, // Кешируем на 10 секунд
    gcTime: 30000, // Храним в кеше 30 секунд
    enabled: isInitialized, // Запрос только после инициализации
    // Не обновляем данные во время ввода - только после debounce
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    // Не обновляем при изменении фокуса или переподключении
    refetchOnReconnect: false,
  });

  const records: DatabaseRecord[] = recordsData?.records || [];
  const totalPages = recordsData?.pages || 1;
  const totalRecords = recordsData?.total || 0;
  const loading = recordsLoading || statsLoading;

  // Веса колонок: приоритет у колонок с малым текстом (полностью видны); длинный текст — уже, частично
  const contentWeights = useMemo((): Record<string, number> => {
    const pxPerChar = 8;
    const shortThreshold = 8;
    const maxCharsLong = 16;
    const longWeightFactor = 0.6;
    const keys = activeTable === 'intermediate_timetable' ? [...INTERMEDIATE_COLUMN_KEYS] : COLUMN_KEYS;
    const getLabel = (k: string) => activeTable === 'intermediate_timetable' ? (INTERMEDIATE_LABELS[k] || '') : (COLUMN_LABELS[k as ColumnKey] || '');

    const rawWeights: number[] = [];
    keys.forEach((key, idx) => {
      const labelLen = getLabel(key).length;
      if (records.length > 0) {
        const lengths = records.map(r => {
          const val = key === 'fio' ? (r.fio ?? r.teacher ?? '') : (r as any)[key];
          return String(val ?? '').length;
        });
        const maxLen = lengths.length ? Math.max(0, ...lengths) : 0;
        let w: number;
        if (maxLen <= shortThreshold) {
          const targetLen = Math.max(labelLen, maxLen, 2);
          w = Math.max(24, targetLen * pxPerChar);
        } else {
          const targetLen = Math.max(labelLen, Math.min(maxLen, maxCharsLong));
          w = Math.max(24, targetLen * pxPerChar * longWeightFactor);
        }
        rawWeights.push(w);
      } else {
        const w = Math.max(24, DEFAULT_COLUMN_WIDTHS[idx] ?? labelLen * pxPerChar);
        rawWeights.push(w);
      }
    });

    const sorted = [...rawWeights].sort((a, b) => a - b);
    const median = sorted[Math.floor(sorted.length / 2)] ?? 100;
    const cap = Math.max(median * 2, 160);

    const out: Record<string, number> = {};
    keys.forEach((key, idx) => {
      out[key as string] = Math.min(rawWeights[idx], cap);
    });
    return out;
  }, [records, activeTable]);

  // Шаблон колонок грида: ручной ресайз — в px, остальные — по весам (fr), заполняют 100%
  const gridTemplateColumns = useMemo(() => {
    return (visibleColumnKeys as string[]).map((k) => {
      const colIndex = activeTable === 'intermediate_timetable' ? (visibleColumnKeys as string[]).indexOf(k) : COLUMN_KEYS.indexOf(k as ColumnKey);
      const userWidth = (columnWidths as number[])[colIndex];
      const defaultWidth = (DEFAULT_COLUMN_WIDTHS as number[])[colIndex];
      const isUserResized = userWidth !== defaultWidth;
      return isUserResized ? `${Math.max(60, Math.min(600, userWidth))}px` : `minmax(60px, ${(contentWeights as Record<string, number>)[k] ?? 100}fr)`;
    }).join(' ');
  }, [visibleColumnKeys, contentWeights, columnWidths, activeTable]);

  // Восстанавливаем фокус после обновления данных
  useLayoutEffect(() => {
    if (focusedFieldRef.current) {
      const field = focusedFieldRef.current;
      const input = filterRefs.current[field];
      const cursorPos = cursorPositionRef.current[field] || 0;

      if (input && input.isConnected) {
        // Восстанавливаем фокус синхронно (до отрисовки)
        if (document.activeElement !== input) {
          input.focus();
        }
        // Восстанавливаем позицию курсора
        const value = filters[field as keyof Filters] || '';
        const newCursorPos = Math.min(cursorPos, value.length);
        try {
          // Устанавливаем курсор только если поле в фокусе
          if (document.activeElement === input) {
            input.setSelectionRange(newCursorPos, newCursorPos);
          }
        } catch (e) {
          // Игнорируем ошибки
        }
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recordsData]); // Только при обновлении данных, не при изменении filters

  // Обрабатываем ошибки запросов (после объявления recordsError)
  useEffect(() => {
    if (recordsError) {
      setError((recordsError as any).response?.data?.error || 'Ошибка при загрузке записей');
    } else {
      setError(null);
    }
  }, [recordsError]);

  const handleFilterChange = useCallback((field: keyof Filters, value: string) => {
    // Сохраняем позицию курсора и фокус перед обновлением
    const input = filterRefs.current[field];
    let cursorPos = 0;
    let wasFocused = false;

    if (input) {
      cursorPos = input.selectionStart || value.length;
      wasFocused = document.activeElement === input;

      // Сохраняем состояние для восстановления после перерендера
      if (wasFocused) {
        focusedFieldRef.current = field;
        cursorPositionRef.current[field] = cursorPos;
      }
    }

    // Обновляем фильтры немедленно (для отображения в input)
    // Используем функциональное обновление, чтобы не зависеть от предыдущего состояния
    setFilters(prev => {
      const newFilters = {
        ...prev,
        [field]: value
      };
      return newFilters;
    });

    // Страницу сбрасываем, но URL обновляем только после debounce
    setCurrentPage(1);
    // URL обновится автоматически через useEffect с debouncedFilters

    // Восстанавливаем фокус и позицию курсора СРАЗУ после обновления состояния
    if (wasFocused && input) {
      // Сохраняем ссылку на input для использования в замыкании
      const inputElement = input;
      const savedCursorPos = cursorPos;
      const newValue = value;

      // Восстанавливаем фокус синхронно (до отрисовки)
      if (inputElement && inputElement.isConnected) {
        if (document.activeElement !== inputElement) {
          inputElement.focus();
        }
        const newCursorPos = Math.min(savedCursorPos, newValue.length);
        try {
          if (document.activeElement === inputElement) {
            inputElement.setSelectionRange(newCursorPos, newCursorPos);
          }
        } catch (e) {
          // Игнорируем ошибки
        }
      }

      // Дополнительная попытка через requestAnimationFrame (перед отрисовкой)
      requestAnimationFrame(() => {
        if (inputElement && inputElement.isConnected) {
          if (document.activeElement !== inputElement) {
            inputElement.focus();
          }
          const newCursorPos = Math.min(savedCursorPos, newValue.length);
          try {
            if (document.activeElement === inputElement) {
              inputElement.setSelectionRange(newCursorPos, newCursorPos);
            }
          } catch (e) {
            // Игнорируем ошибки
          }
        }
      });
    }
  }, []);

  const clearFilters = () => {
    const emptyFilters: Filters = {
      day_of_week: '',
      pair_number: '',
      subject_name: '',
      lecture_type: '',
      audience: '',
      fio: '',
      teacher: '',
      group_name: '',
      subgroup: '',
      week_type: '',
      institute: '',
      course: '',
      direction: '',
      profile: '',
      has_error: '',
      week_error: '',
      audience_error: ''
    };
    setFilters(emptyFilters);
    setCurrentPage(1);

    // Очищаем фильтры из URL
    const params = new URLSearchParams(window.location.search);
    Object.keys(emptyFilters).forEach(key => {
      params.delete(key);
    });
    params.set('page', '1');
    window.history.pushState({}, '', `${window.location.pathname}?${params.toString()}`);
  };

  const hasActiveFilters = () => {
    return Object.values(filters).some(value => value.trim() !== '');
  };

  // Маппинг подписей колонок на поля фильтров (для intermediate — маппинг колонок на общие фильтры)
  const columnToFilterMap: Record<string, keyof Filters | null> = useMemo(() => {
    const map: Record<string, keyof Filters | null> = {};
    if (activeTable === 'intermediate_timetable') {
      const intermediateToFilter: Record<string, keyof Filters | null> = {
        id: null, day_of_week: 'day_of_week', pair_number: 'pair_number', subject_name: 'subject_name',
        discipline_original: null,
        lecture_type: 'lecture_type', audience: 'audience', group_name: 'group_name', week_type: 'week_type',
        subgroup: 'subgroup', institute: 'institute', course: 'course', direction: 'direction',
        department: null, fio: 'fio', week_error: 'week_error', audience_error: 'audience_error'
      };
      INTERMEDIATE_COLUMN_KEYS.forEach((k) => {
        map[INTERMEDIATE_LABELS[k] || k] = intermediateToFilter[k] ?? null;
      });
    } else {
      COLUMN_KEYS.forEach((k) => {
        const label = COLUMN_LABELS[k];
        map[label] = k === 'id' ? null : (k as keyof Filters);
      });
    }
    return map;
  }, [activeTable]);

  // Убрали handleHeaderClick - фильтры теперь всегда видны

  const getFilterValue = (columnName: string): string => {
    const filterKey = columnToFilterMap[columnName];
    return filterKey ? filters[filterKey] : '';
  };

  // Функция для вычисления ширины раскрытия ячейки
  const calculateCellWidth = useCallback((cellElement: HTMLElement, contentElement: HTMLElement): { width: number; direction: 'left' | 'right' } => {
    // Создаем временный элемент для измерения реальной ширины текста
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
    const padding = 1.5 * 16; // 0.75rem * 2 = 1.5rem в пикселях
    const contentWidth = scrollWidth + padding;

    // Максимальная ширина (80vw или 800px, что меньше)
    const maxWidth = Math.min(window.innerWidth * 0.8, 800);
    const finalWidth = Math.min(contentWidth, maxWidth);

    // Определяем направление раскрытия
    const cellRect = cellElement.getBoundingClientRect();
    const spaceRight = window.innerWidth - cellRect.right;

    // Если места справа достаточно - раскрываем вправо, иначе влево
    const direction = spaceRight >= finalWidth ? 'right' : 'left';

    document.body.removeChild(tempElement);

    return { width: finalWidth, direction };
  }, []);

  // Обработчик наведения на ячейку
  const handleCellMouseEnter = useCallback((e: React.MouseEvent<HTMLDivElement>, cellId: string) => {
    const cellElement = e.currentTarget;
    const contentElement = cellElement.querySelector('.cell-content') as HTMLElement;

    if (!contentElement) return;

    // Проверяем, нужна ли раскрытие (если текст обрезан)
    const isOverflowing = contentElement.scrollWidth > contentElement.clientWidth;

    if (isOverflowing) {
      const { width, direction } = calculateCellWidth(cellElement, contentElement);
      setExpandedCell({ id: cellId, width, direction });
    }
  }, [calculateCellWidth]);

  // Обработчик ухода мыши с ячейки
  const handleCellMouseLeave = useCallback(() => {
    setExpandedCell(null);
  }, []);

  const handleColumnFilterChange = useCallback((columnName: string, value: string) => {
    const filterKey = columnToFilterMap[columnName];
    if (filterKey) {
      // Обновляем фильтр немедленно (для отображения в input)
      // Debounce будет применен автоматически через useDebounce
      handleFilterChange(filterKey, value);
    }
  }, [handleFilterChange]);

  const clearDatabase = async () => {
    const tableLabel = activeTable === 'timetable_teacher' ? 'Занятость преподавателей' : activeTable === 'intermediate_timetable' ? 'Промежуточное расписание' : 'Спаршенное расписание';
    if (!window.confirm(`Вы уверены, что хотите очистить таблицу «${tableLabel}»? Это действие нельзя отменить.`)) {
      return;
    }

    try {
      await axios.post(`${API_BASE}/db/clear`, {}, { params: { table: activeTable } });
      setCurrentPage(1);
      queryClient.invalidateQueries({ queryKey: ['db-stats'] });
      queryClient.invalidateQueries({ queryKey: ['db-records'] });
      alert('Таблица успешно очищена');
    } catch (err: any) {
      setError(err.response?.data?.error || 'Ошибка при очистке базы данных');
    }
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Нет данных';
    const date = new Date(dateString);
    return date.toLocaleString('ru-RU');
  };

  // Функция копирования в буфер обмена
  const copyToClipboard = async (text: string, cellId: string) => {
    try {
      await navigator.clipboard.writeText(text);
      // Визуальная обратная связь
      setCopiedCellId(cellId);
      setTimeout(() => setCopiedCellId(null), 1000);
    } catch (err) {
      // Fallback для старых браузеров
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      textArea.style.opacity = '0';
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      // Визуальная обратная связь
      setCopiedCellId(cellId);
      setTimeout(() => setCopiedCellId(null), 1000);
    }
  };

  // Функции для редактирования записей
  const startEditing = (record: DatabaseRecord) => {
    setEditingRecordId(record.id);
    setOriginalValues({ ...record });
    setEditedValues({ ...record });
  };

  const cancelEditing = () => {
    setEditingRecordId(null);
    setEditedValues({});
    setOriginalValues({});
  };

  const handleFieldChange = (field: string, value: string | number | null) => {
    if (editingRecordId) {
      let processedValue: string | number | null = value === '' ? null : value;

      // Обрабатываем числовые поля
      if (field === 'pair_number' || field === 'subgroup' || field === 'num_subgroups') {
        if (processedValue === null || processedValue === '') {
          processedValue = null;
        } else {
          const numValue = Number(processedValue);
          processedValue = isNaN(numValue) ? null : numValue;
        }
      }

      setEditedValues(prev => ({
        ...prev,
        [field]: processedValue
      }));
    }
  };

  const saveRecord = async (recordId: number) => {
    try {
      // Подготавливаем данные для отправки
      const dataToSend: any = {};
      Object.keys(editedValues).forEach(key => {
        if (key !== 'id' && editedValues[key as keyof DatabaseRecord] !== originalValues[key as keyof DatabaseRecord]) {
          dataToSend[key] = editedValues[key as keyof DatabaseRecord];
        }
      });

      if (Object.keys(dataToSend).length === 0) {
        // Нет изменений
        cancelEditing();
        return;
      }

      await axios.put(`${API_BASE}/db/records/${recordId}`, dataToSend, { params: { table: activeTable } });

      queryClient.invalidateQueries({ queryKey: ['db-records'] });
      queryClient.invalidateQueries({ queryKey: ['db-stats'] });

      setEditingRecordId(null);
      setEditedValues({});
      setOriginalValues({});

      // Показываем toast уведомление об успехе
      setToast({ message: 'Запись успешно сохранена', type: 'success' });
    } catch (err: any) {
      const errorMessage = err.response?.data?.error || 'Ошибка при сохранении записи';
      setError(errorMessage);
      setToast({ message: errorMessage, type: 'error' });
    }
  };

  // Отметить поле как правильное (intermediate_timetable: скопировать значение в cleaned/teacher)
  const fixFieldAsCorrect = async (recordId: number, field: 'week_type' | 'audience') => {
    try {
      await axios.put(`${API_BASE}/db/records/${recordId}/fix-field`, { field }, { params: { table: activeTable } });
      queryClient.invalidateQueries({ queryKey: ['db-records'] });
      queryClient.invalidateQueries({ queryKey: ['db-stats'] });
      setCellContextMenu(null);
      setToast({ message: 'Поле отмечено как правильное', type: 'success' });
    } catch (err: any) {
      const errorMessage = err.response?.data?.error || 'Ошибка при обновлении';
      setToast({ message: errorMessage, type: 'error' });
      setCellContextMenu(null);
    }
  };

  // Функция для создания копии записи
  const duplicateRecord = async (recordId: number, position: 'before' | 'after') => {
    try {
      // Находим запись в текущем списке
      const record = records.find((r: DatabaseRecord) => r.id === recordId);
      if (!record) {
        setToast({ message: 'Запись не найдена', type: 'error' });
        setContextMenu(null);
        return;
      }

      // Создаем копию без ID, добавляем параметры позиционирования
      const { id, ...recordData } = record;
      const dataToSend = {
        ...recordData,
        _reference_id: recordId,
        _position: position
      };

      await axios.post(`${API_BASE}/db/records`, dataToSend, { params: { table: activeTable } });

      queryClient.invalidateQueries({ queryKey: ['db-records'] });
      queryClient.invalidateQueries({ queryKey: ['db-stats'] });

      setToast({ message: 'Копия записи успешно создана', type: 'success' });
      setContextMenu(null);
    } catch (err: any) {
      const errorMessage = err.response?.data?.error || 'Ошибка при создании копии записи';
      setToast({ message: errorMessage, type: 'error' });
      setContextMenu(null);
    }
  };

  // Функция для создания пустой записи
  const createEmptyRecord = async (recordId: number, position: 'before' | 'after') => {
    try {
      // Создаем пустую запись с параметрами позиционирования
      const emptyRecord: any = {
        day_of_week: null,
        pair_number: null,
        subject_name: null,
        lecture_type: null,
        audience: null,
        fio: null,
        teacher: null,
        group_name: null,
        week_type: null,
        subgroup: null,
        institute: null,
        course: null,
        direction: null,
        department: null,
        is_external: null,
        is_remote: null,
        num_subgroups: null,
        _reference_id: recordId,
        _position: position
      };

      await axios.post(`${API_BASE}/db/records`, emptyRecord, { params: { table: activeTable } });

      queryClient.invalidateQueries({ queryKey: ['db-records'] });
      queryClient.invalidateQueries({ queryKey: ['db-stats'] });

      setToast({ message: 'Пустая запись успешно создана', type: 'success' });
      setContextMenu(null);
    } catch (err: any) {
      const errorMessage = err.response?.data?.error || 'Ошибка при создании пустой записи';
      setToast({ message: errorMessage, type: 'error' });
      setContextMenu(null);
    }
  };

  // Функция для удаления записи
  const deleteRecord = async (recordId: number) => {
    if (!window.confirm('Вы уверены, что хотите удалить эту запись?')) {
      setContextMenu(null);
      return;
    }

    try {
      await axios.delete(`${API_BASE}/db/records/${recordId}`, { params: { table: activeTable } });

      queryClient.invalidateQueries({ queryKey: ['db-records'] });
      queryClient.invalidateQueries({ queryKey: ['db-stats'] });

      setToast({ message: 'Запись успешно удалена', type: 'success' });
      setContextMenu(null);
    } catch (err: any) {
      const errorMessage = err.response?.data?.error || 'Ошибка при удалении записи';
      setToast({ message: errorMessage, type: 'error' });
      setContextMenu(null);
    }
  };

  // Обработчик правого клика на строке (контекстное меню: редактировать, дублировать, пустая, удалить)
  const handleRowContextMenu = (e: React.MouseEvent, record: DatabaseRecord) => {
    e.preventDefault();
    e.stopPropagation();

    const rowElement = e.currentTarget as HTMLElement;
    const rowRect = rowElement.getBoundingClientRect();
    const clickY = e.clientY;
    const rowCenterY = rowRect.top + rowRect.height / 2;
    const position = clickY < rowCenterY ? 'before' : 'after';

    setContextMenu({
      x: e.clientX,
      y: e.clientY,
      recordId: record.id,
      position
    });
  };

  // Закрытие контекстного меню при клике вне его
  const tableContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClose = () => {
      setContextMenu(null);
      setCellContextMenu(null);
    };

    if (contextMenu || cellContextMenu) {
      document.addEventListener('click', handleClose);
      document.addEventListener('contextmenu', handleClose);
      window.addEventListener('scroll', handleClose, true);
      const tableEl = tableContainerRef.current;
      if (tableEl) tableEl.addEventListener('scroll', handleClose);
      return () => {
        document.removeEventListener('click', handleClose);
        document.removeEventListener('contextmenu', handleClose);
        window.removeEventListener('scroll', handleClose, true);
        if (tableEl) tableEl.removeEventListener('scroll', handleClose);
      };
    }
  }, [contextMenu, cellContextMenu]);

  // Изменение ширины колонки перетаскиванием
  const handleResizeStart = useCallback((e: React.MouseEvent, colIndex: number) => {
    e.preventDefault();
    setResizingCol(colIndex);
    resizeStartX.current = e.clientX;
    // Берём фактическую ширину колонки из DOM, чтобы после сброса (fr) не было скачка
    const cell = (e.target as HTMLElement).closest('.grid-table-cell');
    const actualWidth = cell ? cell.getBoundingClientRect().width : columnWidths[colIndex];
    resizeStartWidth.current = actualWidth;
  }, [columnWidths]);

  useEffect(() => {
    if (resizingCol === null) return;
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';
    const onMove = (e: MouseEvent) => {
      const delta = e.clientX - resizeStartX.current;
      const newW = Math.max(60, Math.min(600, resizeStartWidth.current + delta));
      setColumnWidths(prev => {
        const next = [...prev];
        next[resizingCol] = newW;
        return next;
      });
    };
    const onUp = () => setResizingCol(null);
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
  }, [resizingCol]); // columnWidths in onUp will be stale; save on next effect cleanup or in a ref - see below

  // Сохраняем ширины в localStorage при изменении (после окончания ресайза)
  useEffect(() => {
    if (resizingCol === null) {
      try {
        localStorage.setItem(COLUMN_WIDTHS_KEY, JSON.stringify(columnWidths));
      } catch (_) { }
    }
  }, [columnWidths, resizingCol]);

  return (
    <div className="database-view">
      <div className="card">
        <div className="card-header">
          <h2>Статистика базы данных</h2>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              className="button"
              onClick={() => {
                setShowStats(!showStats);
                updateURL({ showStats: !showStats });
              }}
            >
              {showStats ? 'Скрыть статистику' : 'Показать статистику'}
            </button>
            <button className="button danger" onClick={clearDatabase}>
              Очистить БД
            </button>
          </div>
        </div>

        {error && (
          <div className="message error">
            <strong>Ошибка:</strong> {error}
          </div>
        )}

        {showStats && stats && (
          <>
            <div className="stats-grid">
              <div className="stat-card">
                <h3>{stats.total}</h3>
                <p>Всего записей</p>
              </div>
              <div className="stat-card">
                <h3>{stats.by_day.length}</h3>
                <p>Дней недели</p>
              </div>
              <div className="stat-card">
                <h3>{stats.by_type.length}</h3>
                <p>Типов занятий</p>
              </div>
            </div>

            {stats.last_update && (
              <div className="message info">
                <strong>Последнее обновление:</strong> {formatDate(stats.last_update)}
              </div>
            )}

            {stats.by_day.length > 0 && (
              <div className="stats-section">
                <h3>Распределение по дням недели</h3>
                <div className="stats-list">
                  {stats.by_day.map((item) => (
                    <div key={item.day_of_week} className="stats-item">
                      <span className="stats-label">{item.day_of_week || 'Не указано'}:</span>
                      <span className="stats-value">{item.count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {stats.by_type.length > 0 && (
              <div className="stats-section">
                <h3>Распределение по типам занятий</h3>
                <div className="stats-list">
                  {stats.by_type.map((item) => (
                    <div key={item.lecture_type} className="stats-item">
                      <span className="stats-label">{item.lecture_type || 'Не указано'}:</span>
                      <span className="stats-value">{item.count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>

      <div className="card">
        <div className="card-header">
          <div>
            <div className="db-view-tabs">
              <button
                type="button"
                className={`db-view-tab ${activeTable === 'timetable_cleaned' ? 'active' : ''}`}
                onClick={() => setTable('timetable_cleaned')}
              >
                Спаршенное расписание
              </button>
              <button
                type="button"
                className={`db-view-tab ${activeTable === 'timetable_teacher' ? 'active' : ''}`}
                onClick={() => setTable('timetable_teacher')}
              >
                Занятость преподавателей
              </button>
              <button
                type="button"
                className={`db-view-tab ${activeTable === 'intermediate_timetable' ? 'active' : ''}`}
                onClick={() => setTable('intermediate_timetable')}
              >
                Промежуточное расписание
              </button>
            </div>
            <h2>Записи в базе данных</h2>
            {totalRecords > 0 && (
              <p className="records-count">
                Найдено записей: <strong>{totalRecords}</strong>
                {hasActiveFilters() && ' (с учетом фильтров)'}
              </p>
            )}
          </div>
          <div className="filter-controls">
            <div className="filter-hint">
              💡 Кликните на ячейку для копирования, двойной клик по строке для редактирования
            </div>
            {activeTable === 'intermediate_timetable' && (
              <div className="error-filter-buttons">
                <span className="error-filter-label">Фильтр по ошибкам:</span>
                <button
                  type="button"
                  className={`button error-filter-btn ${filters.has_error === 'true' ? 'active' : ''}`}
                  onClick={() => handleFilterChange('has_error', filters.has_error === 'true' ? '' : 'true')}
                  title="Показать только записи с ошибкой недели или аудитории"
                >
                  Только с ошибками
                </button>
                <button
                  type="button"
                  className={`button error-filter-btn ${filters.week_error === 'true' ? 'active' : ''}`}
                  onClick={() => handleFilterChange('week_error', filters.week_error === 'true' ? '' : 'true')}
                  title="Показать только записи, где неделя не совпадает с занятостью"
                >
                  Ошибка недели
                </button>
                <button
                  type="button"
                  className={`button error-filter-btn ${filters.audience_error === 'true' ? 'active' : ''}`}
                  onClick={() => handleFilterChange('audience_error', filters.audience_error === 'true' ? '' : 'true')}
                  title="Показать только записи, где аудитория не совпадает с занятостью"
                >
                  Ошибка аудитории
                </button>
              </div>
            )}
            <div className="columns-menu-wrapper" ref={columnsMenuRef}>
              <button
                type="button"
                className="button columns-toggle"
                onClick={() => setShowColumnsMenu(v => !v)}
                title="Показать или скрыть колонки"
              >
                Колонки
              </button>
              {showColumnsMenu && (
                <div className="columns-dropdown">
                  <div className="columns-dropdown-title">Видимость колонок ({activeTable === 'timetable_cleaned' ? 'Спаршенное расписание' : activeTable === 'timetable_teacher' ? 'Занятость преподавателей' : 'Промежуточное расписание'})</div>
                  {(COLUMNS_FOR_TABLE[activeTable] as string[]).map(key => (
                    <label key={key} className="columns-dropdown-item">
                      <input
                        type="checkbox"
                        checked={visibleColumnsByTable[activeTable]?.[key] !== false}
                        onChange={() => toggleColumnVisibility(key)}
                      />
                      <span>{getColumnLabel(key)}</span>
                    </label>
                  ))}
                  <div className="columns-dropdown-divider" />
                  <button
                    type="button"
                    className="columns-dropdown-action"
                    onClick={() => { resetColumnWidths(); setShowColumnsMenu(false); }}
                  >
                    Сбросить ширины колонок
                  </button>
                  <button
                    type="button"
                    className="columns-dropdown-action"
                    onClick={() => { clearFilters(); setShowColumnsMenu(false); }}
                  >
                    Очистить фильтры
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>


        {/* Таблица всегда отображается, даже если нет данных */}
        {(
          <>
            <div className="table-container" ref={tableContainerRef}>
              <div className="grid-table">
                <div className="grid-table-header" style={{ display: 'grid', width: '100%', gridTemplateColumns }}>
                  {(visibleColumnKeys as string[]).map((key) => {
                    const colIndex = activeTable === 'intermediate_timetable' ? (visibleColumnKeys as string[]).indexOf(key) : COLUMN_KEYS.indexOf(key as ColumnKey);
                    const label = getColumnLabel(key);
                    const filterable = key !== 'id';
                    return (
                      <div
                        key={key}
                        className="grid-table-cell header-cell-resizable"
                      >
                        <div
                          className={key === 'id' ? 'header-label' : 'header-label header-sortable'}
                          onClick={filterable ? (e) => handleSort(label, e.shiftKey) : undefined}
                          title={filterable ? 'Клик — сортировка по столбцу. Shift+клик — добавить уровень сортировки.' : undefined}
                        >
                          {label}
                          {filterable && (() => {
                            const sortField = columnToSortField[label];
                            const sortIdx = sortField != null ? sortColumns.findIndex(s => s.field === sortField) : -1;
                            const entry = sortIdx >= 0 ? sortColumns[sortIdx] : null;
                            return (
                              <span className="sort-arrows">
                                <span className={`sort-arrow ${entry?.direction === 'asc' ? 'active' : ''}`}>▲</span>
                                <span className={`sort-arrow ${entry?.direction === 'desc' ? 'active' : ''}`}>▼</span>
                                {sortIdx >= 0 && sortColumns.length > 1 && <span className="sort-order-badge">{sortIdx + 1}</span>}
                              </span>
                            );
                          })()}
                        </div>
                        {key === 'id' ? (
                          <input
                            type="text"
                            className="header-filter-input"
                            value=""
                            placeholder={COLUMN_PLACEHOLDERS.id}
                            title="ID не фильтруется"
                            disabled
                          />
                        ) : (
                          <input
                            key={`filter-${key}`}
                            ref={(el) => { filterRefs.current[key] = el; }}
                            type="text"
                            className="header-filter-input"
                            value={getFilterValue(label)}
                            onChange={(e) => { e.stopPropagation(); handleColumnFilterChange(label, e.target.value); }}
                            onKeyDown={(e) => e.stopPropagation()}
                            onKeyUp={(e) => e.stopPropagation()}
                            onFocus={(e) => {
                              e.stopPropagation();
                              focusedFieldRef.current = key;
                              const input = e.target as HTMLInputElement;
                              cursorPositionRef.current[key] = input.selectionStart || 0;
                            }}
                            onBlur={(e) => {
                              e.stopPropagation();
                              setTimeout(() => {
                                if (document.activeElement !== e.target) focusedFieldRef.current = null;
                              }, 100);
                            }}
                            onMouseDown={(e) => e.stopPropagation()}
                            onClick={(e) => e.stopPropagation()}
                            placeholder={activeTable === 'intermediate_timetable' ? `Фильтр: ${label}` : ((COLUMN_PLACEHOLDERS as Record<string, string>)[key] || '')}
                            title={`Поиск по колонке ${label}`}
                            autoComplete="off"
                          />
                        )}
                        <div className="column-resize-handle" onMouseDown={(e) => handleResizeStart(e, colIndex)} title="Изменить ширину" />
                      </div>
                    );
                  })}
                </div>
                <div className="grid-table-body">
                  {loading ? (
                    [...Array(10)].map((_, index) => (
                      <div key={index} className="grid-table-row skeleton-row" style={{ display: 'grid', width: '100%', gridTemplateColumns }}>
                        {visibleColumnKeys.map((k) => (
                          <div key={k} className="grid-table-cell"><div className="skeleton-cell"></div></div>
                        ))}
                      </div>
                    ))
                  ) : (
                    records.map((record: DatabaseRecord) => {
                      const isEditing = editingRecordId === record.id;
                      const currentRecord = isEditing ? { ...record, ...editedValues } : record;
                      const getValue = (value: any): string => (value === null || value === undefined || value === '' ? '' : String(value));
                      const cellId = `cell-${record.id}`;
                      const renderEditableCell = (field: keyof DatabaseRecord, cellIndex: number, displayValue: string) => {
                        const uniqueCellId = `${cellId}-${cellIndex}`;
                        const isExpanded = expandedCell?.id === uniqueCellId;
                        const expandDirection = expandedCell?.direction || 'right';
                        const expandWidth = expandedCell?.width || 0;
                        if (isEditing && field === 'id') {
                          return (
                            <div key={cellIndex} className="grid-table-cell id-cell-with-actions">
                              <div className="id-actions">
                                <button className="save-button" onClick={() => saveRecord(record.id)} title="Сохранить">✓</button>
                                <button className="cancel-button" onClick={cancelEditing} title="Отменить">✕</button>
                              </div>
                              <div className="id-value">{displayValue}</div>
                            </div>
                          );
                        }
                        if (isEditing && field !== 'id') {
                          if (field === 'day_of_week') {
                            return (
                              <div key={cellIndex} className="grid-table-cell editable-cell">
                                <select className="cell-select" value={getValue(currentRecord[field])} onChange={(e) => handleFieldChange(field, e.target.value || null)} onClick={(e) => e.stopPropagation()} onFocus={(e) => e.stopPropagation()}>
                                  <option value="">-</option>
                                  {['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье'].map(d => <option key={d} value={d}>{d}</option>)}
                                </select>
                              </div>
                            );
                          }
                          if (field === 'pair_number') {
                            return (
                              <div key={cellIndex} className="grid-table-cell editable-cell">
                                <select className="cell-select" value={getValue(currentRecord[field])} onChange={(e) => handleFieldChange(field, e.target.value === '' ? null : Number(e.target.value))} onClick={(e) => e.stopPropagation()} onFocus={(e) => e.stopPropagation()}>
                                  <option value="">-</option>
                                  {[1, 2, 3, 4, 5, 6, 7, 8].map(num => <option key={num} value={num}>{num}</option>)}
                                </select>
                              </div>
                            );
                          }
                          if (field === 'lecture_type') {
                            return (
                              <div key={cellIndex} className="grid-table-cell editable-cell">
                                <select className="cell-select" value={getValue(currentRecord[field])} onChange={(e) => handleFieldChange(field, e.target.value || null)} onClick={(e) => e.stopPropagation()} onFocus={(e) => e.stopPropagation()}>
                                  <option value="">-</option>
                                  {['лекция', 'практика', 'лабораторная', 'семинар'].map(t => <option key={t} value={t}>{t}</option>)}
                                </select>
                              </div>
                            );
                          }
                          if (field === 'week_type') {
                            return (
                              <div key={cellIndex} className="grid-table-cell editable-cell">
                                <select className="cell-select" value={getValue(currentRecord[field])} onChange={(e) => handleFieldChange(field, e.target.value || null)} onClick={(e) => e.stopPropagation()} onFocus={(e) => e.stopPropagation()}>
                                  <option value="">-</option>
                                  {['числитель', 'знаменатель', 'обе недели'].map(t => <option key={t} value={t}>{t}</option>)}
                                </select>
                              </div>
                            );
                          }
                          return (
                            <div key={cellIndex} className="grid-table-cell editable-cell">
                              <input type="text" className="cell-input" value={getValue(currentRecord[field])} onChange={(e) => handleFieldChange(String(field), e.target.value)} onClick={(e) => e.stopPropagation()} onFocus={(e) => e.stopPropagation()} />
                            </div>
                          );
                        }
                        const isErrorCell = activeTable === 'intermediate_timetable' && (
                          (field === 'week_type' && (record as any).week_error) ||
                          (field === 'audience' && (record as any).audience_error)
                        );
                        return (
                          <div
                            key={cellIndex}
                            className={`grid-table-cell expandable-cell ${copiedCellId === uniqueCellId ? 'cell-copied' : ''} ${isErrorCell ? 'cell-error' : ''}`}
                            onMouseEnter={(e) => handleCellMouseEnter(e, uniqueCellId)}
                            onMouseLeave={handleCellMouseLeave}
                            onDoubleClick={() => !isEditing && startEditing(record)}
                            onClick={(e) => { if (displayValue && displayValue !== '-') copyToClipboard(displayValue, uniqueCellId); e.stopPropagation(); }}
                            onContextMenu={isErrorCell ? (e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              setCellContextMenu({ x: e.clientX, y: e.clientY, recordId: record.id, field: field as 'week_type' | 'audience' });
                            } : undefined}
                            title={isErrorCell ? (field === 'week_type' ? 'Ошибка: неделя не совпадает с занятостью. ПКМ — отметить как правильное' : 'Ошибка: аудитория не совпадает с занятостью. ПКМ — отметить как правильное') : 'Клик — копировать, двойной клик — редактировать'}
                          >
                            <div className="cell-content" data-expanded={isExpanded} data-direction={expandDirection} style={isExpanded ? { width: `${expandWidth}px`, minWidth: `${expandWidth}px`, ...(expandDirection === 'left' ? { right: 0, left: 'auto' } : { left: 0, right: 'auto' }) } : {}}>
                              {displayValue || '-'}
                            </div>
                          </div>
                        );
                      };
                      return (
                        <div key={record.id} className={`grid-table-row ${isEditing ? 'editing-row' : ''}`} style={{ display: 'grid', width: '100%', gridTemplateColumns }} onContextMenu={(e) => !isEditing && handleRowContextMenu(e, record)}>
                          {(visibleColumnKeys as string[]).map((key) => {
                            const colIndex = activeTable === 'intermediate_timetable' ? (visibleColumnKeys as string[]).indexOf(key) : COLUMN_KEYS.indexOf(key as ColumnKey);
                            const displayValue = activeTable === 'intermediate_timetable' ? getValue((currentRecord as any)[key]) : (key === 'fio' ? getValue(currentRecord.fio || currentRecord.teacher) : getValue((currentRecord as any)[key]));
                            return renderEditableCell(key as keyof DatabaseRecord, colIndex, displayValue);
                          })}
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            </div>
          </>
        )}

        {records.length === 0 && !loading && (
          <div className="message info">
            {hasActiveFilters()
              ? 'Записи не найдены. Попробуйте изменить фильтры.'
              : 'База данных пуста. Запустите скрипты для заполнения данных.'}
          </div>
        )}

        {totalPages > 0 && (
          <div className="pagination">
            <button
              onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
              disabled={currentPage === 1 || loading}
            >
              Назад
            </button>
            <span>
              Страница {currentPage} из {totalPages}
            </span>
            <button
              onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
              disabled={currentPage === totalPages || loading}
            >
              Вперед
            </button>
          </div>
        )}
      </div>

      {/* Toast уведомления */}
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
        />
      )}

      {/* Контекстное меню */}
      {contextMenu && (
        <div
          className="context-menu"
          style={{
            position: 'fixed',
            left: `${contextMenu.x}px`,
            top: `${contextMenu.y}px`,
            zIndex: 10001
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <button
            className="context-menu-item"
            onClick={() => {
              const record = records.find(r => r.id === contextMenu.recordId);
              if (record) startEditing(record);
              setContextMenu(null);
            }}
          >
            Редактировать
          </button>
          <div className="context-menu-divider"></div>
          <button
            className="context-menu-item"
            onClick={() => duplicateRecord(contextMenu.recordId, contextMenu.position)}
          >
            {contextMenu.position === 'before' ? 'Создать копию выше' : 'Создать копию ниже'}
          </button>
          <button
            className="context-menu-item"
            onClick={() => createEmptyRecord(contextMenu.recordId, contextMenu.position)}
          >
            {contextMenu.position === 'before' ? 'Создать пустую выше' : 'Создать пустую ниже'}
          </button>
          <div className="context-menu-divider"></div>
          <button
            className="context-menu-item context-menu-item-danger"
            onClick={() => deleteRecord(contextMenu.recordId)}
          >
            Удалить запись
          </button>
          <div className="context-menu-divider"></div>
          <button
            className="context-menu-item"
            onClick={() => { resetColumnWidths(); setContextMenu(null); }}
          >
            Сбросить ширины колонок
          </button>
          <button
            className="context-menu-item"
            onClick={() => { clearFilters(); setContextMenu(null); }}
          >
            Очистить фильтры
          </button>
          <div className="context-menu-divider"></div>
          <button
            className="context-menu-item"
            onClick={() => setContextMenu(null)}
          >
            Отмена
          </button>
        </div>
      )}

      {/* Контекстное меню по ячейке с ошибкой (intermediate: «Правильное») */}
      {cellContextMenu && (
        <div
          className="context-menu"
          style={{
            position: 'fixed',
            left: `${cellContextMenu.x}px`,
            top: `${cellContextMenu.y}px`,
            zIndex: 10001
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <button
            className="context-menu-item"
            onClick={() => {
              fixFieldAsCorrect(cellContextMenu.recordId, cellContextMenu.field);
            }}
          >
            Правильное
          </button>
          <div className="context-menu-divider"></div>
          <button
            className="context-menu-item"
            onClick={() => setCellContextMenu(null)}
          >
            Отмена
          </button>
        </div>
      )}
    </div>
  );
};

export default DatabaseView;
