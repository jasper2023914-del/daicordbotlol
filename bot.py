import discord
from discord.ext import commands
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool

db_pool = pool.SimpleConnectionPool(1, 5, os.environ['DATABASE_URL'])

def get_db():
    return db_pool.getconn()

def release_db(conn):
    db_pool.putconn(conn)

sword_cache = {}

def refresh_cache():
    global sword_cache
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('SELECT name, value, demand, image_url FROM swords')
        rows = cur.fetchall()
        cur.close()
        sword_cache = {row['name']: {'value': row['value'], 'demand': row['demand'], 'image_url': row['image_url'] or ''} for row in rows}
    finally:
        release_db(conn)

def init_db():
    conn = get_db()
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
        release_db(conn)

def save_sword(name, value, demand):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO swords (name, value, demand, image_url)
            VALUES (%s, %s, %s, '')
            ON CONFLICT (name) DO UPDATE
            SET value = EXCLUDED.value,
                demand = EXCLUDED.demand
        ''', (name, value, demand))
        conn.commit()
        cur.close()
    finally:
        release_db(conn)
    refresh_cache()

def get_sword(name):
    return sword_cache.get(name)

def update_sword_image(name, image_url):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute('UPDATE swords SET image_url = %s WHERE name = %s', (image_url, name))
        conn.commit()
        cur.close()
    finally:
        release_db(conn)
    refresh_cache()

def update_sword_value(name, value):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute('UPDATE swords SET value = %s WHERE name = %s', (value, name))
        conn.commit()
        cur.close()
    finally:
        release_db(conn)
    refresh_cache()

def update_sword_demand(name, demand):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute('UPDATE swords SET demand = %s WHERE name = %s', (demand, name))
        conn.commit()
        cur.close()
    finally:
        release_db(conn)
    refresh_cache()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_ready():
    init_db()
    refresh_cache()
    print(f'Logged in as {bot.user}')
    await bot.tree.sync()
    print("Slash commands synced!")

async def item_name_autocomplete(interaction: discord.Interaction, current: str):
    return [
        discord.app_commands.Choice(name=item, value=item)
        for item in sword_cache
        if current.lower() in item.lower()
    ][:25]

@bot.tree.command(name="setitem", description="Add or update a sword (Admin only)")
@discord.app_commands.default_permissions(administrator=True)
@discord.app_commands.describe(item_name="Name of the sword", value="Value of the sword", demand="Demand level")
@discord.app_commands.autocomplete(item_name=item_name_autocomplete)
async def setitem(interaction: discord.Interaction, item_name: str, value: str, demand: str):
    save_sword(item_name, value, demand)
    await interaction.response.send_message(f"Item '{item_name}' has been set/updated!")

@bot.tree.command(name="setimage", description="Set the image for an existing sword (Admin only)")
@discord.app_commands.default_permissions(administrator=True)
@discord.app_commands.describe(sword_name="Name of the sword", image_url="Image URL")
@discord.app_commands.autocomplete(sword_name=item_name_autocomplete)
async def setimage(interaction: discord.Interaction, sword_name: str, image_url: str):
    if sword_name not in sword_cache:
        await interaction.response.send_message(f"No sword found named '{sword_name}'")
        return
    update_sword_image(sword_name, image_url)
    await interaction.response.send_message(f"Image updated for '{sword_name}'!")

@bot.tree.command(name="updatevalue", description="Update the value of an existing sword (Admin only)")
@discord.app_commands.default_permissions(administrator=True)
@discord.app_commands.describe(sword_name="Name of the sword", value="New value")
@discord.app_commands.autocomplete(sword_name=item_name_autocomplete)
async def updatevalue(interaction: discord.Interaction, sword_name: str, value: str):
    if sword_name not in sword_cache:
        await interaction.response.send_message(f"No sword found named '{sword_name}'")
        return
    update_sword_value(sword_name, value)
    await interaction.response.send_message(f"Value updated for '{sword_name}' to {value}!")

@bot.tree.command(name="updatedemand", description="Update the demand of an existing sword (Admin only)")
@discord.app_commands.default_permissions(administrator=True)
@discord.app_commands.describe(sword_name="Name of the sword", demand="New demand level")
@discord.app_commands.autocomplete(sword_name=item_name_autocomplete)
async def updatedemand(interaction: discord.Interaction, sword_name: str, demand: str):
    if sword_name not in sword_cache:
        await interaction.response.send_message(f"No sword found named '{sword_name}'")
        return
    update_sword_demand(sword_name, demand)
    await interaction.response.send_message(f"Demand updated for '{sword_name}' to {demand}!")

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

bot.run(token)
