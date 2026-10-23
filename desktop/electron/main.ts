import { app, BrowserWindow, globalShortcut, ipcMain, screen } from 'electron';
import * as path from 'path';

let mainWindow: BrowserWindow | null = null;
let killSwitchTriggered = false;

function createWindow() {
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width, height } = primaryDisplay.workAreaSize;

  // Create frameless, transparent sidebar toggle widget window
  mainWindow = new BrowserWindow({
    width: 380,
    height: 600,
    x: width - 400,
    y: 80,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true
    }
  });

  if (process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL);
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  // Register Global Kill-Switch Hotkey (Ctrl+Shift+K / Cmd+Shift+K)
  globalShortcut.register('CommandOrControl+Shift+K', () => {
    killSwitchTriggered = true;
    console.warn('GLOBAL KILL-SWITCH HOTKEY PRESSED!');
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('kill-switch-activated');
    }
  });
}

app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});

// IPC Event Handlers
ipcMain.handle('trigger-kill-switch', () => {
  killSwitchTriggered = true;
  console.warn('Kill switch triggered from renderer UI');
  return { success: true, killSwitchActive: true };
});

ipcMain.handle('reset-kill-switch', () => {
  killSwitchTriggered = false;
  return { success: true, killSwitchActive: false };
});

ipcMain.handle('toggle-sidebar', (_event, isExpanded: boolean) => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    if (isExpanded) {
      mainWindow.setSize(380, 600);
    } else {
      mainWindow.setSize(80, 80);
    }
  }
  return true;
});
