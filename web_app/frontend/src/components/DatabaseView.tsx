import React, { useState, useEffect, useMemo, useRef, useCallback, useLayoutEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { useDebounce } from '../hooks/useDebounce';
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
  week_type: string;
  institute: string;
  course: string;
}

const DatabaseView: React.FC = () => {
  const [currentPage, setCurrentPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<Filters>({
    day_of_week: '',
    pair_number: '',
    subject_name: '',
    lecture_type: '',
    audience: '',
    fio: '',
    teacher: '',
    group_name: '',
    week_type: '',
    institute: '',
    course: ''
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

  // Используем useDebounce для оптимизации запросов (800мс задержка)
  const debouncedFilters = useDebounce<Filters>(filters, 800);

  const API_BASE = import.meta.env.VITE_API_URL || '/api';
  const queryClient = useQueryClient();

  // Восстанавливаем состояние из URL при загрузке
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);

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
      week_type: params.get('week_type') || '',
      institute: params.get('institute') || '',
      course: params.get('course') || ''
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

  // Обновляем URL при изменении состояния показа статистики (только после инициализации)
  useEffect(() => {
    if (!isInitialized) return;
    updateURL({ showStats });
  }, [showStats, isInitialized]);

  // Слушаем изменения в URL (например, при нажатии назад/вперед)
  useEffect(() => {
    const handlePopState = () => {
      const params = new URLSearchParams(window.location.search);

      const restoredFilters: Filters = {
        day_of_week: params.get('day_of_week') || '',
        pair_number: params.get('pair_number') || '',
        subject_name: params.get('subject_name') || '',
        lecture_type: params.get('lecture_type') || '',
        audience: params.get('audience') || '',
        fio: params.get('fio') || '',
        teacher: params.get('teacher') || '',
        group_name: params.get('group_name') || '',
        week_type: params.get('week_type') || '',
        institute: params.get('institute') || '',
        course: params.get('course') || ''
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

  // Мемоизируем параметры запроса для оптимизации (используем debounced фильтры)
  const recordsQueryParams = useMemo(() => {
    const params: any = { page: currentPage, limit: 20 }; // Уменьшили до 20 для ускорения
    Object.keys(debouncedFilters).forEach(key => {
      if (debouncedFilters[key as keyof Filters]) {
        params[key] = debouncedFilters[key as keyof Filters];
      }
    });
    // Добавляем параметры сортировки
    if (sortColumn) {
      params.sort_by = sortColumn;
      params.sort_order = sortDirection;
    }
    return params;
  }, [currentPage, debouncedFilters, sortColumn, sortDirection]);
  
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
    'Неделя': 'week_type'
  }), []);
  
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

  // Запрос статистики с React Query
  const { data: stats, isLoading: statsLoading } = useQuery<DatabaseStats>({
    queryKey: ['db-stats'],
    queryFn: async () => {
      const response = await axios.get(`${API_BASE}/db/stats`);
      return response.data;
    },
    refetchInterval: 60000, // Обновляем каждую минуту
  });

  // Запрос записей с React Query и debounce для фильтров
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
      week_type: '',
      institute: '',
      course: ''
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
    if (!window.confirm('Вы уверены, что хотите очистить базу данных? Это действие нельзя отменить.')) {
      return;
    }

    try {
      await axios.post(`${API_BASE}/db/clear`);
      setCurrentPage(1);
      // Инвалидируем кеш React Query для обновления данных
      queryClient.invalidateQueries({ queryKey: ['db-stats'] });
      queryClient.invalidateQueries({ queryKey: ['db-records'] });
      alert('База данных успешно очищена');
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
      
      await axios.put(`${API_BASE}/db/records/${recordId}`, dataToSend);
      
      // Инвалидируем кеш для обновления данных
      queryClient.invalidateQueries({ queryKey: ['db-records'] });
      queryClient.invalidateQueries({ queryKey: ['db-stats'] });
      
      setEditingRecordId(null);
      setEditedValues({});
      setOriginalValues({});
    } catch (err: any) {
      setError(err.response?.data?.error || 'Ошибка при сохранении записи');
    }
  };

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
            {hasActiveFilters() && (
              <button
                className="button"
                onClick={clearFilters}
                style={{ marginLeft: '0.5rem' }}
              >
                Очистить фильтры
              </button>
            )}
          </div>
        </div>


        {/* Таблица всегда отображается, даже если нет данных */}
        {(
          <>
            <div className="table-container">
              <div className="grid-table">
                <div className="grid-table-header">
                  <div className="grid-table-cell">
                    <div 
                      className="header-label header-sortable"
                      onClick={() => handleSort('ID')}
                      title="Нажмите для сортировки"
                    >
                      ID
                      <span className="sort-arrows">
                        <span className={`sort-arrow ${sortColumn === 'ID' && sortDirection === 'asc' ? 'active' : ''}`}>▲</span>
                        <span className={`sort-arrow ${sortColumn === 'ID' && sortDirection === 'desc' ? 'active' : ''}`}>▼</span>
                      </span>
                    </div>
                    <input
                      type="text"
                      className="header-filter-input"
                      value=""
                      placeholder="ID (не фильтруется)"
                      title="ID не фильтруется"
                      disabled
                    />
                  </div>
                  <div className="grid-table-cell">
                    <div 
                      className="header-label header-sortable"
                      onClick={() => handleSort('День')}
                      title="Нажмите для сортировки"
                    >
                      День
                      <span className="sort-arrows">
                        <span className={`sort-arrow ${sortColumn === 'День' && sortDirection === 'asc' ? 'active' : ''}`}>▲</span>
                        <span className={`sort-arrow ${sortColumn === 'День' && sortDirection === 'desc' ? 'active' : ''}`}>▼</span>
                      </span>
                    </div>
                    <input
                      key="filter-day_of_week"
                      ref={(el) => { filterRefs.current['day_of_week'] = el; }}
                      type="text"
                      className="header-filter-input"
                      value={getFilterValue('День')}
                      onChange={(e) => {
                        e.stopPropagation();
                        handleColumnFilterChange('День', e.target.value);
                      }}
                      onKeyDown={(e) => {
                        e.stopPropagation();
                      }}
                      onKeyUp={(e) => {
                        e.stopPropagation();
                      }}
                      onFocus={(e) => {
                        e.stopPropagation();
                        // Сохраняем, что это поле в фокусе
                        focusedFieldRef.current = 'day_of_week';
                        const input = e.target as HTMLInputElement;
                        cursorPositionRef.current['day_of_week'] = input.selectionStart || 0;
                      }}
                      onBlur={(e) => {
                        // НЕ останавливаем blur, но предотвращаем потерю фокуса из-за других событий
                        e.stopPropagation();
                        // Очищаем фокус только если это действительно blur (не перерендер)
                        setTimeout(() => {
                          if (document.activeElement !== e.target) {
                            focusedFieldRef.current = null;
                          }
                        }, 100);
                      }}
                      onMouseDown={(e) => {
                        e.stopPropagation();
                      }}
                      onClick={(e) => {
                        e.stopPropagation();
                      }}
                      placeholder="Фильтр по дню недели (понедельник, вторник...)"
                      title="Введите день недели для поиска"
                      autoComplete="off"
                    />
                  </div>
                  <div className="grid-table-cell">
                    <div 
                      className="header-label header-sortable"
                      onClick={() => handleSort('Пара')}
                      title="Нажмите для сортировки"
                    >
                      Пара
                      <span className="sort-arrows">
                        <span className={`sort-arrow ${sortColumn === 'Пара' && sortDirection === 'asc' ? 'active' : ''}`}>▲</span>
                        <span className={`sort-arrow ${sortColumn === 'Пара' && sortDirection === 'desc' ? 'active' : ''}`}>▼</span>
                      </span>
                    </div>
                    <input
                      key="filter-pair_number"
                      ref={(el) => { filterRefs.current['pair_number'] = el; }}
                      type="text"
                      className="header-filter-input"
                      value={getFilterValue('Пара')}
                      onChange={(e) => {
                        e.stopPropagation();
                        handleColumnFilterChange('Пара', e.target.value);
                      }}
                      onKeyDown={(e) => e.stopPropagation()}
                      onKeyUp={(e) => e.stopPropagation()}
                      onFocus={(e) => {
                        e.stopPropagation();
                        focusedFieldRef.current = 'pair_number';
                        const input = e.target as HTMLInputElement;
                        cursorPositionRef.current['pair_number'] = input.selectionStart || 0;
                      }}
                      onBlur={(e) => {
                        e.stopPropagation();
                        setTimeout(() => {
                          if (document.activeElement !== e.target) {
                            focusedFieldRef.current = null;
                          }
                        }, 100);
                      }}
                      onMouseDown={(e) => e.stopPropagation()}
                      onClick={(e) => e.stopPropagation()}
                      placeholder="Фильтр по номеру пары (1, 2, 3...)"
                      title="Введите номер пары для поиска"
                      autoComplete="off"
                    />
                  </div>
                  <div className="grid-table-cell">
                    <div className="header-label">Предмет</div>
                    <input
                      key="filter-subject_name"
                      ref={(el) => { filterRefs.current['subject_name'] = el; }}
                      type="text"
                      className="header-filter-input"
                      value={getFilterValue('Предмет')}
                      onChange={(e) => {
                        e.stopPropagation();
                        handleColumnFilterChange('Предмет', e.target.value);
                      }}
                      onKeyDown={(e) => e.stopPropagation()}
                      onKeyUp={(e) => e.stopPropagation()}
                      onFocus={(e) => {
                        e.stopPropagation();
                        focusedFieldRef.current = 'subject_name';
                        const input = e.target as HTMLInputElement;
                        cursorPositionRef.current['subject_name'] = input.selectionStart || 0;
                      }}
                      onBlur={(e) => {
                        e.stopPropagation();
                        setTimeout(() => {
                          if (document.activeElement !== e.target) {
                            focusedFieldRef.current = null;
                          }
                        }, 100);
                      }}
                      onMouseDown={(e) => e.stopPropagation()}
                      onClick={(e) => e.stopPropagation()}
                      placeholder="Фильтр по предмету (Математика, Физика...)"
                      title="Введите название предмета для поиска"
                      autoComplete="off"
                    />
                  </div>
                  <div className="grid-table-cell">
                    <div 
                      className="header-label header-sortable"
                      onClick={() => handleSort('Тип')}
                      title="Нажмите для сортировки"
                    >
                      Тип
                      <span className="sort-arrows">
                        <span className={`sort-arrow ${sortColumn === 'Тип' && sortDirection === 'asc' ? 'active' : ''}`}>▲</span>
                        <span className={`sort-arrow ${sortColumn === 'Тип' && sortDirection === 'desc' ? 'active' : ''}`}>▼</span>
                      </span>
                    </div>
                    <input
                      key="filter-lecture_type"
                      ref={(el) => { filterRefs.current['lecture_type'] = el; }}
                      type="text"
                      className="header-filter-input"
                      value={getFilterValue('Тип')}
                      onChange={(e) => {
                        e.stopPropagation();
                        handleColumnFilterChange('Тип', e.target.value);
                      }}
                      onKeyDown={(e) => e.stopPropagation()}
                      onKeyUp={(e) => e.stopPropagation()}
                      onFocus={(e) => {
                        e.stopPropagation();
                        focusedFieldRef.current = 'lecture_type';
                        const input = e.target as HTMLInputElement;
                        cursorPositionRef.current['lecture_type'] = input.selectionStart || 0;
                      }}
                      onBlur={(e) => {
                        e.stopPropagation();
                        setTimeout(() => {
                          if (document.activeElement !== e.target) {
                            focusedFieldRef.current = null;
                          }
                        }, 100);
                      }}
                      onMouseDown={(e) => e.stopPropagation()}
                      onClick={(e) => e.stopPropagation()}
                      placeholder="Фильтр по типу занятия (лекция, практика...)"
                      title="Введите тип занятия для поиска"
                      autoComplete="off"
                    />
                  </div>
                  <div className="grid-table-cell">
                    <div 
                      className="header-label header-sortable"
                      onClick={() => handleSort('Аудитория')}
                      title="Нажмите для сортировки"
                    >
                      Аудитория
                      <span className="sort-arrows">
                        <span className={`sort-arrow ${sortColumn === 'Аудитория' && sortDirection === 'asc' ? 'active' : ''}`}>▲</span>
                        <span className={`sort-arrow ${sortColumn === 'Аудитория' && sortDirection === 'desc' ? 'active' : ''}`}>▼</span>
                      </span>
                    </div>
                    <input
                      key="filter-audience"
                      ref={(el) => { filterRefs.current['audience'] = el; }}
                      type="text"
                      className="header-filter-input"
                      value={getFilterValue('Аудитория')}
                      onChange={(e) => {
                        e.stopPropagation();
                        handleColumnFilterChange('Аудитория', e.target.value);
                      }}
                      onKeyDown={(e) => e.stopPropagation()}
                      onKeyUp={(e) => e.stopPropagation()}
                      onFocus={(e) => {
                        e.stopPropagation();
                        focusedFieldRef.current = 'audience';
                        const input = e.target as HTMLInputElement;
                        cursorPositionRef.current['audience'] = input.selectionStart || 0;
                      }}
                      onBlur={(e) => {
                        e.stopPropagation();
                        setTimeout(() => {
                          if (document.activeElement !== e.target) {
                            focusedFieldRef.current = null;
                          }
                        }, 100);
                      }}
                      onMouseDown={(e) => e.stopPropagation()}
                      onClick={(e) => e.stopPropagation()}
                      placeholder="Фильтр по аудитории (У804, А539...)"
                      title="Введите номер аудитории для поиска"
                      autoComplete="off"
                    />
                  </div>
                  <div className="grid-table-cell">
                    <div 
                      className="header-label header-sortable"
                      onClick={() => handleSort('Преподаватель')}
                      title="Нажмите для сортировки"
                    >
                      Преподаватель
                      <span className="sort-arrows">
                        <span className={`sort-arrow ${sortColumn === 'Преподаватель' && sortDirection === 'asc' ? 'active' : ''}`}>▲</span>
                        <span className={`sort-arrow ${sortColumn === 'Преподаватель' && sortDirection === 'desc' ? 'active' : ''}`}>▼</span>
                      </span>
                    </div>
                    <input
                      key="filter-fio"
                      ref={(el) => { filterRefs.current['fio'] = el; }}
                      type="text"
                      className="header-filter-input"
                      value={getFilterValue('Преподаватель')}
                      onChange={(e) => {
                        e.stopPropagation();
                        handleColumnFilterChange('Преподаватель', e.target.value);
                      }}
                      onKeyDown={(e) => e.stopPropagation()}
                      onKeyUp={(e) => e.stopPropagation()}
                      onFocus={(e) => {
                        e.stopPropagation();
                        focusedFieldRef.current = 'fio';
                        const input = e.target as HTMLInputElement;
                        cursorPositionRef.current['fio'] = input.selectionStart || 0;
                      }}
                      onBlur={(e) => {
                        e.stopPropagation();
                        setTimeout(() => {
                          if (document.activeElement !== e.target) {
                            focusedFieldRef.current = null;
                          }
                        }, 100);
                      }}
                      onMouseDown={(e) => e.stopPropagation()}
                      onClick={(e) => e.stopPropagation()}
                      placeholder="Фильтр по преподавателю (Иванов И.И...)"
                      title="Введите ФИО преподавателя для поиска"
                      autoComplete="off"
                    />
                  </div>
                  <div className="grid-table-cell">
                    <div 
                      className="header-label header-sortable"
                      onClick={() => handleSort('Группа')}
                      title="Нажмите для сортировки"
                    >
                      Группа
                      <span className="sort-arrows">
                        <span className={`sort-arrow ${sortColumn === 'Группа' && sortDirection === 'asc' ? 'active' : ''}`}>▲</span>
                        <span className={`sort-arrow ${sortColumn === 'Группа' && sortDirection === 'desc' ? 'active' : ''}`}>▼</span>
                      </span>
                    </div>
                    <input
                      key="filter-group_name"
                      ref={(el) => { filterRefs.current['group_name'] = el; }}
                      type="text"
                      className="header-filter-input"
                      value={getFilterValue('Группа')}
                      onChange={(e) => {
                        e.stopPropagation();
                        handleColumnFilterChange('Группа', e.target.value);
                      }}
                      onKeyDown={(e) => e.stopPropagation()}
                      onKeyUp={(e) => e.stopPropagation()}
                      onFocus={(e) => {
                        e.stopPropagation();
                        focusedFieldRef.current = 'group_name';
                        const input = e.target as HTMLInputElement;
                        cursorPositionRef.current['group_name'] = input.selectionStart || 0;
                      }}
                      onBlur={(e) => {
                        e.stopPropagation();
                        setTimeout(() => {
                          if (document.activeElement !== e.target) {
                            focusedFieldRef.current = null;
                          }
                        }, 100);
                      }}
                      onMouseDown={(e) => e.stopPropagation()}
                      onClick={(e) => e.stopPropagation()}
                      placeholder="Фильтр по группе (606-22, 606-21...)"
                      title="Введите номер группы для поиска"
                      autoComplete="off"
                    />
                  </div>
                  <div className="grid-table-cell">
                    <div 
                      className="header-label header-sortable"
                      onClick={() => handleSort('Неделя')}
                      title="Нажмите для сортировки"
                    >
                      Неделя
                      <span className="sort-arrows">
                        <span className={`sort-arrow ${sortColumn === 'Неделя' && sortDirection === 'asc' ? 'active' : ''}`}>▲</span>
                        <span className={`sort-arrow ${sortColumn === 'Неделя' && sortDirection === 'desc' ? 'active' : ''}`}>▼</span>
                      </span>
                    </div>
                    <input
                      key="filter-week_type"
                      ref={(el) => { filterRefs.current['week_type'] = el; }}
                      type="text"
                      className="header-filter-input"
                      value={getFilterValue('Неделя')}
                      onChange={(e) => {
                        e.stopPropagation();
                        handleColumnFilterChange('Неделя', e.target.value);
                      }}
                      onKeyDown={(e) => e.stopPropagation()}
                      onKeyUp={(e) => e.stopPropagation()}
                      onFocus={(e) => {
                        e.stopPropagation();
                        focusedFieldRef.current = 'week_type';
                        const input = e.target as HTMLInputElement;
                        cursorPositionRef.current['week_type'] = input.selectionStart || 0;
                      }}
                      onBlur={(e) => {
                        e.stopPropagation();
                        setTimeout(() => {
                          if (document.activeElement !== e.target) {
                            focusedFieldRef.current = null;
                          }
                        }, 100);
                      }}
                      onMouseDown={(e) => e.stopPropagation()}
                      onClick={(e) => e.stopPropagation()}
                      placeholder="Фильтр по типу недели (числитель, знаменатель...)"
                      title="Введите тип недели для поиска"
                      autoComplete="off"
                    />
                  </div>
                </div>
                <div className="grid-table-body">
                  {loading ? (
                    // Skeleton loader только для тела таблицы
                    [...Array(10)].map((_, index) => (
                      <div key={index} className="grid-table-row skeleton-row">
                        <div className="grid-table-cell"><div className="skeleton-cell"></div></div>
                        <div className="grid-table-cell"><div className="skeleton-cell"></div></div>
                        <div className="grid-table-cell"><div className="skeleton-cell"></div></div>
                        <div className="grid-table-cell"><div className="skeleton-cell"></div></div>
                        <div className="grid-table-cell"><div className="skeleton-cell"></div></div>
                        <div className="grid-table-cell"><div className="skeleton-cell"></div></div>
                        <div className="grid-table-cell"><div className="skeleton-cell"></div></div>
                        <div className="grid-table-cell"><div className="skeleton-cell"></div></div>
                        <div className="grid-table-cell"><div className="skeleton-cell"></div></div>
                      </div>
                    ))
                  ) : (
                    records.map((record: DatabaseRecord) => {
                      const isEditing = editingRecordId === record.id;
                      const currentRecord = isEditing ? { ...record, ...editedValues } : record;
                      
                      // Безопасное получение значений с обработкой null/undefined
                      const getValue = (value: any): string => {
                        if (value === null || value === undefined || value === '') {
                          return '';
                        }
                        return String(value);
                      };

                      const cellId = `cell-${record.id}`;
                      
                      // Функция для рендеринга редактируемой ячейки
                      const renderEditableCell = (
                        field: keyof DatabaseRecord,
                        cellIndex: number,
                        displayValue: string
                      ) => {
                        const uniqueCellId = `${cellId}-${cellIndex}`;
                        const isExpanded = expandedCell?.id === uniqueCellId;
                        const expandDirection = expandedCell?.direction || 'right';
                        const expandWidth = expandedCell?.width || 0;
                        
                        if (isEditing && field !== 'id') {
                          // Редактируемая ячейка
                          const isNumericField = field === 'pair_number' || field === 'subgroup' || field === 'num_subgroups';
                          
                          // Выпадающие списки для определенных полей
                          if (field === 'day_of_week') {
                            return (
                              <div 
                                key={cellIndex}
                                className="grid-table-cell editable-cell"
                              >
                                <select
                                  className="cell-select"
                                  value={getValue(currentRecord[field])}
                                  onChange={(e) => handleFieldChange(field, e.target.value || null)}
                                  onClick={(e) => e.stopPropagation()}
                                  onFocus={(e) => e.stopPropagation()}
                                >
                                  <option value="">-</option>
                                  <option value="понедельник">понедельник</option>
                                  <option value="вторник">вторник</option>
                                  <option value="среда">среда</option>
                                  <option value="четверг">четверг</option>
                                  <option value="пятница">пятница</option>
                                  <option value="суббота">суббота</option>
                                  <option value="воскресенье">воскресенье</option>
                                </select>
                              </div>
                            );
                          }
                          
                          if (field === 'pair_number') {
                            return (
                              <div 
                                key={cellIndex}
                                className="grid-table-cell editable-cell"
                              >
                                <select
                                  className="cell-select"
                                  value={getValue(currentRecord[field])}
                                  onChange={(e) => handleFieldChange(field, e.target.value === '' ? null : Number(e.target.value))}
                                  onClick={(e) => e.stopPropagation()}
                                  onFocus={(e) => e.stopPropagation()}
                                >
                                  <option value="">-</option>
                                  {[1, 2, 3, 4, 5, 6, 7, 8].map(num => (
                                    <option key={num} value={num}>{num}</option>
                                  ))}
                                </select>
                              </div>
                            );
                          }
                          
                          if (field === 'lecture_type') {
                            return (
                              <div 
                                key={cellIndex}
                                className="grid-table-cell editable-cell"
                              >
                                <select
                                  className="cell-select"
                                  value={getValue(currentRecord[field])}
                                  onChange={(e) => handleFieldChange(field, e.target.value || null)}
                                  onClick={(e) => e.stopPropagation()}
                                  onFocus={(e) => e.stopPropagation()}
                                >
                                  <option value="">-</option>
                                  <option value="лекция">лекция</option>
                                  <option value="практика">практика</option>
                                  <option value="лабораторная">лабораторная</option>
                                  <option value="семинар">семинар</option>
                                </select>
                              </div>
                            );
                          }
                          
                          if (field === 'week_type') {
                            return (
                              <div 
                                key={cellIndex}
                                className="grid-table-cell editable-cell"
                              >
                                <select
                                  className="cell-select"
                                  value={getValue(currentRecord[field])}
                                  onChange={(e) => handleFieldChange(field, e.target.value || null)}
                                  onClick={(e) => e.stopPropagation()}
                                  onFocus={(e) => e.stopPropagation()}
                                >
                                  <option value="">-</option>
                                  <option value="числитель">числитель</option>
                                  <option value="знаменатель">знаменатель</option>
                                  <option value="обе недели">обе недели</option>
                                </select>
                              </div>
                            );
                          }
                          
                          // Обычное текстовое поле для остальных полей
                          return (
                            <div 
                              key={cellIndex}
                              className="grid-table-cell editable-cell"
                            >
                              <input
                                type="text"
                                className="cell-input"
                                value={getValue(currentRecord[field])}
                                onChange={(e) => handleFieldChange(field, e.target.value)}
                                onClick={(e) => e.stopPropagation()}
                                onFocus={(e) => e.stopPropagation()}
                              />
                            </div>
                          );
                        } else {
                          // Обычная ячейка
                          return (
                            <div 
                              key={cellIndex}
                              className={`grid-table-cell expandable-cell ${copiedCellId === uniqueCellId ? 'cell-copied' : ''}`}
                              onMouseEnter={(e) => handleCellMouseEnter(e, uniqueCellId)}
                              onMouseLeave={handleCellMouseLeave}
                              onDoubleClick={() => !isEditing && startEditing(record)}
                              onClick={(e) => {
                                // Копируем значение при клике
                                const textToCopy = displayValue || '-';
                                if (textToCopy !== '-') {
                                  copyToClipboard(textToCopy, uniqueCellId);
                                }
                                e.stopPropagation();
                              }}
                              title="Кликните для копирования, двойной клик для редактирования"
                            >
                              <div 
                                className="cell-content"
                                data-expanded={isExpanded}
                                data-direction={expandDirection}
                                style={isExpanded ? {
                                  width: `${expandWidth}px`,
                                  minWidth: `${expandWidth}px`,
                                  ...(expandDirection === 'left' ? { right: 0, left: 'auto' } : { left: 0, right: 'auto' })
                                } : {}}
                              >
                                {displayValue || '-'}
                              </div>
                            </div>
                          );
                        }
                      };
                      
                      return (
                        <div key={record.id} className={`grid-table-row ${isEditing ? 'editing-row' : ''}`}>
                          {renderEditableCell('id', 0, String(record.id || '-'))}
                          {renderEditableCell('day_of_week', 1, getValue(currentRecord.day_of_week))}
                          {renderEditableCell('pair_number', 2, getValue(currentRecord.pair_number))}
                          {renderEditableCell('subject_name', 3, getValue(currentRecord.subject_name))}
                          {renderEditableCell('lecture_type', 4, getValue(currentRecord.lecture_type))}
                          {renderEditableCell('audience', 5, getValue(currentRecord.audience))}
                          {renderEditableCell('fio', 6, getValue(currentRecord.fio || currentRecord.teacher))}
                          {renderEditableCell('group_name', 7, getValue(currentRecord.group_name))}
                          {renderEditableCell('week_type', 8, getValue(currentRecord.week_type))}
                          {isEditing && (
                            <div className="grid-table-cell action-cell">
                              <button
                                className="save-button"
                                onClick={() => saveRecord(record.id)}
                                title="Сохранить изменения"
                              >
                                ✓
                              </button>
                              <button
                                className="cancel-button"
                                onClick={cancelEditing}
                                title="Отменить изменения"
                              >
                                ✕
                              </button>
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            </div>

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
          </>
        )}
      </div>

    </div>
  );
};

export default DatabaseView;
