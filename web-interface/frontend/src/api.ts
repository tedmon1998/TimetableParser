import axios from 'axios';

// Используем полный URL
// Можно также использовать переменную окружения REACT_APP_API_URL
// Порт 5001, так как 5000 часто занят AirPlay Receiver на macOS
const API_BASE = process.env.REACT_APP_API_URL || 'http://127.0.0.1:5001/api';

// Перехватчик только для ошибок (не логируем успешные запросы)
axios.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    // Логируем только ошибки
    console.error('API Error:', error.response?.status, error.config?.url, error.message);
    return Promise.reject(error);
  }
);

export interface FileInfo {
  name: string;
  size: number;
  modified: number;
}

export interface TimetableEntry {
  discipline: string;
  group: string;
  day_of_week: string;
  room: string;
  period: number;
  institute: string;
  specialty: string;
  course: string;
  even_week: boolean;
  odd_week: boolean;
  subgroup: number | null;
  lesson_type?: string;
  period_dates?: string;
}

export interface TaskStatus {
  running: boolean;
  progress: number;
  message: string;
}

export interface Abbreviations {
  abbreviations: {
    [category: string]: {
      [pattern: string]: string;
    };
  };
  metadata: {
    version?: string;
    last_updated?: string;
    description?: string;
  };
}

export const api = {
  getStatus: () => axios.get(`${API_BASE}/status`),
  
  getFiles: (type: 'json' | 'parsed' | 'pdf') => 
    axios.get<FileInfo[]>(`${API_BASE}/files?type=${type}`),
  
  getFile: (filename: string, type: 'json' | 'parsed' | 'pdf') =>
    axios.get<TimetableEntry[]>(`${API_BASE}/file/${filename}?type=${type}`),
  
  getAbbreviations: () => axios.get<Abbreviations>(`${API_BASE}/abbreviations`),
  
  saveAbbreviations: (data: Abbreviations) =>
    axios.post(`${API_BASE}/abbreviations`, data),
  
  startDownload: () => axios.post(`${API_BASE}/tasks/download`),
  startParse: () => axios.post(`${API_BASE}/tasks/parse`),
  startNormalize: () => axios.post(`${API_BASE}/tasks/normalize`),
  
  stopTask: (taskName: string) =>
    axios.post(`${API_BASE}/tasks/${taskName}/stop`),
  
  getTaskStatus: (taskName: string) =>
    axios.get<TaskStatus>(`${API_BASE}/tasks/${taskName}/status`),
};

