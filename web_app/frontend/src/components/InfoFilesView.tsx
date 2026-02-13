import React, { useState, useCallback, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import Toast from './Toast';
import './InfoFilesView.css';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

type InfoFileId = 'skip_row_phrases' | 'slash_protected' | 'strip_from_subject' | 'replace_in_subject';

const INFO_FILES: { id: InfoFileId; label: string; description: string }[] = [
  { id: 'skip_row_phrases', label: 'Пропуск строк', description: 'Фразы, при наличии которых строка таблицы пропускается (skip_row_phrases.json)' },
  { id: 'slash_protected', label: 'Защита слэша', description: 'Токены с «/», которые не разбивать на числитель/знаменатель (slash_protected.json)' },
  { id: 'strip_from_subject', label: 'Удалить из названия', description: 'Фразы, удаляемые из названия дисциплины (strip_from_subject.json)' },
  { id: 'replace_in_subject', label: 'Замена в названии', description: 'Пары «что заменить» → «на что» в тексте дисциплины (replace_in_subject.json)' },
];

type ReplaceItem = { from: string; to: string };

const InfoFilesView: React.FC = () => {
  const [subTab, setSubTab] = useState<InfoFileId>('skip_row_phrases');
  const [items, setItems] = useState<string[]>([]);
  const [replaceItems, setReplaceItems] = useState<ReplaceItem[]>([]);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);
  const queryClient = useQueryClient();

  const isReplace = subTab === 'replace_in_subject';

  const { data, isLoading, error } = useQuery({
    queryKey: ['info-file', subTab],
    queryFn: async () => {
      const res = await axios.get(`${API_BASE}/info-files/${subTab}`);
      return res.data as { content: unknown; raw: string };
    },
  });

  useEffect(() => {
    if (!data?.content) return;
    const content = data.content;
    if (!Array.isArray(content)) return;
    if (subTab === 'replace_in_subject') {
      setReplaceItems(
        content.map((x) => {
          if (x && typeof x === 'object' && 'from' in x && 'to' in x) {
            return { from: String((x as ReplaceItem).from ?? ''), to: String((x as ReplaceItem).to ?? '') };
          }
          return { from: '', to: '' };
        })
      );
    } else {
      setItems(content.map((x) => (typeof x === 'string' ? x : String(x ?? ''))));
    }
  }, [data, subTab]);

  const saveMutation = useMutation({
    mutationFn: async (payload: string[] | ReplaceItem[]) => {
      const raw = JSON.stringify(payload, null, 2);
      const res = await axios.put(`${API_BASE}/info-files/${subTab}`, { raw });
      return res.data as { message: string; raw: string };
    },
    onSuccess: (_, payload) => {
      if (subTab === 'replace_in_subject') setReplaceItems(payload as ReplaceItem[]);
      else setItems(payload as string[]);
      queryClient.invalidateQueries({ queryKey: ['info-file', subTab] });
      setToast({ message: 'Файл сохранён', type: 'success' });
    },
    onError: (err: any) => {
      const msg = err.response?.data?.error || 'Ошибка сохранения';
      setToast({ message: msg, type: 'error' });
    },
  });

  const updateItem = useCallback((index: number, value: string) => {
    setItems((prev) => {
      const next = [...prev];
      next[index] = value;
      return next;
    });
  }, []);

  const updateReplaceItem = useCallback((index: number, field: 'from' | 'to', value: string) => {
    setReplaceItems((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], [field]: value };
      return next;
    });
  }, []);

  const removeItem = useCallback((index: number) => {
    setItems((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const removeReplaceItem = useCallback((index: number) => {
    setReplaceItems((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const addItem = useCallback(() => {
    setItems((prev) => [...prev, '']);
  }, []);

  const addReplaceItem = useCallback(() => {
    setReplaceItems((prev) => [...prev, { from: '', to: '' }]);
  }, []);

  const handleSave = useCallback(() => {
    if (isReplace) {
      const trimmed = replaceItems
        .map((r) => ({ from: r.from.trim(), to: r.to.trim() }))
        .filter((r) => r.from || r.to);
      saveMutation.mutate(trimmed.length ? trimmed : []);
    } else {
      const trimmed = items.map((s) => s.trim()).filter(Boolean);
      saveMutation.mutate(trimmed.length ? trimmed : []);
    }
  }, [isReplace, items, replaceItems, saveMutation]);

  const currentMeta = INFO_FILES.find((f) => f.id === subTab);

  return (
    <div className="info-files-view">
      <div className="info-files-subnav">
        {INFO_FILES.map((f) => (
          <button
            key={f.id}
            type="button"
            className={`info-files-subtab ${subTab === f.id ? 'active' : ''}`}
            onClick={() => setSubTab(f.id)}
          >
            {f.label}
          </button>
        ))}
      </div>
      <div className="info-files-editor card">
        {currentMeta && (
          <p className="info-files-description">{currentMeta.description}</p>
        )}
        {isLoading && <p className="info-files-loading">Загрузка…</p>}
        {error && (
          <p className="info-files-error">
            {(error as any)?.response?.data?.error || 'Ошибка загрузки'}
          </p>
        )}
        {!isLoading && !error && isReplace && (
          <>
            <div className="info-files-list info-files-list-replace">
              <div className="info-files-row info-files-row-header">
                <span className="info-files-row-num">№</span>
                <span className="info-files-replace-from">Заменить</span>
                <span className="info-files-replace-to">На</span>
                <span className="info-files-remove-btn-placeholder" />
              </div>
              {replaceItems.map((row, index) => (
                <div key={index} className="info-files-row info-files-row-replace">
                  <span className="info-files-row-num">{index + 1}</span>
                  <input
                    type="text"
                    className="info-files-input info-files-replace-from"
                    value={row.from}
                    onChange={(e) => updateReplaceItem(index, 'from', e.target.value)}
                    placeholder="м/зал"
                  />
                  <input
                    type="text"
                    className="info-files-input info-files-replace-to"
                    value={row.to}
                    onChange={(e) => updateReplaceItem(index, 'to', e.target.value)}
                    placeholder="К301"
                  />
                  <button
                    type="button"
                    className="info-files-remove-btn"
                    onClick={() => removeReplaceItem(index)}
                    title="Удалить"
                    aria-label="Удалить"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
            <div className="info-files-actions">
              <button type="button" className="info-files-add-btn" onClick={addReplaceItem}>
                + Добавить
              </button>
              <button
                type="button"
                className="info-files-save-btn"
                onClick={handleSave}
                disabled={saveMutation.isPending}
              >
                {saveMutation.isPending ? 'Сохранение…' : 'Сохранить'}
              </button>
            </div>
          </>
        )}
        {!isLoading && !error && !isReplace && (
          <>
            <div className="info-files-list">
              {items.map((value, index) => (
                <div key={index} className="info-files-row">
                  <span className="info-files-row-num">{index + 1}</span>
                  <input
                    type="text"
                    className="info-files-input"
                    value={value}
                    onChange={(e) => updateItem(index, e.target.value)}
                    placeholder="Введите фразу или токен"
                  />
                  <button
                    type="button"
                    className="info-files-remove-btn"
                    onClick={() => removeItem(index)}
                    title="Удалить"
                    aria-label="Удалить"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
            <div className="info-files-actions">
              <button type="button" className="info-files-add-btn" onClick={addItem}>
                + Добавить
              </button>
              <button
                type="button"
                className="info-files-save-btn"
                onClick={handleSave}
                disabled={saveMutation.isPending}
              >
                {saveMutation.isPending ? 'Сохранение…' : 'Сохранить'}
              </button>
            </div>
          </>
        )}
      </div>
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
        />
      )}
    </div>
  );
};

export default InfoFilesView;
