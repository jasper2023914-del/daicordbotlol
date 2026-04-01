import discord
from discord.ext import commands, tasks
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return 'Bot is alive!'

def run_server():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_server)
    t.daemon = True
    t.start()

def get_db():
    return psycopg2.connect(os.environ['DATABASE_URL'])

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS swords (
            name TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            demand TEXT NOT NULL,
            image_url TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS bot_status (
            id SERIAL PRIMARY KEY,
            last_message_id TEXT
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()

def get_last_message_id():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT last_message_id FROM bot_status LIMIT 1')
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None

def save_last_message_id(message_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM bot_status')
    cur.execute('INSERT INTO bot_status (last_message_id) VALUES (%s)', (str(message_id),))
    conn.commit()
    cur.close()
    conn.close()

def get_all_swords():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT name, value, demand, image_url FROM swords')
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {row['name']: {'value': row['value'], 'demand': row['demand'], 'image_url': row['image_url']} for row in rows}

def save_sword(name, value, demand, image_url):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO swords (name, value, demand, image_url)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (name) DO UPDATE
        SET value = EXCLUDED.value,
            demand = EXCLUDED.demand,
            image_url = EXCLUDED.image_url
    ''', (name, value, demand, image_url))
    conn.commit()
    cur.close()
    conn.close()

def get_sword(name):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT value, demand, image_url FROM swords WHERE name = %s', (name,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

STATUS_CHANNEL_ID = int(os.environ.get('STATUS_CHANNEL_ID', 0))

@tasks.loop(hours=1)
async def send_status():
    if not STATUS_CHANNEL_ID:
        return
    channel = bot.get_channel(STATUS_CHANNEL_ID)
    if channel:
        msg = await channel.send('🟢 - ONLINE')
        save_last_message_id(msg.id)

@bot.event
async def on_ready():
    init_db()
    print(f'Logged in as {bot.user}')
    await bot.tree.sync()
    print("Slash commands synced!")

    if STATUS_CHANNEL_ID:
        channel = bot.get_channel(STATUS_CHANNEL_ID)
        if channel:
            last_id = get_last_message_id()
            if last_id:
                try:
                    old_msg = await channel.fetch_message(int(last_id))
                    await old_msg.edit(content='🔴 - OFFLINE (was down, now back)')
                except:
                    pass
            msg = await channel.send('🟢 - ONLINE')
            save_last_message_id(msg.id)

    send_status.start()

async def item_name_autocomplete(interaction: discord.Interaction, current: str):
    swords = get_all_swords()
    return [
        discord.app_commands.Choice(name=item, value=item)
        for item in swords
        if current.lower() in item.lower()
    ][:25]

@bot.tree.command(name="setitem", description="Set or update an item's info (Admin only)")
@discord.app_commands.default_permissions(administrator=True)
@discord.app_commands.describe(item_name="Name of the item", value="Value of the item", demand="Demand level", image_url="Image URL")
@discord.app_commands.autocomplete(item_name=item_name_autocomplete)
async def setitem(interaction: discord.Interaction, item_name: str, value: str, demand: str, image_url: str):
    save_sword(item_name, value, demand, image_url)
    await interaction.response.send_message(f"Item '{item_name}' has been set/updated!")

@bot.tree.command(name="sword", description="View info of an item")
@discord.app_commands.describe(sword_name="Name of the item")
@discord.app_commands.autocomplete(sword_name=item_name_autocomplete)
async def sword(interaction: discord.Interaction, sword_name: str):
    data = get_sword(sword_name)
    if not data:
        await interaction.response.send_message(f"No data found for '{sword_name}'")
        return
    embed = discord.Embed(title=f"{sword_name} Info")
    embed.add_field(name="Value", value=data['value'], inline=True)
    embed.add_field(name="Demand", value=data['demand'], inline=True)
    if data['image_url']:
        embed.set_image(url=data['image_url'])
    await interaction.response.send_message(embed=embed)

token = os.environ.get('DISCORD_TOKEN')
if not token:
    raise ValueError("DISCORD_TOKEN environment variable is not set!")

keep_alive()
bot.run(token)
