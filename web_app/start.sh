#!/bin/bash

echo "Starting Парсер расписания Web Application..."
echo ""

# Проверяем наличие Python 3
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed or not in PATH"
    exit 1
fi

# Проверяем наличие Node.js
if ! command -v node &> /dev/null; then
    echo "Error: Node.js is not installed or not in PATH"
    exit 1
fi

# Запускаем backend в фоне
echo "Starting Backend..."
cd backend
python3 app.py &
BACKEND_PID=$!
cd ..

# Ждем немного перед запуском frontend
sleep 2

# Запускаем frontend в фоне
echo "Starting Frontend..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "Both servers are starting..."
echo "Backend: http://localhost:5001"
echo "Frontend: http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop both servers"

# Обработка сигнала завершения
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM

# Ждем завершения процессов
wait
