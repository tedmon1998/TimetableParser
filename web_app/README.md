# Timetable Parser Web Application

Веб-интерфейс для управления парсингом расписания и работы с базой данных.

## Структура проекта

```
web_app/
├── backend/          # Flask API сервер
│   ├── app.py       # Основной файл API
│   └── requirements.txt
└── frontend/        # React TypeScript приложение (Vite)
    ├── src/
    │   ├── components/
    │   │   ├── ScriptRunner.tsx
    │   │   ├── DatabaseView.tsx
    │   ├── App.tsx
    │   └── index.tsx
    ├── index.html   # Точка входа (Vite)
    ├── vite.config.ts
    └── package.json
```

## Установка и запуск

### Быстрый старт (рекомендуется)

#### Вариант 1: Использование npm (кроссплатформенный)

1. Установите зависимости для всех компонентов:
```bash
cd web_app
npm install              # Установит concurrently для параллельного запуска
npm run install:all      # Установит зависимости для backend и frontend
```

2. Запустите оба сервера одновременно:
```bash
npm run dev
```

Это запустит backend и frontend с цветным выводом в консоли.

#### Вариант 2: Использование скриптов запуска

**Windows:**
```bash
cd web_app
start.bat
```

**Linux/Mac:**
```bash
cd web_app
chmod +x start.sh
./start.sh
```

Backend будет доступен на `http://localhost:5000`  
Frontend будет доступен на `http://localhost:3000`

### Отдельный запуск

#### Backend

1. Установите зависимости:
```bash
cd web_app/backend
pip install -r requirements.txt
```

2. Запустите сервер:
```bash
python app.py
```

Сервер будет доступен на `http://localhost:5000`

#### Frontend

1. Установите зависимости:
```bash
cd web_app/frontend
npm install
```

2. Запустите приложение:
```bash
npm run dev
```

Приложение будет доступно на `http://localhost:3000`

### Доступные команды

- `npm run dev` - Запустить backend и frontend одновременно (с цветным выводом)
- `npm run start:backend` - Запустить только backend
- `npm run start:frontend` - Запустить только frontend (Vite dev server)
- `npm run install:all` - Установить все зависимости
- `npm run install:backend` - Установить зависимости backend
- `npm run install:frontend` - Установить зависимости frontend
- `npm run build` - Собрать production версию frontend
- `npm run preview` - Предпросмотр production сборки frontend

## Функциональность

### Запуск скриптов

- **Парсинг расписания**: Запускает `parse_timetable_excel.py`
  - Автоматически удаляет старые файлы в `output/timetable`
  - Показывает прогресс выполнения
  - Отображает статус и ошибки

- **Очистка аудиторий**: Запускает `clean_audiences.py`
  - Автоматически удаляет старые cleaned файлы
  - Обновляет базу данных
  - Показывает прогресс выполнения

### Работа с базой данных

- **Статистика**: Показывает общее количество записей, распределение по дням недели и типам занятий
- **Просмотр записей**: Таблица с пагинацией для просмотра всех записей
- **Очистка БД**: Кнопка для полной очистки базы данных

## API Endpoints

### Скрипты

- `POST /api/run/parse_timetable` - Запустить парсинг расписания
- `POST /api/run/clean_audiences` - Запустить очистку аудиторий
- `GET /api/status/<script_name>` - Получить статус выполнения скрипта

### База данных

- `GET /api/db/stats` - Получить статистику БД
- `GET /api/db/records?page=1&limit=50` - Получить записи с пагинацией
- `POST /api/db/clear` - Очистить базу данных

## Примечания

- При запуске скриптов старые файлы автоматически удаляются
- База данных полностью обновляется при каждом запуске `clean_audiences.py`
- Прогресс обновляется в реальном времени каждые 500мс
