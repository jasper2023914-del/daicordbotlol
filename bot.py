import discord
from discord.ext import commands
import os
import psycopg2
from psycopg2.extras import RealDictCursor

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

def update_sword_image(name, image_url):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('UPDATE swords SET image_url = %s WHERE name = %s', (image_url, name))
    conn.commit()
    cur.close()
    conn.close()

def update_sword_value(name, value):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('UPDATE swords SET value = %s WHERE name = %s', (value, name))
    conn.commit()
    cur.close()
    conn.close()

def update_sword_demand(name, demand):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('UPDATE swords SET demand = %s WHERE name = %s', (demand, name))
    conn.commit()
    cur.close()
    conn.close()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_ready():
    init_db()
    print(f'Logged in as {bot.user}')
    await bot.tree.sync()
    print("Slash commands synced!")

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

@bot.tree.command(name="setimage", description="Set the image for an existing sword (Admin only)")
@discord.app_commands.default_permissions(administrator=True)
@discord.app_commands.describe(sword_name="Name of the sword", image_url="Image URL")
@discord.app_commands.autocomplete(sword_name=item_name_autocomplete)
async def setimage(interaction: discord.Interaction, sword_name: str, image_url: str):
    data = get_sword(sword_name)
    if not data:
        await interaction.response.send_message(f"No sword found named '{sword_name}'")
        return
    update_sword_image(sword_name, image_url)
    await interaction.response.send_message(f"Image updated for '{sword_name}'!")

@bot.tree.command(name="updatevalue", description="Update the value of an existing sword (Admin only)")
@discord.app_commands.default_permissions(administrator=True)
@discord.app_commands.describe(sword_name="Name of the sword", value="New value")
@discord.app_commands.autocomplete(sword_name=item_name_autocomplete)
async def updatevalue(interaction: discord.Interaction, sword_name: str, value: str):
    data = get_sword(sword_name)
    if not data:
        await interaction.response.send_message(f"No sword found named '{sword_name}'")
        return
    update_sword_value(sword_name, value)
    await interaction.response.send_message(f"Value updated for '{sword_name}' to {value}!")

@bot.tree.command(name="updatedemand", description="Update the demand of an existing sword (Admin only)")
@discord.app_commands.default_permissions(administrator=True)
@discord.app_commands.describe(sword_name="Name of the sword", demand="New demand level")
@discord.app_commands.autocomplete(sword_name=item_name_autocomplete)
async def updatedemand(interaction: discord.Interaction, sword_name: str, demand: str):
    data = get_sword(sword_name)
    if not data:
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
