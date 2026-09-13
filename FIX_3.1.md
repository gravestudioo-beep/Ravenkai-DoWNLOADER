# v3.1 hotfix — startup SQLite fix

The startup crash:

`ValueError: no active connection`

was caused by awaiting the `aiosqlite.connect()` coroutine before entering `async with`, which starts the connection worker and then tries to start it again.

The connection helper returns the connection object directly, and callers use:

```python
async with connect() as db:
    ...
```

This lets `aiosqlite` start the connection exactly once.

All database call sites in `bot/database.py` were updated accordingly.
