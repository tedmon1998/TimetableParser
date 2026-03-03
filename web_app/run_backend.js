#!/usr/bin/env node
const { spawn } = require('child_process');
const path = require('path');

const py = process.platform === 'win32' ? 'python' : 'python3';
const backendDir = path.join(__dirname, 'backend');
const child = spawn(py, ['app.py'], {
  cwd: backendDir,
  stdio: 'inherit',
  shell: process.platform === 'win32',
});

child.on('exit', (code, signal) => {
  process.exit(code ?? (signal ? 1 : 0));
});
