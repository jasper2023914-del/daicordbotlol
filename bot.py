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

def _save_sword(name, value, demand):
    conn = _get_db()
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
        _release_db(conn)
    _refresh_cache()

def _update_image(name, image_url):
    conn = _get_db()
    try:
        cur = conn.cursor()
        cur.execute('UPDATE swords SET image_url = %s WHERE name = %s', (image_url, name))
        conn.commit()
        cur.close()
    finally:
        _release_db(conn)
    _refresh_cache()

def _update_value(name, value):
    conn = _get_db()
    try:
        cur = conn.cursor()
        cur.execute('UPDATE swords SET value = %s WHERE name = %s', (value, name))
        conn.commit()
        cur.close()
    finally:
        _release_db(conn)
    _refresh_cache()

def _update_demand(name, demand):
    conn = _get_db()
    try:
        cur = conn.cursor()
        cur.execute('UPDATE swords SET demand = %s WHERE name = %s', (demand, name))
        conn.commit()
        cur.close()
    finally:
        _release_db(conn)
    _refresh_cache()

def _delete_sword(name):
    conn = _get_db()
    try:
        cur = conn.cursor()
        cur.execute('DELETE FROM swords WHERE name = %s', (name,))
        conn.commit()
        cur.close()
    finally:
        _release_db(conn)
    _refresh_cache()

async def run_db(func, *args):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, func, *args)

async def log_action(interaction: discord.Interaction, description: str):
    channel = interaction.client.get_channel(LOG_CHANNEL_ID)
    if channel is None:
        return
    user = interaction.user
    embed = discord.Embed(
        title="Action Log",
        description=description,
        color=discord.Color.blurple()
    )
    embed.set_author(name=str(user), icon_url=user.display_avatar.url)
    embed.add_field(name="User", value=f"{user.mention} (`{user.id}`)", inline=True)
    embed.add_field(name="Channel", value=f"<#{interaction.channel_id}>", inline=True)
    import datetime
    embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
    await channel.send(embed=embed)

def has_value_adjuster_or_admin(interaction: discord.Interaction) -> bool:
    member = interaction.user
    if not isinstance(member, discord.Member):
        return False
    if member.guild_permissions.administrator:
        return True
    return any(role.name.lower() == VALUE_ADJUSTER_ROLE for role in member.roles)

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

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    if isinstance(error, discord.app_commands.CheckFailure):
        await interaction.response.send_message(
            "You don't have permission to use this command.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"An error occurred: {error}",
            ephemeral=True
        )

async def item_name_autocomplete(interaction: discord.Interaction, current: str):
    return [
        discord.app_commands.Choice(name=item, value=item)
        for item in sword_cache
        if current.lower() in item.lower()
    ][:25]

@bot.tree.command(name="setitem", description="Add or update a sword (Value Adjuster or Admin only)")
@discord.app_commands.check(has_value_adjuster_or_admin)
@discord.app_commands.describe(item_name="Name of the sword", value="Value of the sword", demand="Demand level")
@discord.app_commands.autocomplete(item_name=item_name_autocomplete)
async def setitem(interaction: discord.Interaction, item_name: str, value: str, demand: str):
    await interaction.response.defer(ephemeral=True)
    try:
        await run_db(_save_sword, item_name, value, demand)
        await interaction.followup.send(f"'{item_name}' has been set/updated!")
        await log_action(interaction, f"**`/setitem`** — Set/updated **{item_name}**\nValue: `{value}` | Demand: `{demand}`")
    except Exception as e:
        await interaction.followup.send(f"Error saving '{item_name}': {e}")

@bot.tree.command(name="setimage", description="Set the image for an existing sword (Value Adjuster or Admin only)")
@discord.app_commands.check(has_value_adjuster_or_admin)
@discord.app_commands.describe(sword_name="Name of the sword", image_url="Image URL")
@discord.app_commands.autocomplete(sword_name=item_name_autocomplete)
async def setimage(interaction: discord.Interaction, sword_name: str, image_url: str):
    await interaction.response.defer(ephemeral=True)
    if sword_name not in sword_cache:
        await interaction.followup.send(f"No sword found named '{sword_name}'")
        return
    try:
        await run_db(_update_image, sword_name, image_url)
        await interaction.followup.send(f"Image updated for '{sword_name}'!")
        await log_action(interaction, f"**`/setimage`** — Updated image for **{sword_name}**\nURL: `{image_url}`")
    except Exception as e:
        await interaction.followup.send(f"Error updating image: {e}")

@bot.tree.command(name="updatevalue", description="Update the value of an existing sword (Value Adjuster or Admin only)")
@discord.app_commands.check(has_value_adjuster_or_admin)
@discord.app_commands.describe(sword_name="Name of the sword", value="New value")
@discord.app_commands.autocomplete(sword_name=item_name_autocomplete)
async def updatevalue(interaction: discord.Interaction, sword_name: str, value: str):
    await interaction.response.defer(ephemeral=True)
    if sword_name not in sword_cache:
        await interaction.followup.send(f"No sword found named '{sword_name}'")
        return
    try:
        await run_db(_update_value, sword_name, value)
        await interaction.followup.send(f"Value updated for '{sword_name}' to {value}!")
        await log_action(interaction, f"**`/updatevalue`** — Updated value for **{sword_name}**\nNew Value: `{value}`")
    except Exception as e:
        await interaction.followup.send(f"Error updating value: {e}")

@bot.tree.command(name="updatedemand", description="Update the demand of an existing sword (Value Adjuster or Admin only)")
@discord.app_commands.check(has_value_adjuster_or_admin)
@discord.app_commands.describe(sword_name="Name of the sword", demand="New demand level")
@discord.app_commands.autocomplete(sword_name=item_name_autocomplete)
async def updatedemand(interaction: discord.Interaction, sword_name: str, demand: str):
    await interaction.response.defer(ephemeral=True)
    if sword_name not in sword_cache:
        await interaction.followup.send(f"No sword found named '{sword_name}'")
        return
    try:
        await run_db(_update_demand, sword_name, demand)
        await interaction.followup.send(f"Demand updated for '{sword_name}' to {demand}!")
        await log_action(interaction, f"**`/updatedemand`** — Updated demand for **{sword_name}**\nNew Demand: `{demand}`")
    except Exception as e:
        await interaction.followup.send(f"Error updating demand: {e}")

@bot.tree.command(name="deletesword", description="Delete a sword and all its data (Value Adjuster or Admin only)")
@discord.app_commands.check(has_value_adjuster_or_admin)
@discord.app_commands.describe(sword_name="Name of the sword to delete")
@discord.app_commands.autocomplete(sword_name=item_name_autocomplete)
async def deletesword(interaction: discord.Interaction, sword_name: str):
    await interaction.response.defer(ephemeral=True)
    if sword_name not in sword_cache:
        await interaction.followup.send(f"No sword found named '{sword_name}'")
        return
    try:
        await run_db(_delete_sword, sword_name)
        await interaction.followup.send(f"'{sword_name}' has been deleted!")
        await log_action(interaction, f"**`/deletesword`** — Deleted **{sword_name}**")
    except Exception as e:
        await interaction.followup.send(f"Error deleting '{sword_name}': {e}")

@bot.tree.command(name="sword", description="View info of an item")
@discord.app_commands.describe(sword_name="Name of the item")
@discord.app_commands.autocomplete(sword_name=item_name_autocomplete)
async def sword(interaction: discord.Interaction, sword_name: str):
    try:
        data = sword_cache.get(sword_name)
        if not data:
            await interaction.response.send_message(f"No data found for '{sword_name}'")
            return
        embed = discord.Embed(title=f"{sword_name} Info")
        embed.add_field(name="Value", value=data['value'] or "N/A", inline=True)
        embed.add_field(name="Demand", value=data['demand'] or "N/A", inline=True)
        if data['image_url']:
            embed.set_image(url=data['image_url'])
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"Error fetching '{sword_name}': {e}")

token = os.environ.get('DISCORD_TOKEN')
if not token:
    raise ValueError("DISCORD_TOKEN environment variable is not set!")

bot.run(token)
