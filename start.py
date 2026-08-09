"""
绕过uvicorn的_multiprocessing DLL依赖启动服务器
"""
import multiprocessing

# Monkey-patch: 禁用allow_connection_pickling以避免加载_multiprocessing DLL
# 必须在import uvicorn之前执行
def _noop():
    pass

multiprocessing.allow_connection_pickling = _noop

# 现在安全导入uvicorn（不会触发_multiprocessing DLL加载）
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
