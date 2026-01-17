import React, { useState, useEffect } from 'react';
import { api, Abbreviations } from '../api';
import './AbbreviationsEditor.css';

const AbbreviationsEditor: React.FC = () => {
  const [data, setData] = useState<Abbreviations | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    loadAbbreviations();
  }, []);

  const loadAbbreviations = async () => {
    try {
      const response = await api.getAbbreviations();
      setData(response.data);
    } catch (error) {
      console.error('Error loading abbreviations:', error);
      setMessage('Ошибка при загрузке сокращений');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!data) return;
    
    setSaving(true);
    setMessage('');
    
    try {
      await api.saveAbbreviations(data);
      setMessage('Сокращения успешно сохранены!');
      setTimeout(() => setMessage(''), 3000);
    } catch (error) {
      console.error('Error saving abbreviations:', error);
      setMessage('Ошибка при сохранении');
    } finally {
      setSaving(false);
    }
  };

  const handleAddCategory = () => {
    if (!data) return;
    
    const categoryName = prompt('Введите название категории:');
    if (categoryName && !data.abbreviations[categoryName]) {
      setData({
        ...data,
        abbreviations: {
          ...data.abbreviations,
          [categoryName]: {}
        }
      });
    }
  };

  const handleAddAbbreviation = (category: string) => {
    if (!data) return;
    
    const pattern = prompt('Введите паттерн (regex):');
    const replacement = prompt('Введите замену:');
    
    if (pattern && replacement) {
      setData({
        ...data,
        abbreviations: {
          ...data.abbreviations,
          [category]: {
            ...data.abbreviations[category],
            [pattern]: replacement
          }
        }
      });
    }
  };

  const handleDeleteAbbreviation = (category: string, pattern: string) => {
    if (!data) return;
    
    if (window.confirm('Удалить это сокращение?')) {
      const newCategory = { ...data.abbreviations[category] };
      delete newCategory[pattern];
      
      setData({
        ...data,
        abbreviations: {
          ...data.abbreviations,
          [category]: newCategory
        }
      });
    }
  };

  const handleUpdateAbbreviation = (
    category: string,
    oldPattern: string,
    newPattern: string,
    newReplacement: string
  ) => {
    if (!data) return;
    
    const newCategory = { ...data.abbreviations[category] };
    delete newCategory[oldPattern];
    newCategory[newPattern] = newReplacement;
    
    setData({
      ...data,
      abbreviations: {
        ...data.abbreviations,
        [category]: newCategory
      }
    });
  };

  if (loading) {
    return <div className="card">Загрузка...</div>;
  }

  if (!data) {
    return <div className="card">Ошибка загрузки данных</div>;
  }

  return (
    <div className="abbreviations-editor">
      <div className="card">
        <div className="editor-header">
          <h2>Редактор сокращений</h2>
          <div className="editor-actions">
            <button className="btn btn-secondary" onClick={handleAddCategory}>
              Добавить категорию
            </button>
            <button className="btn" onClick={handleSave} disabled={saving}>
              {saving ? 'Сохранение...' : 'Сохранить'}
            </button>
          </div>
        </div>
        {message && (
          <div className={`message ${message.includes('Ошибка') ? 'error' : 'success'}`}>
            {message}
          </div>
        )}
      </div>

      {Object.entries(data.abbreviations).map(([category, abbreviations]) => (
        <div key={category} className="card">
          <div className="category-header">
            <h3>{category}</h3>
            <button
              className="btn btn-secondary"
              onClick={() => handleAddAbbreviation(category)}
            >
              Добавить сокращение
            </button>
          </div>
          <div className="abbreviations-list">
            {Object.entries(abbreviations).map(([pattern, replacement]) => (
              <AbbreviationItem
                key={pattern}
                category={category}
                pattern={pattern}
                replacement={replacement}
                onUpdate={handleUpdateAbbreviation}
                onDelete={handleDeleteAbbreviation}
              />
            ))}
            {Object.keys(abbreviations).length === 0 && (
              <div className="empty-state">Нет сокращений в этой категории</div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};

interface AbbreviationItemProps {
  category: string;
  pattern: string;
  replacement: string;
  onUpdate: (category: string, oldPattern: string, newPattern: string, newReplacement: string) => void;
  onDelete: (category: string, pattern: string) => void;
}

const AbbreviationItem: React.FC<AbbreviationItemProps> = ({
  category,
  pattern,
  replacement,
  onUpdate,
  onDelete
}) => {
  const [editing, setEditing] = useState(false);
  const [editPattern, setEditPattern] = useState(pattern);
  const [editReplacement, setEditReplacement] = useState(replacement);

  const handleSave = () => {
    onUpdate(category, pattern, editPattern, editReplacement);
    setEditing(false);
  };

  const handleCancel = () => {
    setEditPattern(pattern);
    setEditReplacement(replacement);
    setEditing(false);
  };

  if (editing) {
    return (
      <div className="abbreviation-item editing">
        <input
          type="text"
          value={editPattern}
          onChange={(e) => setEditPattern(e.target.value)}
          placeholder="Паттерн (regex)"
        />
        <input
          type="text"
          value={editReplacement}
          onChange={(e) => setEditReplacement(e.target.value)}
          placeholder="Замена"
        />
        <button className="btn" onClick={handleSave}>Сохранить</button>
        <button className="btn btn-secondary" onClick={handleCancel}>Отмена</button>
      </div>
    );
  }

  return (
    <div className="abbreviation-item">
      <div className="abbreviation-content">
        <div className="abbreviation-pattern">{pattern}</div>
        <div className="abbreviation-arrow">→</div>
        <div className="abbreviation-replacement">{replacement}</div>
      </div>
      <div className="abbreviation-actions">
        <button className="btn btn-secondary" onClick={() => setEditing(true)}>
          Редактировать
        </button>
        <button className="btn btn-secondary" onClick={() => onDelete(category, pattern)}>
          Удалить
        </button>
      </div>
    </div>
  );
};

export default AbbreviationsEditor;

