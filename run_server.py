"""
直接启动服务器 -- 绕过uvicorn的multiprocessing依赖
"""
import sys
import os

# 在uvicorn导入之前，先patch multiprocessing
import importlib
import types

# 创建一个最小化的multiprocessing mock来绕过DLL加载
_fake_mp = types.ModuleType("multiprocessing")


def _fake_allow_pickling():
    pass


_fake_mp.allow_connection_pickling = _fake_allow_pickling

# 也需要mock context子模块
_fake_context = types.ModuleType("multiprocessing.context")
_fake_context.SpawnProcess = type("SpawnProcess", (), {})
_fake_context.allow_connection_pickling = _fake_allow_pickling

# 还需要mock _subprocess需要的部分
_fake_mp.context = _fake_context
sys.modules["multiprocessing"] = _fake_mp
sys.modules["multiprocessing.context"] = _fake_context

# 现在可以安全导入uvicorn了
import asyncio
from uvicorn import Config, Server


async def main():
    config = Config(
        app="app.main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=False,
    )
    server = Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
