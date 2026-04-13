import discord
from discord.ext import commands
import os
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool

sword_cache = {}
db_pool = None

VALUE_ADJUSTER_ROLE = "value adjuster"
LOG_CHANNEL_ID = 1490419697399890080

def _create_pool():
    return pool.ThreadedConnectionPool(1, 5, os.environ['DATABASE_URL'])

def _get_db():
    return db_pool.getconn()

def _release_db(conn):
    db_pool.putconn(conn)

def _refresh_cache():
    global sword_cache
    conn = _get_db()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('SELECT name, value, demand, image_url FROM swords')
        rows = cur.fetchall()
        cur.close()
        sword_cache = {
            row['name']: {
                'value': row['value'],
                'demand': row['demand'],
                'image_url': row['image_url'] or ''
            }
            for row in rows
        }
    finally:
        _release_db(conn)

def _init_db():
    conn = _get_db()
    try:
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS swords (
                name TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                demand TEXT NOT NULL,
                image_url TEXT DEFAULT ''
            )
        ''')
        conn.commit()
        cur.close()
    finally:
        _release_db(conn)
    _refresh_cache()

async def item_name_autocomplete(interaction: discord.Interaction, current: str):
    return [
        discord.app_commands.Choice(name=item, value=item)
        for item in sword_cache
        if current.lower() in item.lower()
    ][:25]

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_ready():
    global db_pool
    db_pool = _create_pool()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _init_db)
    print(f'Logged in as {bot.user}')
    await bot.tree.sync()
    print("Slash commands synced!")

DISABLED_MSG = "lmao this isnt gonna work anymore"

@bot.tree.command(name="setitem", description="Add or update a sword")
@discord.app_commands.describe(item_name="Name of the sword", value="Value of the sword", demand="Demand level")
@discord.app_commands.autocomplete(item_name=item_name_autocomplete)
async def setitem(interaction: discord.Interaction, item_name: str, value: str, demand: str):
    await interaction.response.send_message(DISABLED_MSG)

@bot.tree.command(name="setimage", description="Set the image for an existing sword")
@discord.app_commands.describe(sword_name="Name of the sword", image_url="Image URL")
@discord.app_commands.autocomplete(sword_name=item_name_autocomplete)
async def setimage(interaction: discord.Interaction, sword_name: str, image_url: str):
    await interaction.response.send_message(DISABLED_MSG)

@bot.tree.command(name="updatevalue", description="Update the value of an existing sword")
@discord.app_commands.describe(sword_name="Name of the sword", value="New value")
@discord.app_commands.autocomplete(sword_name=item_name_autocomplete)
async def updatevalue(interaction: discord.Interaction, sword_name: str, value: str):
    await interaction.response.send_message(DISABLED_MSG)

@bot.tree.command(name="updatedemand", description="Update the demand of an existing sword")
@discord.app_commands.describe(sword_name="Name of the sword", demand="New demand level")
@discord.app_commands.autocomplete(sword_name=item_name_autocomplete)
async def updatedemand(interaction: discord.Interaction, sword_name: str, demand: str):
    await interaction.response.send_message(DISABLED_MSG)

@bot.tree.command(name="deletesword", description="Delete a sword and all its data")
@discord.app_commands.describe(sword_name="Name of the sword to delete")
@discord.app_commands.autocomplete(sword_name=item_name_autocomplete)
async def deletesword(interaction: discord.Interaction, sword_name: str):
    await interaction.response.send_message(DISABLED_MSG)

@bot.tree.command(name="sword", description="View info of an item")
@discord.app_commands.describe(sword_name="Name of the item")
@discord.app_commands.autocomplete(sword_name=item_name_autocomplete)
async def sword(interaction: discord.Interaction, sword_name: str):
    await interaction.response.send_message(DISABLED_MSG)

token = os.environ.get('DISCORD_TOKEN')
if not token:
    raise ValueError("DISCORD_TOKEN environment variable is not set!")

bot.run(token)
