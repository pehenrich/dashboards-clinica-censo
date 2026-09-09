"""
Servico do Windows que mantem o backend (uvicorn) rodando de forma
independente da sessao/console que o iniciou. Usa pywin32.

Instalar (como Administrador):
    C:\\Python312\\python.exe service_dashboard.py --startup auto install
Iniciar/parar:
    C:\\Python312\\python.exe service_dashboard.py start
    C:\\Python312\\python.exe service_dashboard.py stop
Remover:
    C:\\Python312\\python.exe service_dashboard.py remove
"""
import os
import subprocess

import win32event
import win32service
import win32serviceutil

BACKEND_DIR = r"C:\Dashboard\backend"
LOG_PATH = r"C:\Dashboard\backend_out.log"
PYTHON_EXE = r"C:\Python312\python.exe"


class DashboardService(win32serviceutil.ServiceFramework):
    _svc_name_ = "DashboardBackend"
    _svc_display_name_ = "ICDS Dashboard Backend"
    _svc_description_ = "FastAPI/uvicorn do Dashboard Clinica Censo (HTTPS :31000)"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.process = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self.process and self.process.poll() is None:
            self.process.terminate()
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        os.chdir(BACKEND_DIR)
        cmd = [
            PYTHON_EXE, "-m", "uvicorn", "main:app",
            "--host", "0.0.0.0", "--port", "31000",
            "--ssl-keyfile", "ssl/dashboard_ip.key",
            "--ssl-certfile", "ssl/dashboard_ip.crt",
            "--workers", "1",
        ]
        with open(LOG_PATH, "a", encoding="utf-8") as log:
            log.write("\n\n===== [service] iniciando backend =====\n")
            log.flush()
            self.process = subprocess.Popen(cmd, cwd=BACKEND_DIR, stdout=log, stderr=subprocess.STDOUT)
            win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)
            if self.process and self.process.poll() is None:
                self.process.terminate()
                self.process.wait(timeout=15)


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(DashboardService)
