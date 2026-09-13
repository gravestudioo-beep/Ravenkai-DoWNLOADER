import asyncio
from bot.database import init_db

async def main():
    await init_db()
    print("SQLite init OK")

if __name__ == "__main__":
    asyncio.run(main())
