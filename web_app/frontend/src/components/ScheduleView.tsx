import React, { useState, useCallback, useEffect } from 'react';
import axios from 'axios';
import Toast from './Toast';
import './ScheduleView.css';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

const SCHEDULE_LABELS: Record<string, string> = {
  id: 'ID',
  day_of_week: 'День',
  pair_number: 'Пара',
  subject_name: 'Предмет',
  lecture_type: 'Тип',
  audience: 'Ауд.',
  group_name: 'Группа',
  week_type: 'Неделя',
  subgroup: 'п/г',
  institute: 'Институт',
  course: 'Курс',
  direction: 'Направление',
  department: 'Кафедра',
  fio: 'Преподаватель',
  is_external: 'Внешний',
  is_remote: 'Дистант',
  num_subgroups: 'п/г кол-во',
};

const ScheduleView: React.FC = () => {
  const [total, setTotal] = useState(0);
  const [records, setRecords] = useState<Record<string, unknown>[]>([]);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);
  const limit = 50;

  const loadStats = useCallback(async () => {
    try {
      const res = await axios.get(`${API_BASE}/schedule/stats`);
      setTotal((res.data as { total?: number }).total ?? 0);
    } catch {
      setTotal(0);
    }
  }, []);

  const loadRecords = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API_BASE}/schedule/records`, {
        params: { page, limit },
      });
      const data = res.data as { records?: Record<string, unknown>[]; total?: number; error?: string };
      if (data.error) {
        setToast({ message: data.error, type: 'error' });
        setRecords([]);
      } else {
        setRecords(data.records ?? []);
        setTotal(data.total ?? 0);
      }
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } }; message?: string })?.response?.data?.error
        || (err as { message?: string })?.message
        || 'Ошибка загрузки';
      setToast({ message: String(msg), type: 'error' });
      setRecords([]);
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  useEffect(() => {
    loadRecords();
  }, [loadRecords]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      const res = await axios.post(`${API_BASE}/schedule/save`);
      const data = res.data as { saved?: number; message?: string; error?: string };
      if (data.error) {
        setToast({ message: data.error, type: 'error' });
      } else {
        setToast({ message: data.message || `Сохранено записей: ${data.saved ?? 0}`, type: 'success' });
        await loadStats();
        await loadRecords();
      }
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } }; message?: string })?.response?.data?.error
        || (err as { message?: string })?.message
        || 'Ошибка сохранения';
      setToast({ message: String(msg), type: 'error' });
    } finally {
      setSaving(false);
    }
  }, [loadStats, loadRecords]);

  const handleDownloadBackup = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/schedule/backup`);
      if (!res.ok) throw new Error(res.statusText);
      const blob = await res.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `schedule_backup_${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(a.href);
      setToast({ message: 'Файл бэкапа скачан', type: 'success' });
    } catch (e) {
      setToast({ message: (e as Error).message || 'Ошибка скачивания', type: 'error' });
    }
  }, []);

  const handleRestore = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      setRestoring(true);
      try {
        const form = new FormData();
        form.append('file', file);
        const res = await axios.post(`${API_BASE}/schedule/restore`, form, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
        const data = res.data as { restored?: number; message?: string; error?: string };
        if (data.error) {
          setToast({ message: data.error, type: 'error' });
        } else {
          setToast({ message: data.message || `Восстановлено записей: ${data.restored ?? 0}`, type: 'success' });
          await loadStats();
          await loadRecords();
        }
      } catch (err: unknown) {
        const msg = (err as { response?: { data?: { error?: string } }; message?: string })?.response?.data?.error
          || (err as { message?: string })?.message
          || 'Ошибка восстановления';
        setToast({ message: String(msg), type: 'error' });
      } finally {
        setRestoring(false);
        e.target.value = '';
      }
    },
    [loadStats, loadRecords]
  );

  const columns = ['id', 'day_of_week', 'pair_number', 'subject_name', 'lecture_type', 'audience', 'group_name', 'week_type', 'subgroup', 'institute', 'course', 'direction', 'department', 'fio'];
  const pages = Math.max(1, Math.ceil(total / limit));

  return (
    <div className="schedule-view">
      <section className="schedule-toolbar">
        <h2>Расписание</h2>
        <p className="schedule-desc">
          Чистое расписание без полей ошибок (без week_error, audience_error и служебных id).
          Данные копируются из «Промежуточного расписания» по кнопке «Сохранить в Расписание».
        </p>
        <div className="schedule-actions">
          <button
            type="button"
            className="schedule-btn schedule-btn-save"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? 'Сохранение...' : 'Сохранить в Расписание'}
          </button>
          <button
            type="button"
            className="schedule-btn schedule-btn-backup"
            onClick={handleDownloadBackup}
          >
            Скачать backup
          </button>
          <label className="schedule-btn schedule-btn-restore">
            {restoring ? 'Восстановление...' : 'Восстановить из backup'}
            <input
              type="file"
              accept=".json"
              hidden
              disabled={restoring}
              onChange={handleRestore}
            />
          </label>
        </div>
        <p className="schedule-stats">Записей в расписании: <strong>{total}</strong></p>
      </section>

      <section className="schedule-table-wrap">
        {loading ? (
          <p className="schedule-loading">Загрузка...</p>
        ) : records.length === 0 ? (
          <p className="schedule-empty">Нет записей. Нажмите «Сохранить в Расписание» после слияния.</p>
        ) : (
          <>
            <div className="schedule-table-scroll">
              <table className="schedule-table">
                <thead>
                  <tr>
                    {columns.map((col) => (
                      <th key={col}>{SCHEDULE_LABELS[col] ?? col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {records.map((row, idx) => (
                    <tr key={(row.id as number) ?? idx}>
                      {columns.map((col) => (
                        <td key={col}>
                          {row[col] != null ? String(row[col]) : '—'}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {pages > 1 && (
              <div className="schedule-pagination">
                <button
                  type="button"
                  className="schedule-page-btn"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  Назад
                </button>
                <span className="schedule-page-info">
                  Страница {page} из {pages}
                </span>
                <button
                  type="button"
                  className="schedule-page-btn"
                  disabled={page >= pages}
                  onClick={() => setPage((p) => Math.min(pages, p + 1))}
                >
                  Вперёд
                </button>
              </div>
            )}
          </>
        )}
      </section>

      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
          duration={5000}
        />
      )}
    </div>
  );
};

export default ScheduleView;
