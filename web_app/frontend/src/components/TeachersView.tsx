import React, { useState, useCallback, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { useDebounce } from '../hooks/useDebounce';
import Toast from './Toast';
import TeachersTable, { type TeacherRecord } from './TeachersTable';
import './TeachersView.css';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

export type { TeacherRecord };

const TeachersView: React.FC = () => {
  const [page, setPage] = useState(1);
  const [fioFilter, setFioFilter] = useState('');
  const [bulkLines, setBulkLines] = useState('');
  const [bulkLoading, setBulkLoading] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);
  const [fetchStatus, setFetchStatus] = useState<{ running: boolean; message: string; error: string | null }>({ running: false, message: '', error: null });
  const debouncedFio = useDebounce(fioFilter, 500);
  const queryClient = useQueryClient();
  const limit = 50;

  const pollFetchStatus = useCallback(async () => {
    try {
      const res = await axios.get(`${API_BASE}/status/fetch_teachers`);
      const d = res.data as { running: boolean; message: string; error: string | null };
      setFetchStatus({ running: d.running, message: d.message || '', error: d.error || null });
      if (!d.running && !d.error) {
        queryClient.invalidateQueries({ queryKey: ['teachers'] });
      }
    } catch (_) {}
  }, [queryClient]);

  useEffect(() => {
    if (!fetchStatus.running) return;
    const t = setInterval(pollFetchStatus, 2000);
    return () => clearInterval(t);
  }, [fetchStatus.running, pollFetchStatus]);

  const { data, isLoading } = useQuery({
    queryKey: ['teachers', page, debouncedFio, limit],
    queryFn: async () => {
      const params: Record<string, string | number> = { page, limit };
      if (debouncedFio) params.fio = debouncedFio;
      const res = await axios.get(`${API_BASE}/teachers`, { params });
      return res.data as { teachers: TeacherRecord[]; total: number; pages: number };
    },
  });

  const teachers = data?.teachers ?? [];
  const totalPages = data?.pages ?? 0;
  const total = data?.total ?? 0;

  const saveTeacher = useCallback(async (index: number, values: Partial<TeacherRecord>) => {
    try {
      const payload: Record<string, string> = {};
      (['fio', 'post_name', 'post_struct', 'all_staj', 'staj_spec', 'phone', 'predmet'] as const).forEach(k => {
        const v = values[k];
        payload[k] = typeof v === 'string' ? v.trim() : '';
      });
      await axios.put(`${API_BASE}/teachers/${index}`, payload);
      queryClient.invalidateQueries({ queryKey: ['teachers'] });
      setToast({ message: 'Сохранено', type: 'success' });
    } catch (err: any) {
      const msg = err.response?.data?.error || 'Ошибка сохранения';
      setToast({ message: msg, type: 'error' });
    }
  }, [queryClient]);

  const duplicateTeacher = useCallback(async (t: TeacherRecord) => {
    try {
      const payload = {
        fio: (t.fio || '').trim(),
        post_name: (t.post_name || '').trim(),
        post_struct: (t.post_struct || '').trim(),
        all_staj: (t.all_staj || '').trim(),
        staj_spec: (t.staj_spec || '').trim(),
        phone: (t.phone || '').trim(),
        predmet: (t.predmet || '').trim()
      };
      await axios.post(`${API_BASE}/teachers`, payload);
      queryClient.invalidateQueries({ queryKey: ['teachers'] });
      setToast({ message: 'Запись продублирована', type: 'success' });
    } catch (err: any) {
      const msg = err.response?.data?.error || 'Ошибка дублирования';
      setToast({ message: msg, type: 'error' });
    }
  }, [queryClient]);

  const createEmptyTeacher = useCallback(async () => {
    try {
      await axios.post(`${API_BASE}/teachers`, {
        fio: '',
        post_name: '',
        post_struct: '',
        all_staj: '',
        staj_spec: '',
        phone: '',
        predmet: ''
      });
      queryClient.invalidateQueries({ queryKey: ['teachers'] });
      setToast({ message: 'Пустая запись добавлена', type: 'success' });
    } catch (err: any) {
      const msg = err.response?.data?.error || 'Ошибка добавления';
      setToast({ message: msg, type: 'error' });
    }
  }, [queryClient]);

  const deleteTeacher = useCallback(async (t: TeacherRecord) => {
    const idx = t._index;
    if (idx === undefined) return;
    if (!window.confirm('Удалить этого преподавателя из списка?')) return;
    try {
      await axios.delete(`${API_BASE}/teachers/${idx}`);
      queryClient.invalidateQueries({ queryKey: ['teachers'] });
      setToast({ message: 'Удалено', type: 'success' });
    } catch (err: any) {
      const msg = err.response?.data?.error || 'Ошибка удаления';
      setToast({ message: msg, type: 'error' });
    }
  }, [queryClient]);

  const handleBulkAdd = useCallback(async () => {
    const lines = bulkLines.trim();
    if (!lines) {
      setToast({ message: 'Вставьте строки (каждая строка — ФИО)', type: 'info' });
      return;
    }
    setBulkLoading(true);
    try {
      const res = await axios.post(`${API_BASE}/teachers/bulk`, { lines });
      const d = res.data as { added: number; skipped_duplicates: number; total: number };
      setBulkLines('');
      queryClient.invalidateQueries({ queryKey: ['teachers'] });
      setToast({
        message: `Добавлено: ${d.added}, пропущено дубликатов: ${d.skipped_duplicates}. Всего записей: ${d.total}`,
        type: 'success'
      });
    } catch (err: any) {
      const msg = err.response?.data?.error || 'Ошибка добавления';
      setToast({ message: msg, type: 'error' });
    } finally {
      setBulkLoading(false);
    }
  }, [bulkLines, queryClient]);

  const startFetchFromSite = useCallback(async () => {
    try {
      await axios.post(`${API_BASE}/run/fetch_teachers`);
      setFetchStatus(prev => ({ ...prev, running: true, message: 'Запуск...', error: null }));
      pollFetchStatus();
    } catch (err: any) {
      setToast({ message: err.response?.data?.error || 'Ошибка запуска', type: 'error' });
    }
  }, [pollFetchStatus]);

  return (
    <div className="teachers-view">
      <section className="teachers-fetch-site">
        <h3>Дополнить с сайта СурГУ</h3>
        <p className="teachers-fetch-hint">Собрать данные преподавателей с сайта и перезаписать info/teacher_all.json (долго, до 1000 страниц).</p>
        <button type="button" className="teachers-fetch-btn" onClick={startFetchFromSite} disabled={fetchStatus.running}>
          {fetchStatus.running ? fetchStatus.message : 'Дополнить с сайта'}
        </button>
        {fetchStatus.error && <p className="teachers-fetch-error">{fetchStatus.error}</p>}
      </section>

      <section className="teachers-bulk">
        <h3>Добавить по списку</h3>
        <p className="teachers-bulk-hint">Вставьте список ФИО: каждая строка — один преподаватель. Дубликаты не добавляются.</p>
        <textarea
          className="teachers-bulk-textarea"
          placeholder="Иванов Иван Иванович&#10;Петрова Мария Сергеевна&#10;..."
          value={bulkLines}
          onChange={e => setBulkLines(e.target.value)}
          rows={5}
        />
        <button type="button" className="teachers-bulk-btn" onClick={handleBulkAdd} disabled={bulkLoading}>
          {bulkLoading ? 'Добавление...' : 'Добавить'}
        </button>
      </section>

      <TeachersTable
        teachers={teachers}
        loading={isLoading}
        page={page}
        totalPages={totalPages}
        total={total}
        fioFilter={fioFilter}
        onFioFilterChange={setFioFilter}
        onPageChange={setPage}
        onSave={saveTeacher}
        onDuplicate={duplicateTeacher}
        onCreateEmpty={createEmptyTeacher}
        onDelete={deleteTeacher}
        onToast={(msg, type) => setToast({ message: msg, type })}
      />

      {toast && (
        <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />
      )}
    </div>
  );
};

export default TeachersView;
