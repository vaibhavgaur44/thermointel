import asyncio
from core.database import get_db

async def main():
    db = get_db()
    print(await db.list_collection_names())

asyncio.run(main())
