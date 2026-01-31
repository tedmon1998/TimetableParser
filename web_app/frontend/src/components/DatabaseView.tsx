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
  audience: 'Аудитория',
  fio: 'Преподаватель',
  group_name: 'Группа',
  subgroup: 'Подгруппа',
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

export type DbTableType = 'timetable_cleaned' | 'timetable_teacher';

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
    profile: ''
  });
  const [showStats, setShowStats] = useState(false);
  const [isInitialized, setIsInitialized] = useState(false);

  // Состояние для сортировки
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');

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

  // Видимость колонок (сохраняем в localStorage). Подгруппа и Курс по умолчанию скрыты.
  const VISIBLE_COLUMNS_KEY = 'timetable_db_visible_columns';
  const HIDDEN_BY_DEFAULT_KEYS = ['subgroup', 'course'];
  const [visibleColumns, setVisibleColumns] = useState<Record<string, boolean>>(() => {
    try {
      const saved = localStorage.getItem(VISIBLE_COLUMNS_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as Record<string, boolean>;
        const out: Record<string, boolean> = {};
        COLUMN_KEYS.forEach(k => { out[k] = parsed[k] !== false; });
        return out;
      }
    } catch (_) { }
    return COLUMN_KEYS.reduce<Record<string, boolean>>((acc, k) => ({
      ...acc,
      [k]: HIDDEN_BY_DEFAULT_KEYS.includes(k) ? false : true
    }), {});
  });
  // Колонки, скрытые по типу таблицы: спаршенное расписание — без «Преподаватель», занятость — без «Предмет» и «Тип»
  const columnsHiddenByTable = useMemo((): string[] => {
    if (activeTable === 'timetable_cleaned') return ['fio'];
    if (activeTable === 'timetable_teacher') return ['subject_name', 'lecture_type'];
    return [];
  }, [activeTable]);
  const visibleColumnKeys = useMemo(
    () => COLUMN_KEYS.filter(k => visibleColumns[k] !== false && !columnsHiddenByTable.includes(k)),
    [visibleColumns, columnsHiddenByTable]
  );
  const toggleColumnVisibility = useCallback((key: string) => {
    setVisibleColumns(prev => {
      const next = { ...prev, [key]: !prev[key] };
      try {
        localStorage.setItem(VISIBLE_COLUMNS_KEY, JSON.stringify(next));
      } catch (_) { }
      return next;
    });
  }, []);
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

  // Используем useDebounce для оптимизации запросов (800мс задержка)
  const debouncedFilters = useDebounce<Filters>(filters, 800);

  const API_BASE = import.meta.env.VITE_API_URL || '/api';
  const queryClient = useQueryClient();

  // Восстанавливаем состояние из URL при загрузке
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);

    const tableParam = params.get('table');
    if (tableParam === 'timetable_teacher' || tableParam === 'timetable_cleaned') {
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
      profile: params.get('profile') || ''
    };
    setFilters(restoredFilters);

    // Восстанавливаем страницу
    const page = parseInt(params.get('page') || '1', 10);
    if (page > 0) {
      setCurrentPage(page);
    }

    // Восстанавливаем состояние показа статистики
    setShowStats(params.get('showStats') === 'true');

    // Восстанавливаем сортировку
    const sortBy = params.get('sort_by');
    const sortOrder = params.get('sort_order');
    if (sortBy) {
      setSortColumn(sortBy);
      setSortDirection((sortOrder === 'desc' ? 'desc' : 'asc') as 'asc' | 'desc');
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

  // Слушаем изменения в URL (например, при нажатии назад/вперед)
  useEffect(() => {
    const handlePopState = () => {
      const params = new URLSearchParams(window.location.search);
      const tableParam = params.get('table');
      if (tableParam === 'timetable_teacher' || tableParam === 'timetable_cleaned') {
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
        profile: params.get('profile') || ''
      };
      setFilters(restoredFilters);

      const page = parseInt(params.get('page') || '1', 10);
      if (page > 0) {
        setCurrentPage(page);
      }

      setShowStats(params.get('showStats') === 'true');
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  // Убрали логику закрытия фильтров - они теперь всегда видны

  // Маппинг названий колонок на поля базы данных для сортировки
  const columnToSortField: Record<string, string> = useMemo(() => ({
    'ID': 'id',
    'День': 'day_of_week',
    'Пара': 'pair_number',
    'Предмет': 'subject_name',
    'Тип': 'lecture_type',
    'Аудитория': 'audience',
    'Преподаватель': 'fio',
    'Группа': 'group_name',
    'Подгруппа': 'subgroup',
    'Курс': 'course',
    'Институт': 'institute',
    'Направление': 'direction',
    'Профиль': 'profile',
    'Неделя': 'week_type'
  }), []);

  // Мемоизируем параметры запроса для оптимизации (используем debounced фильтры)
  const recordsQueryParams = useMemo(() => {
    const params: any = { page: currentPage, limit: 20, table: activeTable };
    Object.keys(debouncedFilters).forEach(key => {
      if (debouncedFilters[key as keyof Filters]) {
        params[key] = debouncedFilters[key as keyof Filters];
      }
    });
    if (sortColumn) {
      const sortField = columnToSortField[sortColumn] || sortColumn;
      params.sort_by = sortField;
      params.sort_order = sortDirection;
    }
    return params;
  }, [currentPage, debouncedFilters, sortColumn, sortDirection, activeTable, columnToSortField]);

  // Обработчик клика на заголовок для сортировки
  const handleSort = useCallback((column: string) => {
    const sortField = columnToSortField[column];
    if (!sortField) return;

    if (sortColumn === column) {
      // Если кликнули на ту же колонку - меняем направление
      const newDirection = sortDirection === 'asc' ? 'desc' : 'asc';
      setSortDirection(newDirection);
      updateURL({ sort_by: sortField, sort_order: newDirection });
    } else {
      // Если кликнули на другую колонку - устанавливаем новую сортировку
      setSortColumn(column);
      setSortDirection('asc');
      updateURL({ sort_by: sortField, sort_order: 'asc' });
    }
    setCurrentPage(1); // Сбрасываем на первую страницу при сортировке
  }, [sortColumn, sortDirection, columnToSortField, updateURL]);

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
      profile: ''
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

  // Маппинг названий колонок на поля фильтров
  const columnToFilterMap: Record<string, keyof Filters | null> = {
    'ID': null, // ID не фильтруется
    'День': 'day_of_week',
    'Пара': 'pair_number',
    'Предмет': 'subject_name',
    'Тип': 'lecture_type',
    'Аудитория': 'audience',
    'Преподаватель': 'fio',
    'Группа': 'group_name',
    'Подгруппа': 'subgroup',
    'Курс': 'course',
    'Институт': 'institute',
    'Направление': 'direction',
    'Профиль': 'profile',
    'Неделя': 'week_type'
  };

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
    const tableLabel = activeTable === 'timetable_teacher' ? 'Занятость преподавателей' : 'Спаршенное расписание';
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

  // Обработчик правого клика на строке
  const handleRowContextMenu = (e: React.MouseEvent, record: DatabaseRecord) => {
    e.preventDefault();
    e.stopPropagation();

    // Определяем позицию (до или после)
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
    const handleClose = () => setContextMenu(null);

    if (contextMenu) {
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
  }, [contextMenu]);

  // Изменение ширины колонки перетаскиванием
  const handleResizeStart = useCallback((e: React.MouseEvent, colIndex: number) => {
    e.preventDefault();
    setResizingCol(colIndex);
    resizeStartX.current = e.clientX;
    resizeStartWidth.current = columnWidths[colIndex];
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
                  <div className="columns-dropdown-title">Видимость колонок</div>
                  {COLUMN_KEYS.map(key => (
                    <label key={key} className="columns-dropdown-item">
                      <input
                        type="checkbox"
                        checked={visibleColumns[key] !== false}
                        onChange={() => toggleColumnVisibility(key)}
                      />
                      <span>{COLUMN_LABELS[key]}</span>
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
                <div className="grid-table-header">
                  {visibleColumnKeys.map((key) => {
                    const colIndex = COLUMN_KEYS.indexOf(key);
                    const label = COLUMN_LABELS[key];
                    const w = columnWidths[colIndex];
                    const filterable = key !== 'id';
                    return (
                      <div
                        key={key}
                        className="grid-table-cell header-cell-resizable"
                        style={{ width: w, minWidth: w, maxWidth: w }}
                      >
                        <div
                          className={key === 'id' ? 'header-label' : 'header-label header-sortable'}
                          onClick={filterable ? () => handleSort(label) : undefined}
                          title={filterable ? 'Нажмите для сортировки' : undefined}
                        >
                          {label}
                          {filterable && (
                            <span className="sort-arrows">
                              <span className={`sort-arrow ${sortColumn === label && sortDirection === 'asc' ? 'active' : ''}`}>▲</span>
                              <span className={`sort-arrow ${sortColumn === label && sortDirection === 'desc' ? 'active' : ''}`}>▼</span>
                            </span>
                          )}
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
                            placeholder={COLUMN_PLACEHOLDERS[key] || ''}
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
                      <div key={index} className="grid-table-row skeleton-row">
                        {visibleColumnKeys.map((k) => {
                          const colIndex = COLUMN_KEYS.indexOf(k);
                          const w = columnWidths[colIndex];
                          return <div key={k} className="grid-table-cell" style={{ width: w, minWidth: w, maxWidth: w }}><div className="skeleton-cell"></div></div>;
                        })}
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
                        const width = columnWidths[cellIndex];
                        if (isEditing && field === 'id') {
                          return (
                            <div key={cellIndex} className="grid-table-cell id-cell-with-actions" style={{ width, minWidth: width, maxWidth: width }}>
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
                              <div key={cellIndex} className="grid-table-cell editable-cell" style={{ width, minWidth: width, maxWidth: width }}>
                                <select className="cell-select" value={getValue(currentRecord[field])} onChange={(e) => handleFieldChange(field, e.target.value || null)} onClick={(e) => e.stopPropagation()} onFocus={(e) => e.stopPropagation()}>
                                  <option value="">-</option>
                                  {['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье'].map(d => <option key={d} value={d}>{d}</option>)}
                                </select>
                              </div>
                            );
                          }
                          if (field === 'pair_number') {
                            return (
                              <div key={cellIndex} className="grid-table-cell editable-cell" style={{ width, minWidth: width, maxWidth: width }}>
                                <select className="cell-select" value={getValue(currentRecord[field])} onChange={(e) => handleFieldChange(field, e.target.value === '' ? null : Number(e.target.value))} onClick={(e) => e.stopPropagation()} onFocus={(e) => e.stopPropagation()}>
                                  <option value="">-</option>
                                  {[1, 2, 3, 4, 5, 6, 7, 8].map(num => <option key={num} value={num}>{num}</option>)}
                                </select>
                              </div>
                            );
                          }
                          if (field === 'lecture_type') {
                            return (
                              <div key={cellIndex} className="grid-table-cell editable-cell" style={{ width, minWidth: width, maxWidth: width }}>
                                <select className="cell-select" value={getValue(currentRecord[field])} onChange={(e) => handleFieldChange(field, e.target.value || null)} onClick={(e) => e.stopPropagation()} onFocus={(e) => e.stopPropagation()}>
                                  <option value="">-</option>
                                  {['лекция', 'практика', 'лабораторная', 'семинар'].map(t => <option key={t} value={t}>{t}</option>)}
                                </select>
                              </div>
                            );
                          }
                          if (field === 'week_type') {
                            return (
                              <div key={cellIndex} className="grid-table-cell editable-cell" style={{ width, minWidth: width, maxWidth: width }}>
                                <select className="cell-select" value={getValue(currentRecord[field])} onChange={(e) => handleFieldChange(field, e.target.value || null)} onClick={(e) => e.stopPropagation()} onFocus={(e) => e.stopPropagation()}>
                                  <option value="">-</option>
                                  {['числитель', 'знаменатель', 'обе недели'].map(t => <option key={t} value={t}>{t}</option>)}
                                </select>
                              </div>
                            );
                          }
                          return (
                            <div key={cellIndex} className="grid-table-cell editable-cell" style={{ width, minWidth: width, maxWidth: width }}>
                              <input type="text" className="cell-input" value={getValue(currentRecord[field])} onChange={(e) => handleFieldChange(String(field), e.target.value)} onClick={(e) => e.stopPropagation()} onFocus={(e) => e.stopPropagation()} />
                            </div>
                          );
                        }
                        return (
                          <div
                            key={cellIndex}
                            className={`grid-table-cell expandable-cell ${copiedCellId === uniqueCellId ? 'cell-copied' : ''}`}
                            style={{ width, minWidth: width, maxWidth: width }}
                            onMouseEnter={(e) => handleCellMouseEnter(e, uniqueCellId)}
                            onMouseLeave={handleCellMouseLeave}
                            onDoubleClick={() => !isEditing && startEditing(record)}
                            onClick={(e) => { if (displayValue && displayValue !== '-') copyToClipboard(displayValue, uniqueCellId); e.stopPropagation(); }}
                            title="Клик — копировать, двойной клик — редактировать"
                          >
                            <div className="cell-content" data-expanded={isExpanded} data-direction={expandDirection} style={isExpanded ? { width: `${expandWidth}px`, minWidth: `${expandWidth}px`, ...(expandDirection === 'left' ? { right: 0, left: 'auto' } : { left: 0, right: 'auto' }) } : {}}>
                              {displayValue || '-'}
                            </div>
                          </div>
                        );
                      };
                      return (
                        <div key={record.id} className={`grid-table-row ${isEditing ? 'editing-row' : ''}`} onContextMenu={(e) => !isEditing && handleRowContextMenu(e, record)}>
                          {visibleColumnKeys.map((key) => {
                            const colIndex = COLUMN_KEYS.indexOf(key);
                            const displayValue = key === 'fio' ? getValue(currentRecord.fio || currentRecord.teacher) : getValue((currentRecord as any)[key]);
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
    </div>
  );
};

export default DatabaseView;
