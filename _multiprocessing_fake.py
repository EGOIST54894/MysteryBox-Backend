"""
Fake _multiprocessing module to bypass WDAC DLL block.
Provides just enough symbols for uvicorn to work.
"""
# SemLock - needed by multiprocessing.synchronize
class SemLock:
    def __init__(self, kind, value, maxvalue, *args, **kwargs):
        self._kind = kind
        self._value = value
        self._maxvalue = maxvalue

    def _count(self):
        return 0

    def _is_zero(self):
        return True

    def _after_fork(self):
        pass

    @staticmethod
    def _rebuild(*args, **kwargs):
        return SemLock(0, 0, 0)

    def acquire(self, *args, **kwargs):
        return True

    def release(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


# Flags
SEM_VALUE_MAX = 2147483647


# win32 specific
def win32_CreateFile(*args, **kwargs):
    return 0


def win32_CloseHandle(*args, **kwargs):
    pass
