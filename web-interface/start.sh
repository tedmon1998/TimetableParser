#!/bin/bash
# Скрипт для запуска веб-интерфейса

echo "Запуск веб-интерфейса для управления расписаниями"
echo "================================================"

# Проверяем наличие Python
if ! command -v python3 &> /dev/null; then
    echo "Ошибка: Python3 не установлен"
    exit 1
fi

# Проверяем наличие Node.js
if ! command -v node &> /dev/null; then
    echo "Ошибка: Node.js не установлен"
    exit 1
fi

# Устанавливаем зависимости backend
echo "Установка зависимостей backend..."
cd backend
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt > /dev/null 2>&1
cd ..

# Устанавливаем зависимости frontend
echo "Установка зависимостей frontend..."
cd frontend
if [ ! -d "node_modules" ]; then
    npm install
fi
cd ..

echo ""
echo "Запуск backend на http://localhost:5000"
cd backend
source venv/bin/activate
python3 app.py &
BACKEND_PID=$!
cd ..

sleep 2

echo "Запуск frontend на http://localhost:3000"
cd frontend
npm start &
FRONTEND_PID=$!
cd ..

echo ""
echo "Веб-интерфейс запущен!"
echo "Backend: http://localhost:5000"
echo "Frontend: http://localhost:3000"
echo ""
echo "Для остановки нажмите Ctrl+C"

# Ожидаем сигнала завершения
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait

