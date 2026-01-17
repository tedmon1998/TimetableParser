import axios from 'axios';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:5000/api';

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
  
  getTaskStatus: (taskName: string) =>
    axios.get<TaskStatus>(`${API_BASE}/tasks/${taskName}/status`),
};

