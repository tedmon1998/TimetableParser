import React, { useState, useCallback, useRef, useEffect } from 'react';
import './TeachersTable.css';

export const TEACHER_TABLE_KEYS = ['fio', 'post_name', 'post_struct', 'all_staj', 'staj_spec', 'phone', 'predmet'] as const;
const COLUMN_LABELS: Record<string, string> = {
  fio: 'ФИО',
  post_name: 'Должность',
  post_struct: 'Структура',
  all_staj: 'Общий стаж',
  staj_spec: 'Стаж по спец.',
  phone: 'Телефон',
  predmet: 'Предметы'
};

export interface TeacherRecord {
  fio: string;
  post_name: string;
  post_struct: string;
  all_staj: string;
  staj_spec: string;
  phone: string;
  predmet: string;
  _index?: number;
}

const DEFAULT_WIDTHS = [200, 160, 180, 140, 140, 140, 280];
const STORAGE_KEY = 'teachers_table_column_widths';

export interface TeachersTableProps {
  teachers: TeacherRecord[];
  loading: boolean;
  page: number;
  totalPages: number;
  total: number;
  fioFilter: string;
  onFioFilterChange: (v: string) => void;
  onPageChange: (page: number) => void;
  onSave: (index: number, values: Partial<TeacherRecord>) => Promise<void>;
  onDuplicate: (teacher: TeacherRecord) => Promise<void>;
  onCreateEmpty: () => Promise<void>;
  onDelete: (teacher: TeacherRecord) => Promise<void>;
  onToast?: (message: string, type: 'success' | 'error' | 'info') => void;
}

const TeachersTable: React.FC<TeachersTableProps> = ({
  teachers,
  loading,
  page,
  totalPages,
  total,
  fioFilter,
  onFioFilterChange,
  onPageChange,
  onSave,
  onDuplicate,
  onCreateEmpty,
  onDelete,
  onToast
}) => {
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editedValues, setEditedValues] = useState<Partial<TeacherRecord>>({});
  const [expandedCell, setExpandedCell] = useState<{ id: string; width: number; direction: 'left' | 'right' } | null>(null);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; teacher: TeacherRecord } | null>(null);
  const [copiedCellId, setCopiedCellId] = useState<string | null>(null);
  const [columnWidths, setColumnWidths] = useState<number[]>(() => {
    try {
      const s = localStorage.getItem(STORAGE_KEY);
      if (s) {
        const arr = JSON.parse(s) as number[];
        if (Array.isArray(arr) && arr.length === TEACHER_TABLE_KEYS.length) return arr;
      }
    } catch (_) {}
    return [...DEFAULT_WIDTHS];
  });
  const [resizingCol, setResizingCol] = useState<number | null>(null);
  const resizeStartX = useRef(0);
  const resizeStartWidth = useRef(0);
  const tableContainerRef = useRef<HTMLDivElement>(null);

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
  }, [resizingCol]);

  useEffect(() => {
    if (resizingCol === null) {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(columnWidths));
      } catch (_) {}
    }
  }, [columnWidths, resizingCol]);

  useEffect(() => {
    if (!contextMenu) return;
    const close = () => setContextMenu(null);
    document.addEventListener('click', close);
    document.addEventListener('contextmenu', close);
    window.addEventListener('scroll', close, true);
    const el = tableContainerRef.current;
    if (el) el.addEventListener('scroll', close);
    return () => {
      document.removeEventListener('click', close);
      document.removeEventListener('contextmenu', close);
      window.removeEventListener('scroll', close, true);
      if (el) el.removeEventListener('scroll', close);
    };
  }, [contextMenu]);

  const calculateCellWidth = useCallback((cellElement: HTMLElement, contentElement: HTMLElement) => {
    const temp = document.createElement('div');
    const style = window.getComputedStyle(contentElement);
    temp.style.cssText = `
      position: absolute; visibility: hidden; white-space: nowrap;
      font: ${style.font}; letter-spacing: ${style.letterSpacing};
      padding: 0.5rem; box-sizing: border-box;
    `;
    temp.textContent = contentElement.textContent || '';
    document.body.appendChild(temp);
    const contentWidth = temp.scrollWidth + 16;
    document.body.removeChild(temp);
    const maxW = Math.min(window.innerWidth * 0.8, 800);
    const width = Math.min(contentWidth, maxW);
    const cellRect = cellElement.getBoundingClientRect();
    const direction = window.innerWidth - cellRect.right >= width ? 'right' : 'left';
    return { width, direction };
  }, []);

  const handleCellMouseEnter = useCallback((e: React.MouseEvent<HTMLDivElement>, cellId: string) => {
    const cell = e.currentTarget;
    const content = cell.querySelector('.teachers-table-cell-content') as HTMLElement;
    if (!content || content.scrollWidth <= content.clientWidth) return;
    const { width, direction } = calculateCellWidth(cell, content);
    setExpandedCell({ id: cellId, width, direction });
  }, [calculateCellWidth]);

  const handleCellMouseLeave = useCallback(() => setExpandedCell(null), []);

  const copyToClipboard = useCallback(async (text: string, cellId: string) => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopiedCellId(cellId);
      setTimeout(() => setCopiedCellId(null), 1000);
    } catch (_) {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      setCopiedCellId(cellId);
      setTimeout(() => setCopiedCellId(null), 1000);
    }
  }, []);

  const startEditing = useCallback((t: TeacherRecord) => {
    if (t._index === undefined) return;
    setEditingIndex(t._index);
    setEditedValues({ ...t });
  }, []);

  const cancelEditing = useCallback(() => {
    setEditingIndex(null);
    setEditedValues({});
  }, []);

  const handleFieldChange = useCallback((field: string, value: string) => {
    setEditedValues(prev => ({ ...prev, [field]: value }));
  }, []);

  const saveEditing = useCallback(async () => {
    if (editingIndex === null) return;
    const payload: Partial<TeacherRecord> = {};
    TEACHER_TABLE_KEYS.forEach(k => {
      payload[k] = (editedValues[k] ?? '').trim();
    });
    await onSave(editingIndex, payload);
    setEditingIndex(null);
    setEditedValues({});
  }, [editingIndex, editedValues, onSave]);

  const handleRowContextMenu = useCallback((e: React.MouseEvent, teacher: TeacherRecord) => {
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({ x: e.clientX, y: e.clientY, teacher });
  }, []);

  const resetColumnWidths = useCallback(() => {
    setColumnWidths([...DEFAULT_WIDTHS]);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (_) {}
    setContextMenu(null);
    onToast?.('Ширины колонок сброшены', 'info');
  }, [onToast]);

  const clearFilters = useCallback(() => {
    onFioFilterChange('');
    setContextMenu(null);
    onToast?.('Фильтр очищен', 'info');
  }, [onFioFilterChange, onToast]);

  const getVal = (v: any) => (v === null || v === undefined || v === '' ? '' : String(v));

  return (
    <section className="teachers-table-section">
      <div className="teachers-table-toolbar">
        <span className="teachers-table-total">Всего: {total}</span>
        <div className="teachers-table-hint">Клик по ячейке — копировать, двойной клик по строке — редактировать, ПКМ — меню</div>
      </div>

      <div className="teachers-table-container" ref={tableContainerRef}>
        <div className="teachers-table">
          <div className="teachers-table-header">
            {TEACHER_TABLE_KEYS.map((k, colIndex) => (
              <div
                key={k}
                className="teachers-table-header-cell teachers-table-header-resizable"
                style={{ width: columnWidths[colIndex], minWidth: columnWidths[colIndex], maxWidth: columnWidths[colIndex] }}
              >
                <span className="teachers-table-header-label">{COLUMN_LABELS[k] || k}</span>
                {k === 'fio' && (
                  <input
                    type="text"
                    className="teachers-table-header-filter"
                    value={fioFilter}
                    onChange={e => onFioFilterChange(e.target.value)}
                    placeholder="ФИО..."
                    onClick={e => e.stopPropagation()}
                  />
                )}
                <div
                  className="teachers-table-resize-handle"
                  onMouseDown={e => {
                    e.preventDefault();
                    setResizingCol(colIndex);
                    resizeStartX.current = e.clientX;
                    resizeStartWidth.current = columnWidths[colIndex];
                  }}
                  title="Изменить ширину"
                />
              </div>
            ))}
          </div>
          <div className="teachers-table-body">
            {loading ? (
              [...Array(8)].map((_, i) => (
                <div key={i} className="teachers-table-row">
                  {TEACHER_TABLE_KEYS.map((k, ci) => (
                    <div key={k} className="teachers-table-cell" style={{ width: columnWidths[ci], minWidth: columnWidths[ci], maxWidth: columnWidths[ci] }}>
                      <div className="teachers-table-skeleton" />
                    </div>
                  ))}
                </div>
              ))
            ) : (
              teachers.map(t => {
                const idx = t._index;
                const isEditing = idx !== undefined && editingIndex === idx;
                const row = isEditing ? { ...t, ...editedValues } : t;
                const rowId = `row-${idx ?? -1}`;
                return (
                  <div
                    key={idx ?? -1}
                    className={`teachers-table-row ${isEditing ? 'editing' : ''}`}
                    onDoubleClick={() => !isEditing && startEditing(t)}
                    onContextMenu={e => !isEditing && handleRowContextMenu(e, t)}
                  >
                    {TEACHER_TABLE_KEYS.map((key, cellIndex) => {
                      const cellId = `${rowId}-${cellIndex}`;
                      const isExpanded = expandedCell?.id === cellId;
                      const displayValue = getVal(row[key as keyof TeacherRecord]);
                      const w = columnWidths[cellIndex];

                      if (isEditing && key === 'fio') {
                        return (
                          <div key={key} className="teachers-table-cell teachers-table-cell-actions" style={{ width: w, minWidth: w, maxWidth: w }}>
                            <div className="teachers-table-id-actions">
                              <button type="button" className="teachers-table-btn-save" onClick={saveEditing} title="Сохранить">✓</button>
                              <button type="button" className="teachers-table-btn-cancel" onClick={cancelEditing} title="Отменить">✕</button>
                            </div>
                            <input
                              type="text"
                              className="teachers-table-cell-input"
                              value={getVal(editedValues.fio)}
                              onChange={e => handleFieldChange('fio', e.target.value)}
                              onClick={e => e.stopPropagation()}
                            />
                          </div>
                        );
                      }
                      if (isEditing && key !== 'fio') {
                        return (
                          <div key={key} className="teachers-table-cell" style={{ width: w, minWidth: w, maxWidth: w }}>
                            {key === 'predmet' ? (
                              <textarea
                                className="teachers-table-cell-textarea"
                                value={getVal(row[key as keyof TeacherRecord])}
                                onChange={e => handleFieldChange(key, e.target.value)}
                                onClick={e => e.stopPropagation()}
                                rows={2}
                              />
                            ) : (
                              <input
                                type="text"
                                className="teachers-table-cell-input"
                                value={getVal(row[key as keyof TeacherRecord])}
                                onChange={e => handleFieldChange(key, e.target.value)}
                                onClick={e => e.stopPropagation()}
                              />
                            )}
                          </div>
                        );
                      }
                      return (
                        <div
                          key={key}
                          className={`teachers-table-cell teachers-table-cell-expandable ${copiedCellId === cellId ? 'cell-copied' : ''}`}
                          style={{ width: w, minWidth: w, maxWidth: w }}
                          onMouseEnter={e => handleCellMouseEnter(e, cellId)}
                          onMouseLeave={handleCellMouseLeave}
                          onClick={e => {
                            if (displayValue) copyToClipboard(displayValue, cellId);
                            e.stopPropagation();
                          }}
                          title="Клик — копировать, двойной клик — редактировать"
                        >
                          <div
                            className="teachers-table-cell-content"
                            data-expanded={isExpanded}
                            data-direction={expandedCell?.direction}
                            style={isExpanded ? { width: expandedCell!.width, minWidth: expandedCell!.width, [expandedCell!.direction === 'left' ? 'right' : 'left']: 0 } : {}}
                          >
                            {displayValue || '—'}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {totalPages > 0 && (
        <div className="teachers-table-pagination">
          <button type="button" disabled={page <= 1 || loading} onClick={() => onPageChange(Math.max(1, page - 1))}>
            Назад
          </button>
          <span>Страница {page} из {totalPages}</span>
          <button type="button" disabled={page >= totalPages || loading} onClick={() => onPageChange(Math.min(totalPages, page + 1))}>
            Вперед
          </button>
        </div>
      )}

      {teachers.length === 0 && !loading && (
        <div className="teachers-table-empty">
          {total === 0
            ? 'Список преподавателей пуст. Добавьте ФИО выше или загрузите данные с сайта.'
            : 'Нет записей по фильтру. Измените фильтр по ФИО.'}
        </div>
      )}

      {contextMenu && (
        <div
          className="teachers-table-context-menu"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={e => e.stopPropagation()}
        >
          <button
            type="button"
            className="teachers-table-context-item"
            onClick={() => { onDuplicate(contextMenu.teacher); setContextMenu(null); }}
          >
            Дублировать запись
          </button>
          <button
            type="button"
            className="teachers-table-context-item"
            onClick={() => { onCreateEmpty(); setContextMenu(null); }}
          >
            Создать пустую запись
          </button>
          <div className="teachers-table-context-divider" />
          <button
            type="button"
            className="teachers-table-context-item teachers-table-context-danger"
            onClick={() => { onDelete(contextMenu.teacher); setContextMenu(null); }}
          >
            Удалить запись
          </button>
          <div className="teachers-table-context-divider" />
          <button type="button" className="teachers-table-context-item" onClick={resetColumnWidths}>
            Сбросить ширины колонок
          </button>
          <button type="button" className="teachers-table-context-item" onClick={clearFilters}>
            Очистить фильтры
          </button>
          <div className="teachers-table-context-divider" />
          <button type="button" className="teachers-table-context-item" onClick={() => setContextMenu(null)}>
            Отмена
          </button>
        </div>
      )}
    </section>
  );
};

export default TeachersTable;
