"""Python 3.8 兼容：asyncio.to_thread 在 3.9+ 才有。"""
from __future__ import annotations

import asyncio


def ensure_to_thread() -> None:
    if hasattr(asyncio, "to_thread"):
        return

    async def _to_thread_py38(func, /, *args, **kwargs):
        loop = asyncio.get_event_loop()
        if args or kwargs:
            import functools

            fn = functools.partial(func, *args, **kwargs)
        else:
            fn = func
        return await loop.run_in_executor(None, fn)

    asyncio.to_thread = _to_thread_py38  # type: ignore[attr-defined, assignment]
