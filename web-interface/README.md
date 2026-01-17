# Веб-интерфейс для управления расписаниями

Веб-приложение на React + TypeScript для просмотра и управления расписаниями СурГУ.

## Структура

```
web-interface/
├── frontend/          # React + TypeScript приложение
├── backend/           # Python Flask API
└── README.md
```

## Установка

### Backend

```bash
cd backend
pip install -r requirements.txt
python app.py
```

Backend будет доступен на `http://localhost:5000`

### Frontend

```bash
cd frontend
npm install
npm start
```

Frontend будет доступен на `http://localhost:3000`

## Функциональность

### 1. Просмотр файлов
- Просмотр распарсенных JSON файлов
- Просмотр нормализованных JSON файлов
- Поиск по данным
- Таблица с фильтрацией

### 2. Управление задачами
- Запуск скачивания расписаний с сайта
- Запуск парсинга PDF файлов
- Запуск нормализации названий дисциплин
- Мониторинг статуса задач

### 3. Редактор сокращений
- Просмотр всех сокращений
- Добавление новых сокращений
- Редактирование существующих
- Удаление сокращений
- Сохранение изменений

## API Endpoints

- `GET /api/status` - статус сервера и статистика
- `GET /api/files?type=json|parsed|pdf` - список файлов
- `GET /api/file/<filename>?type=json|parsed|pdf` - содержимое файла
- `GET /api/abbreviations` - получить сокращения
- `POST /api/abbreviations` - сохранить сокращения
- `POST /api/tasks/download` - запустить скачивание
- `POST /api/tasks/parse` - запустить парсинг
- `POST /api/tasks/normalize` - запустить нормализацию
- `GET /api/tasks/<task_name>/status` - статус задачи

