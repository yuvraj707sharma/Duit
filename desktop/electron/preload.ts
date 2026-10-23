import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electronAPI', {
  triggerKillSwitch: () => ipcRenderer.invoke('trigger-kill-switch'),
  resetKillSwitch: () => ipcRenderer.invoke('reset-kill-switch'),
  toggleSidebar: (isExpanded: boolean) => ipcRenderer.invoke('toggle-sidebar', isExpanded),
  onKillSwitchActivated: (callback: () => void) => {
    ipcRenderer.on('kill-switch-activated', () => callback());
  }
});
