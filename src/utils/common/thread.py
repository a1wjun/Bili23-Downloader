import ctypes
import threading
from concurrent.futures import ThreadPoolExecutor

class Thread(threading.Thread):
    def __init__(self, target = None, args = (), kwargs = None, name = "", daemon = True):
        threading.Thread.__init__(self, target = target, args = args, kwargs = kwargs, name = name, daemon = daemon)
    
    def stop(self):
        # 使用 Python C API 强制停止线程
        ctypes.pythonapi.PyThreadState_SetAsyncExc(self.ident, ctypes.py_object(SystemExit))
    
    def start(self):
        threading.Thread.start(self)

class DaemonThreadPoolExecutor(ThreadPoolExecutor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._thread_factory = lambda: threading.Thread(daemon = True)