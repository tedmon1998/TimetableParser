import React, { useState, useEffect } from 'react';
import { api, FileInfo, TimetableEntry } from '../api';
import './FileViewer.css';

const FileViewer: React.FC = () => {
  const [fileType, setFileType] = useState<'json' | 'parsed'>('json');
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [data, setData] = useState<TimetableEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    loadFiles();
  }, [fileType]);

  const loadFiles = async () => {
    try {
      const response = await api.getFiles(fileType);
      setFiles(response.data);
    } catch (error) {
      console.error('Error loading files:', error);
    }
  };

  const loadFileData = async (filename: string) => {
    setLoading(true);
    setSelectedFile(filename);
    try {
      const response = await api.getFile(filename, fileType);
      setData(response.data);
    } catch (error) {
      console.error('Error loading file data:', error);
      setData([]);
    } finally {
      setLoading(false);
    }
  };

  const filteredData = data.filter(entry =>
    Object.values(entry).some(value =>
      String(value).toLowerCase().includes(searchTerm.toLowerCase())
    )
  );

  const formatDate = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleString('ru-RU');
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  return (
    <div className="file-viewer">
      <div className="card">
        <h2>Просмотр файлов</h2>
        <div className="file-type-selector">
          <button
            className={fileType === 'json' ? 'active' : ''}
            onClick={() => setFileType('json')}
          >
            Распарсенные
          </button>
          <button
            className={fileType === 'parsed' ? 'active' : ''}
            onClick={() => setFileType('parsed')}
          >
            Нормализованные
          </button>
        </div>
      </div>

      <div className="file-viewer-content">
        <div className="file-list">
          <div className="card">
            <h3>Файлы ({files.length})</h3>
            <div className="file-list-items">
              {files.map((file) => (
                <div
                  key={file.name}
                  className={`file-item ${selectedFile === file.name ? 'active' : ''}`}
                  onClick={() => loadFileData(file.name)}
                >
                  <div className="file-name">{file.name}</div>
                  <div className="file-meta">
                    {formatSize(file.size)} • {formatDate(file.modified)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="file-data">
          {selectedFile && (
            <div className="card">
              <h3>{selectedFile}</h3>
              {loading ? (
                <div className="loading">Загрузка...</div>
              ) : (
                <>
                  <div className="search-box">
                    <input
                      type="text"
                      placeholder="Поиск..."
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                    />
                    <span className="results-count">
                      Показано: {filteredData.length} из {data.length}
                    </span>
                  </div>
                  <div className="table-container">
                    <table>
                      <thead>
                        <tr>
                          <th>Дисциплина</th>
                          <th>Группа</th>
                          <th>День</th>
                          <th>Пара</th>
                          <th>Аудитория</th>
                          <th>Институт</th>
                          <th>Специальность</th>
                          <th>Курс</th>
                          <th>Недели</th>
                          <th>Подгруппа</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredData.map((entry, index) => (
                          <tr key={index}>
                            <td>{entry.discipline}</td>
                            <td>{entry.group}</td>
                            <td>{entry.day_of_week}</td>
                            <td>{entry.period}</td>
                            <td>{entry.room}</td>
                            <td>{entry.institute}</td>
                            <td>{entry.specialty}</td>
                            <td>{entry.course}</td>
                            <td>
                              {entry.even_week && entry.odd_week
                                ? 'Ч/Н'
                                : entry.even_week
                                ? 'Ч'
                                : entry.odd_week
                                ? 'Н'
                                : 'Все'}
                            </td>
                            <td>{entry.subgroup || '-'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default FileViewer;

