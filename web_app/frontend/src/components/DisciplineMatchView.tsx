import React, { useState, useCallback } from 'react';
import axios from 'axios';
import Toast from './Toast';
import './DisciplineMatchView.css';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

export interface MatchAlternative {
  name: string;
  score: number;
}

export interface MatchItem {
  original: string;
  suggested: string;
  score: number;
  alternatives: MatchAlternative[];
}

type DisciplineMatchSource = 'intermediate' | 'aspi' | 'spo';

const DisciplineMatchView: React.FC = () => {
  const [source, setSource] = useState<DisciplineMatchSource>('intermediate');
  const [threshold, setThreshold] = useState<string>('0.95');
  const [stripText, setStripText] = useState<string>('');
  const [stripAt, setStripAt] = useState<'start' | 'end'>('start');
  const [matchFull, setMatchFull] = useState<boolean>(true);
  const [ollamaMode, setOllamaMode] = useState<'remote' | 'local'>('remote');
  const [items, setItems] = useState<MatchItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);
  const [replacing, setReplacing] = useState<string | null>(null);
  const [applying, setApplying] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string>('');
  const [hiddenOriginals, setHiddenOriginals] = useState<Set<string>>(new Set());
  const [showHiddenOnly, setShowHiddenOnly] = useState(false);
  const [selectedAlt, setSelectedAlt] = useState<Record<string, string>>({});
  const [customName, setCustomName] = useState<Record<string, string>>({});

  const loadUnmatched = useCallback(async () => {
    setLoading(true);
    setStatusMessage('Загрузка несовпадающих дисциплин...');
    try {
      const params = new URLSearchParams({ table: source });
      if (stripText.trim()) {
        params.set('strip_text', stripText.trim());
        params.set('strip_at', stripAt);
      }
      if (ollamaMode === 'local') {
        params.set('ollama', 'local');
      }
      params.set('match_full', matchFull ? '1' : '0');
      const res = await axios.get(`${API_BASE}/discipline-match/unmatched?${params.toString()}`);
      const data = res.data as { items: MatchItem[]; error?: string };
      if (data.error) {
        setStatusMessage(`Ошибка: ${data.error}`);
        setToast({ message: data.error, type: 'error' });
        setItems([]);
      } else {
        const list = data.items || [];
        setItems(list);
        setSelectedAlt({});
        setCustomName({});
        setHiddenOriginals(new Set());
        setShowHiddenOnly(false);
        setStatusMessage(list.length ? `Загружено несовпадающих: ${list.length}` : 'Нет несовпадающих дисциплин');
      }
    } catch (err: any) {
      const data = err.response?.data;
      const msg =
        (typeof data === 'object' && data?.error) ||
        (typeof data === 'string' ? data : null) ||
        err.message ||
        'Ошибка загрузки';
      setStatusMessage(`Ошибка: ${msg}`);
      setToast({ message: String(msg), type: 'error' });
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [source, stripText, stripAt, matchFull, ollamaMode]);

  const replaceWith = useCallback(async (original: string, replacement: string) => {
    if (!replacement?.trim()) return;
    setReplacing(original);
    setStatusMessage('Выполняю замену...');
    try {
      const res = await axios.post(`${API_BASE}/discipline-match/replace`, {
        original,
        replacement: replacement.trim(),
        table: source
      });
      const data = res.data as { updated?: number; error?: string };
      if (data.error) {
        setStatusMessage(`Ошибка: ${data.error}`);
        setToast({ message: data.error, type: 'error' });
      } else {
        const n = data.updated ?? 0;
        setItems(prev => prev.filter(i => i.original !== original));
        setStatusMessage(`Заменено записей: ${n}`);
        setToast({ message: `Заменено записей: ${n}`, type: 'success' });
      }
    } catch (err: any) {
      const data = err.response?.data;
      const msg =
        (typeof data === 'object' && data?.error) ||
        (typeof data === 'string' ? data : null) ||
        err.message ||
        'Ошибка замены';
      setStatusMessage(`Ошибка: ${msg}`);
      setToast({ message: String(msg), type: 'error' });
    } finally {
      setReplacing(null);
    }
  }, [source]);

  const handleReplaceSuggested = useCallback((item: MatchItem) => {
    replaceWith(item.original, item.suggested);
  }, [replaceWith]);

  const handleReplaceAlternative = useCallback((item: MatchItem, name: string) => {
    replaceWith(item.original, name);
  }, [replaceWith]);

  const handleApplyThreshold = useCallback(async () => {
    const t = parseFloat(threshold);
    if (Number.isNaN(t) || t < 0 || t > 1) {
      setStatusMessage('Введите порог от 0 до 1');
      setToast({ message: 'Введите порог от 0 до 1', type: 'error' });
      return;
    }
    setApplying(true);
    setStatusMessage('Применяю порог в БД...');
    try {
      const body: Record<string, unknown> = { threshold: t, table: source, match_full: matchFull };
      if (stripText.trim()) {
        body.strip_text = stripText.trim();
        body.strip_at = stripAt;
      }
      if (ollamaMode === 'local') {
        body.ollama = 'local';
      }
      const res = await axios.post(`${API_BASE}/discipline-match/apply`, body);
      const data = res.data as { replaced?: number; error?: string; message?: string };
      if (data.error) {
        setStatusMessage(`Ошибка: ${data.error}`);
        setToast({ message: data.error, type: 'error' });
      } else {
        const count = data.replaced ?? 0;
        const msg = count > 0
          ? `В БД заменено: ${count}`
          : (data.message || 'Нет дисциплин выше порога');
        setStatusMessage(msg);
        setToast({
          message: count > 0
            ? `В БД заменено дисциплин с точностью ≥ ${threshold}: ${count}`
            : (data.message || 'Нет дисциплин выше порога для автоматической замены'),
          type: count > 0 ? 'success' : 'info'
        });
        if (count > 0) {
          await loadUnmatched();
        }
      }
    } catch (err: any) {
      const data = err.response?.data;
      const msg =
        (typeof data === 'object' && data?.error) ||
        (typeof data === 'string' ? data : null) ||
        err.message ||
        'Ошибка применения порога';
      setStatusMessage(`Ошибка: ${msg}`);
      setToast({ message: String(msg), type: 'error' });
    } finally {
      setApplying(false);
    }
  }, [threshold, source, stripText, stripAt, matchFull, loadUnmatched]);

  const visibleItems = showHiddenOnly
    ? items.filter((i) => hiddenOriginals.has(i.original))
    : items.filter((i) => !hiddenOriginals.has(i.original));
  const hiddenCount = hiddenOriginals.size;

  const toggleHide = useCallback((original: string) => {
    setHiddenOriginals((prev) => {
      const next = new Set(prev);
      if (next.has(original)) next.delete(original);
      else next.add(original);
      return next;
    });
  }, []);

  const showAllHidden = useCallback(() => {
    setShowHiddenOnly((v) => !v);
  }, []);

  const unhideAll = useCallback(() => {
    setHiddenOriginals(new Set());
    setShowHiddenOnly(false);
  }, []);

  const onSourceChange = useCallback((newSource: DisciplineMatchSource) => {
    if (newSource === source) return;
    setSource(newSource);
    setItems([]);
    setStatusMessage(
      newSource === 'aspi'
        ? 'Выбрана таблица аспирантов (timetable_aspi). Нажмите «Загрузить несовпадающие».'
        : newSource === 'spo'
          ? 'Выбрана таблица СПО (timetable_spo). Нажмите «Загрузить несовпадающие».'
          : 'Выбрана таблица бакалавров/магистров. Нажмите «Загрузить несовпадающие».'
    );
    setHiddenOriginals(new Set());
    setShowHiddenOnly(false);
  }, [source]);

  return (
    <div className="discipline-match-view">
      <section className="discipline-match-toolbar">
        <h2>Сопоставление дисциплин из БД со справочником</h2>
        <div className="discipline-match-tabs">
          <button
            type="button"
            className={`discipline-match-tab ${source === 'intermediate' ? 'discipline-match-tab-active' : ''}`}
            onClick={() => onSourceChange('intermediate')}
          >
            Бакалавры и магистры
          </button>
          <button
            type="button"
            className={`discipline-match-tab ${source === 'aspi' ? 'discipline-match-tab-active' : ''}`}
            onClick={() => onSourceChange('aspi')}
          >
            Аспиранты
          </button>
          <button
            type="button"
            className={`discipline-match-tab ${source === 'spo' ? 'discipline-match-tab-active' : ''}`}
            onClick={() => onSourceChange('spo')}
          >
            СПО
          </button>
        </div>
        <p className="discipline-match-desc">
          {source === 'aspi' ? (
            <>Загружаются названия из <code>timetable_aspi</code>, которых нет в <code>info/discipline.json</code>. Замены применяются только в таблице аспирантов.</>
          ) : source === 'spo' ? (
            <>Загружаются названия из <code>timetable_spo</code>, которых нет в <code>info/discipline.json</code>. Замены применяются только в таблице СПО.</>
          ) : (
            <>Загружаются названия из <code>intermediate_timetable</code>, которых нет в <code>info/discipline.json</code>. Кнопка «Применить порог в БД» автоматически заменяет в БД все дисциплины с точностью ≥ порога; остальные — вручную по кнопкам.</>
          )}
        </p>
        <div className="discipline-match-controls">
          <label>
            Удалить перед сравнением
            <input
              type="text"
              placeholder="например: ФТД: "
              value={stripText}
              onChange={e => setStripText(e.target.value)}
              className="discipline-match-strip-input"
            />
          </label>
          <label className="discipline-match-radio-label">
            <input
              type="radio"
              name="strip_at"
              checked={stripAt === 'start'}
              onChange={() => setStripAt('start')}
            />
            в начале
          </label>
          <label className="discipline-match-radio-label">
            <input
              type="radio"
              name="strip_at"
              checked={stripAt === 'end'}
              onChange={() => setStripAt('end')}
            />
            в конце
          </label>
          <label className="discipline-match-checkbox-label">
            <input
              type="checkbox"
              checked={matchFull}
              onChange={e => setMatchFull(e.target.checked)}
            />
            полное сравнение
          </label>
          <div className="discipline-match-ollama-mode">
            <span className="discipline-match-ollama-label">Векторизация (Ollama):</span>
            <label className="discipline-match-radio-label">
              <input
                type="radio"
                name="ollama_mode"
                checked={ollamaMode === 'remote'}
                onChange={() => setOllamaMode('remote')}
              />
              удалённая
            </label>
            <label className="discipline-match-radio-label">
              <input
                type="radio"
                name="ollama_mode"
                checked={ollamaMode === 'local'}
                onChange={() => setOllamaMode('local')}
              />
              локальная
            </label>
          </div>
          <label>
            Порог точности (0–1)
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={threshold}
              onChange={e => setThreshold(e.target.value)}
              className="discipline-match-threshold"
            />
          </label>
          <button
            type="button"
            className="discipline-match-load-btn"
            onClick={(e) => {
              e.preventDefault();
              if (!loading) loadUnmatched();
            }}
            disabled={loading}
          >
            {loading ? 'Загрузка...' : 'Загрузить несовпадающие'}
          </button>
          <button
            type="button"
            className="discipline-match-apply-btn"
            onClick={(e) => {
              e.preventDefault();
              if (!applying) handleApplyThreshold();
            }}
            disabled={loading || applying}
          >
            {applying ? 'Применяю...' : 'Применить порог в БД'}
          </button>
        </div>
        {statusMessage && (
          <p className="discipline-match-status" role="status">
            {statusMessage}
          </p>
        )}
      </section>

      <section className="discipline-match-list">
        {items.length > 0 && (
          <>
            <p className="discipline-match-remaining">
              {showHiddenOnly
                ? `Скрытые записи: ${visibleItems.length}`
                : `Осталось: ${visibleItems.length}${hiddenCount > 0 ? ` (скрыто: ${hiddenCount})` : ''}`}
            </p>
            {hiddenCount > 0 && (
              <div className="discipline-match-hide-actions">
                <button
                  type="button"
                  className="discipline-match-btn discipline-match-btn-secondary"
                  onClick={showAllHidden}
                >
                  {showHiddenOnly ? 'Показать все' : `Показать скрытые записи (${hiddenCount})`}
                </button>
                {showHiddenOnly && (
                  <button
                    type="button"
                    className="discipline-match-btn"
                    onClick={unhideAll}
                  >
                    Вернуть все в список
                  </button>
                )}
              </div>
            )}
          </>
        )}
        {items.length === 0 && !loading && (
          <p className="discipline-match-empty">
            Нет несовпадающих дисциплин или загрузите список кнопкой выше.
          </p>
        )}
        {visibleItems.length === 0 && items.length > 0 && !loading && (
          <p className="discipline-match-empty">
            {showHiddenOnly ? 'Нет скрытых записей.' : 'Все записи скрыты. Нажмите «Показать скрытые записи».'}
          </p>
        )}
        {visibleItems.map((item, idx) => (
          <div key={`${item.original}-${idx}`} className="discipline-match-card">
            <div className="discipline-match-row discipline-match-row-header">
              <span className="discipline-match-label">Исходное название:</span>
              <span className="discipline-match-original">{item.original}</span>
              <button
                type="button"
                className="discipline-match-hide-btn"
                onClick={() => toggleHide(item.original)}
                title={showHiddenOnly ? 'Вернуть в список' : 'Скрыть запись'}
              >
                {showHiddenOnly ? 'Вернуть в список' : 'Скрыть'}
              </button>
            </div>
            <div className="discipline-match-row">
              <span className="discipline-match-label">Предложено:</span>
              <span className="discipline-match-suggested">{item.suggested || '—'}</span>
              <span className="discipline-match-score">Точность: {item.score.toFixed(3)}</span>
            </div>
            <div className="discipline-match-actions">
              <button
                type="button"
                className="discipline-match-btn discipline-match-btn-primary"
                onClick={() => handleReplaceSuggested(item)}
                disabled={replacing === item.original || !item.suggested}
              >
                {replacing === item.original ? 'Замена...' : 'Заменить на предложенное'}
              </button>
              {item.alternatives && item.alternatives.length > 0 && (
                <div className="discipline-match-alt">
                  <label>Другие варианты (3 ближайших):</label>
                  <select
                    value={selectedAlt[item.original] ?? ''}
                    onChange={e => setSelectedAlt(prev => ({ ...prev, [item.original]: e.target.value }))}
                    className="discipline-match-select"
                  >
                    <option value="">— выбрать —</option>
                    {item.alternatives.map((alt, i) => (
                      <option key={i} value={alt.name}>
                        {alt.name} (точность {alt.score.toFixed(3)})
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="discipline-match-btn"
                    onClick={() => selectedAlt[item.original] && handleReplaceAlternative(item, selectedAlt[item.original])}
                    disabled={!selectedAlt[item.original] || replacing === item.original}
                  >
                    Заменить на выбранное
                  </button>
                </div>
              )}
              <div className="discipline-match-custom">
                <label>Или введите своё название:</label>
                <input
                  type="text"
                  className="discipline-match-custom-input"
                  placeholder="Название дисциплины"
                  value={customName[item.original] ?? ''}
                  onChange={e => setCustomName(prev => ({ ...prev, [item.original]: e.target.value }))}
                />
                <button
                  type="button"
                  className="discipline-match-btn"
                  onClick={() => (customName[item.original]?.trim() && replaceWith(item.original, customName[item.original].trim()))}
                  disabled={!customName[item.original]?.trim() || replacing === item.original}
                >
                  Заменить на введённое
                </button>
              </div>
            </div>
          </div>
        ))}
      </section>

      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
          duration={6000}
        />
      )}
    </div>
  );
};

export default DisciplineMatchView;
