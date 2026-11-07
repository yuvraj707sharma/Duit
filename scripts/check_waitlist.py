import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect(
        'postgresql://duit_user:cywesx9wSvcBC8hQ4Yc8afhWnbrh3EhV@dpg-dbncp715efls73avoadg-a.singapore-postgres.render.com/duit',
        ssl='require'
    )
    rows = await conn.fetch('SELECT email, phone_number, status, created_at FROM beta_registrations ORDER BY created_at DESC')
    print("=== LIVE BETA WAITLIST ENTRIES ===")
    print(f"Total count: {len(rows)}")
    for r in rows:
        print(f"Gmail: {r['email']}  |  WhatsApp: {r['phone_number']}  |  Status: {r['status']}  |  Registered: {r['created_at']}")
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())

