import React, { useState, useCallback, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { useDebounce } from '../hooks/useDebounce';
import Toast from './Toast';
import './DisciplinesView.css';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

export interface DisciplineItem {
  name: string;
  _index?: number;
}

const DisciplinesView: React.FC = () => {
  const [page, setPage] = useState(1);
  const [nameFilter, setNameFilter] = useState('');
  const [bulkLines, setBulkLines] = useState('');
  const [bulkLoading, setBulkLoading] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editingName, setEditingName] = useState('');
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; item: DisciplineItem } | null>(null);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);
  const debouncedName = useDebounce(nameFilter, 500);
  const queryClient = useQueryClient();
  const limit = 50;

  const { data, isLoading } = useQuery({
    queryKey: ['disciplines', page, debouncedName, limit],
    queryFn: async () => {
      const params: Record<string, string | number> = { page, limit };
      if (debouncedName) params.name = debouncedName;
      const res = await axios.get(`${API_BASE}/disciplines`, { params });
      return res.data as { disciplines: DisciplineItem[]; total: number; pages: number };
    },
  });

  const disciplines = data?.disciplines ?? [];
  const totalPages = data?.pages ?? 0;
  const total = data?.total ?? 0;

  const startEditing = useCallback((item: DisciplineItem) => {
    if (item._index === undefined) return;
    setEditingIndex(item._index);
    setEditingName(item.name || '');
  }, []);

  const cancelEditing = useCallback(() => {
    setEditingIndex(null);
    setEditingName('');
  }, []);

  const saveEditing = useCallback(async () => {
    if (editingIndex === null) return;
    const name = editingName.trim();
    if (!name) {
      setToast({ message: 'Название не может быть пустым', type: 'info' });
      return;
    }
    try {
      await axios.put(`${API_BASE}/disciplines/${editingIndex}`, { name });
      queryClient.invalidateQueries({ queryKey: ['disciplines'] });
      setEditingIndex(null);
      setEditingName('');
      setToast({ message: 'Сохранено', type: 'success' });
    } catch (err: any) {
      const msg = err.response?.data?.error || 'Ошибка сохранения';
      setToast({ message: msg, type: 'error' });
    }
  }, [editingIndex, editingName, queryClient]);

  const duplicateItem = useCallback(async (item: DisciplineItem) => {
    try {
      await axios.post(`${API_BASE}/disciplines`, { name: item.name || '' });
      queryClient.invalidateQueries({ queryKey: ['disciplines'] });
      setToast({ message: 'Дисциплина продублирована', type: 'success' });
    } catch (err: any) {
      const msg = err.response?.data?.error || 'Ошибка (возможно, дубликат)';
      setToast({ message: msg, type: 'error' });
    }
    setContextMenu(null);
  }, [queryClient]);

  const deleteItem = useCallback(async (item: DisciplineItem) => {
    const idx = item._index;
    if (idx === undefined) return;
    if (!window.confirm('Удалить эту дисциплину из списка?')) return;
    try {
      await axios.delete(`${API_BASE}/disciplines/${idx}`);
      queryClient.invalidateQueries({ queryKey: ['disciplines'] });
      setToast({ message: 'Удалено', type: 'success' });
    } catch (err: any) {
      const msg = err.response?.data?.error || 'Ошибка удаления';
      setToast({ message: msg, type: 'error' });
    }
    setContextMenu(null);
  }, [queryClient]);

  const handleBulkAdd = useCallback(async () => {
    const lines = bulkLines.trim();
    if (!lines) {
      setToast({ message: 'Вставьте строки (каждая строка — название дисциплины)', type: 'info' });
      return;
    }
    setBulkLoading(true);
    try {
      const res = await axios.post(`${API_BASE}/disciplines/bulk`, { lines });
      const d = res.data as { added: number; skipped_duplicates: number; total: number };
      setBulkLines('');
      queryClient.invalidateQueries({ queryKey: ['disciplines'] });
      setToast({
        message: `Добавлено: ${d.added}, пропущено дубликатов: ${d.skipped_duplicates}. Всего: ${d.total}`,
        type: 'success'
      });
    } catch (err: any) {
      const msg = err.response?.data?.error || 'Ошибка добавления';
      setToast({ message: msg, type: 'error' });
    } finally {
      setBulkLoading(false);
    }
  }, [bulkLines, queryClient]);

  useEffect(() => {
    if (!contextMenu) return;
    const close = () => setContextMenu(null);
    document.addEventListener('click', close);
    document.addEventListener('contextmenu', close);
    return () => {
      document.removeEventListener('click', close);
      document.removeEventListener('contextmenu', close);
    };
  }, [contextMenu]);

  return (
    <div className="disciplines-view">
      <section className="disciplines-bulk">
        <h3>Добавить по списку</h3>
        <p className="disciplines-bulk-hint">Каждая строка — одно название дисциплины. Дубликаты не добавляются.</p>
        <textarea
          className="disciplines-bulk-textarea"
          placeholder="Математика&#10;Физика&#10;Информатика&#10;..."
          value={bulkLines}
          onChange={e => setBulkLines(e.target.value)}
          rows={5}
        />
        <button type="button" className="disciplines-bulk-btn" onClick={handleBulkAdd} disabled={bulkLoading}>
          {bulkLoading ? 'Добавление...' : 'Добавить'}
        </button>
      </section>

      <section className="disciplines-table-section">
        <div className="disciplines-toolbar">
          <label>
            Фильтр по названию:
            <input
              type="text"
              className="disciplines-filter-input"
              value={nameFilter}
              onChange={e => setNameFilter(e.target.value)}
              placeholder="Часть названия..."
            />
          </label>
          <span className="disciplines-total">Всего: {total}</span>
          <div className="disciplines-hint">Двойной клик — редактировать, ПКМ — меню</div>
        </div>

        <div className="disciplines-table-container">
          <table className="disciplines-table">
            <thead>
              <tr>
                <th className="disciplines-th-num">№</th>
                <th className="disciplines-th-name">Название дисциплины</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                [...Array(10)].map((_, i) => (
                  <tr key={i}>
                    <td className="disciplines-td-num"><div className="disciplines-skeleton" /></td>
                    <td className="disciplines-td-name"><div className="disciplines-skeleton" /></td>
                  </tr>
                ))
              ) : (
                disciplines.map((item, i) => {
                  const idx = item._index;
                  const isEditing = idx !== undefined && editingIndex === idx;
                  return (
                    <tr
                      key={idx ?? i}
                      className={isEditing ? 'editing' : ''}
                      onDoubleClick={() => !isEditing && startEditing(item)}
                      onContextMenu={e => {
                        if (!isEditing) {
                          e.preventDefault();
                          setContextMenu({ x: e.clientX, y: e.clientY, item });
                        }
                      }}
                    >
                      <td className="disciplines-td-num">{(page - 1) * limit + i + 1}</td>
                      <td className="disciplines-td-name">
                        {isEditing ? (
                          <div className="disciplines-edit-cell">
                            <input
                              type="text"
                              className="disciplines-cell-input"
                              value={editingName}
                              onChange={e => setEditingName(e.target.value)}
                              onClick={e => e.stopPropagation()}
                              autoFocus
                            />
                            <button type="button" className="disciplines-btn-save" onClick={saveEditing}>Сохранить</button>
                            <button type="button" className="disciplines-btn-cancel" onClick={cancelEditing}>Отмена</button>
                          </div>
                        ) : (
                          item.name || '—'
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {totalPages > 0 && (
          <div className="disciplines-pagination">
            <button type="button" disabled={page <= 1 || isLoading} onClick={() => setPage(p => Math.max(1, p - 1))}>
              Назад
            </button>
            <span>Страница {page} из {totalPages}</span>
            <button type="button" disabled={page >= totalPages || isLoading} onClick={() => setPage(p => Math.min(totalPages, p + 1))}>
              Вперед
            </button>
          </div>
        )}

        {disciplines.length === 0 && !isLoading && (
          <div className="disciplines-empty">
            {total === 0
              ? 'Список дисциплин пуст. Добавьте названия выше.'
              : 'Нет записей по фильтру.'}
          </div>
        )}
      </section>

      {contextMenu && (
        <div
          className="disciplines-context-menu"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={e => e.stopPropagation()}
        >
          <button type="button" className="disciplines-context-item" onClick={() => duplicateItem(contextMenu.item)}>
            Дублировать
          </button>
          <button type="button" className="disciplines-context-item disciplines-context-danger" onClick={() => deleteItem(contextMenu.item)}>
            Удалить
          </button>
          <div className="disciplines-context-divider" />
          <button type="button" className="disciplines-context-item" onClick={() => { setNameFilter(''); setContextMenu(null); }}>
            Очистить фильтр
          </button>
          <button type="button" className="disciplines-context-item" onClick={() => setContextMenu(null)}>
            Отмена
          </button>
        </div>
      )}

      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
    </div>
  );
};

export default DisciplinesView;
