import discord
from discord.ext import commands, tasks
import requests
import random
from datetime import datetime, timedelta
from flask import Flask
import threading

# Bot configuration
TOKEN = 'DISCORD TOKEN'
POLITICS_AND_WAR_API_KEY = 'API KEY'
VERIFIED_ROLE_NAME = 'Verified'  # Role that allows users to interact with the bot

# Initialize the bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='$', intents=intents)

# In-memory database (you can replace this with a persistent database)
balances = {}
user_nations = {}
pending_trades = {}
verification_trades = {}

# Flask app for keeping the bot alive
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    app.run(host='0.0.0.0', port=5000)

# Helper functions to interact with Politics and War API
def send_trade_offer(nation_id, amount, resource):
    api_endpoint = "https://politicsandwar.com/api/trade/create/"
    payload = {
        'key': POLITICS_AND_WAR_API_KEY,
        'nation_id': nation_id,
        'amount': amount,
        'resource': resource
    }
    
    response = requests.post(api_endpoint, data=payload)
    return response.json()

def check_trade_status(trade_id):
    api_endpoint = f"https://politicsandwar.com/api/trade/{trade_id}/"
    params = {'key': POLITICS_AND_WAR_API_KEY}
    
    response = requests.get(api_endpoint, params=params)
    return response.json()

def cancel_trade_offer(trade_id):
    api_endpoint = f"https://politicsandwar.com/api/trade/{trade_id}/delete/"
    params = {'key': POLITICS_AND_WAR_API_KEY}
    
    response = requests.get(api_endpoint, params=params)
    return response.json()

def check_naval_blockade(nation_id):
    api_endpoint = f"https://politicsandwar.com/api/nation/id={nation_id}"
    params = {'key': POLITICS_AND_WAR_API_KEY}
    
    response = requests.get(api_endpoint, params=params)
    nation_data = response.json()
    
    return nation_data.get('success') and nation_data['nation'].get('blockaded')

def update_balance(user_id, amount, resource, operation):
    if user_id not in balances:
        balances[user_id] = {}
    if resource not in balances[user_id]:
        balances[user_id][resource] = 0
    
    if operation == 'deposit':
        balances[user_id][resource] += amount
    elif operation == 'withdraw':
        if balances[user_id][resource] >= amount:
            balances[user_id][resource] -= amount
        else:
            return False  # Insufficient balance
    
    return True

# Check if user has the verified role
def is_verified(ctx):
    role = discord.utils.get(ctx.guild.roles, name=VERIFIED_ROLE_NAME)
    return role in ctx.author.roles

# Background task to check pending trades
@tasks.loop(minutes=1)
async def check_pending_trades():
    now = datetime.utcnow()
    to_remove = []
    for trade_id, trade_info in pending_trades.items():
        if now >= trade_info['timestamp'] + timedelta(minutes=5):
            trade_status = check_trade_status(trade_id)
            if trade_status.get('success') and trade_status.get('status') == 'accepted':
                update_balance(trade_info['user_id'], trade_info['amount'], trade_info['resource'], 'deposit')
                user = bot.get_user(trade_info['user_id'])
                await user.send("Trade offer accepted. Balance updated.")
            else:
                cancel_trade_offer(trade_id)
                user = bot.get_user(trade_info['user_id'])
                await user.send("Trade offer not accepted within 5 minutes. Trade offer canceled.")
            to_remove.append(trade_id)
    
    for trade_id in to_remove:
        pending_trades.pop(trade_id)

# Commands
@bot.command(help="Link your Discord account with a nation ID: $link (nation id)")
async def link(ctx, nation_id: int):
    user_id = str(ctx.author.id)
    if user_id in user_nations:
        await ctx.send("You are already linked to a nation. Use $unlink first if you want to change.")
        return
    
    # Send a trade offer for food with a random amount between 1 and 10
    amount = random.randint(1, 10)
    trade_response = send_trade_offer(nation_id, amount, 'food')
    
    if trade_response.get('success'):
        trade_id = trade_response['trade_id']
        verification_trades[user_id] = {
            'nation_id': nation_id,
            'amount': amount,
            'trade_id': trade_id,
            'timestamp': datetime.utcnow()
        }
        await ctx.send(f"Trade offer has been sent. Please accept the trade offer for {amount} food, then use the command ${amount} to complete verification.")
    else:
        await ctx.send("Error sending trade offer. Contact an admin.")

@bot.command(help="Complete verification after accepting trade offer: $[amount]")
async def verify(ctx, amount: int):
    user_id = str(ctx.author.id)
    if user_id not in verification_trades:
        await ctx.send("No pending verification trade found. Use $link (nation id) to start verification.")
        return
    
    trade_info = verification_trades[user_id]
    if amount == trade_info['amount']:
        role = discord.utils.get(ctx.guild.roles, name=VERIFIED_ROLE_NAME)
        if role:
            await ctx.author.add_roles(role)
            user_nations[user_id] = trade_info['nation_id']
            await ctx.send(f"Verification successful. You have been given the {VERIFIED_ROLE_NAME} role.")
            verification_trades.pop(user_id)
        else:
            await ctx.send(f"The {VERIFIED_ROLE_NAME} role does not exist. Please contact an admin.")
    else:
        await ctx.send("Verification failed. Incorrect amount. Please try again or contact an admin.")

@bot.command(help="Unlink your Discord account from a nation ID: $unlink")
async def unlink(ctx):
    user_id = str(ctx.author.id)
    if user_id in user_nations:
        user_nations.pop(user_id)
        await ctx.send("Your account has been unlinked from the nation ID.")
    else:
        await ctx.send("Your account is not linked to any nation ID.")

@bot.command(help="Deposit resources to your nation's bank: $deposit (amount) (resource)")
async def deposit(ctx, amount: int, resource: str):
    if not is_verified(ctx):
        await ctx.send("You need to verify your account using $link (nation id) before using this command.")
        return
    
    user_id = str(ctx.author.id)
    nation_id = user_nations.get(user_id)
    
    if not nation_id:
        await ctx.send("Your account is not linked with any nation. Please use $link (nation id) to link your account.")
        return
    
    # Send trade offer
    trade_response = send_trade_offer(nation_id, amount, resource)
    
    if trade_response.get('success'):
        trade_id = trade_response['trade_id']
        pending_trades[trade_id] = {
            'user_id': user_id,
            'amount': amount,
            'resource': resource,
            'timestamp': datetime.utcnow()
        }
        await ctx.send("Trade offer has been sent. You have 5 minutes to accept the trade offer before it is canceled.")
    else:
        await ctx.send("Error sending trade offer. Contact an admin.")

@bot.command(help="Withdraw resources from your nation's bank: $withdraw (amount) (resource)")
async def withdraw(ctx, amount: int, resource: str):
    if not is_verified(ctx):
        await ctx.send("You need to verify your account using $link (nation id) before using this command.")
        return
    
    user_id = str(ctx.author.id)
    nation_id = user_nations.get(user_id)
    
    if not nation_id:
        await ctx.send("Your account is not linked with any nation. Please use $link (nation id) to link your account.")
        return
    
    if check_naval_blockade(nation_id):
        await ctx.send("Your nation is currently under a naval blockade. Withdrawal not processed.")
        return
    
    if user_id in balances and resource in balances[user_id] and balances[user_id][resource] >= amount:
        if update_balance(user_id, amount, resource, 'withdraw'):
            await ctx.send("Withdrawal successful. Balance updated.")
        else:
            await ctx.send("Error updating balance. Contact an admin.")
    else:
        await ctx.send("Insufficient balance. Withdrawal not processed.")

@bot.command(help="Check your balance: $balance")
async def balance(ctx):
    if not is_verified(ctx):
        await ctx.send("You need to verify your account using $link (nation id) before using this command.")
        return
    
    user_id = str(ctx.author.id)
    user_balance = balances.get(user_id, {})
    
    balance_details = {
        'Money': user_balance.get('Money', 0),
        'Food': user_balance.get('Food', 0),
        'Coal': user_balance.get('Coal', 0),
        'Oil': user_balance.get('Oil', 0),
        'Uranium': user_balance.get('Uranium', 0),
        'Lead': user_balance.get('Lead', 0),
        'Iron': user_balance.get('Iron', 0),
        'Bauxite': user_balance.get('Bauxite', 0),
        'Gasoline': user_balance.get('Gasoline', 0),
        'Munitions': user_balance.get('Munitions', 0),
        'Steel': user_balance.get('Steel', 0),
        'Aluminum': user_balance.get('Aluminum', 0),
    }
    
    balance_msg = "\n".join([f"{res}: {amt}" for res, amt in balance_details.items()])

    embed = discord.Embed(
        title=f"Balance of {ctx.author.display_name}",
        description=balance_msg,
        colour=0x00f510,
        timestamp=datetime.now()
    )

    embed.set_footer(text="Made By AyeSea")

    await ctx.send(embed=embed)

@bot.command(help="Admin command: Check the balance of a user: $check_balance @DiscordUser")
@commands.has_role('Admin')  # Replace 'Admin' with the appropriate role name
async def check_balance(ctx, member: discord.Member):
    user_id = str(member.id)
    user_balance = balances.get(user_id, {})
    
    balance_details = {
        'Money': user_balance.get('Money', 0),
        'Food': user_balance.get('Food', 0),
        'Coal': user_balance.get('Coal', 0),
        'Oil': user_balance.get('Oil', 0),
        'Uranium': user_balance.get('Uranium', 0),
        'Lead': user_balance.get('Lead', 0),
        'Iron': user_balance.get('Iron', 0),
        'Bauxite': user_balance.get('Bauxite', 0),
        'Gasoline': user_balance.get('Gasoline', 0),
        'Munitions': user_balance.get('Munitions', 0),
        'Steel': user_balance.get('Steel', 0),
        'Aluminum': user_balance.get('Aluminum', 0),
    }
    
    balance_msg = "\n".join([f"{res}: {amt}" for res, amt in balance_details.items()])

    embed = discord.Embed(
        title=f"Balance of {member.display_name}",
        description=balance_msg,
        colour=0x00f510,
        timestamp=datetime.now()
    )

    embed.set_footer(text="Made By AyeSea")

    await ctx.send(embed=embed)

@bot.command(help="Admin command: Add resources to a user's balance: $add @DiscordUser (amount) (resource)")
@commands.has_role('Admin')  # Replace 'Admin' with the appropriate role name
async def add(ctx, member: discord.Member, amount: int, resource: str):
    user_id = str(member.id)
    
    if update_balance(user_id, amount, resource, 'deposit'):
        await ctx.send(f"Added {amount} {resource} to {member.mention}'s balance.")
    else:
        await ctx.send("Error updating balance. Contact an admin.")

@bot.command(help="Admin command: Remove resources from a user's balance: $remove @DiscordUser (amount) (resource)")
@commands.has_role('Admin')  # Replace 'Admin' with the appropriate role name
async def remove(ctx, member: discord.Member, amount: int, resource: str):
    user_id = str(member.id)
    
    if user_id in balances and resource in balances[user_id] and balances[user_id][resource] >= amount:
        if update_balance(user_id, amount, resource, 'withdraw'):
            await ctx.send(f"Removed {amount} {resource} from {member.mention}'s balance.")
        else:
            await ctx.send("Error updating balance. Contact an admin.")
    else:
        await ctx.send(f"Insufficient balance for {member.mention}. Removal not processed.")

@bot.command(help="Transfer resources to another user: $transfer @DiscordUser (amount) (resource)")
async def transfer(ctx, member: discord.Member, amount: int, resource: str):
    if not is_verified(ctx):
        await ctx.send("You need to verify your account using $link (nation id) before using this command.")
        return
    
    user_id = str(ctx.author.id)
    recipient_id = str(member.id)
    
    if user_id not in balances or resource not in balances[user_id] or balances[user_id][resource] < amount:
        await ctx.send("Insufficient balance. Transfer not processed.")
        return
    
    if update_balance(user_id, amount, resource, 'withdraw') and update_balance(recipient_id, amount, resource, 'deposit'):
        await ctx.send("Transfer success. Balances updated.")
    else:
        await ctx.send("Error processing transfer. Contact an admin.")

@bot.command(help="Show all commands and their descriptions: $cmds")
async def cmds(ctx):
    embed = discord.Embed(
        title="Command List",
        description="Here are the available commands:",
        colour=0x00f510,
        timestamp=datetime.now()
    )
    
    for command in bot.commands:
        embed.add_field(name=f"${command}", value=command.help, inline=False)
    
    embed.set_footer(text="Made By AyeSea")
    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game(name="$Banking$"), status=discord.Status.online)
    print(f'Logged in as {bot.user.name} - {bot.user.id}')

# Run the bot
check_pending_trades.start()
flask_thread = threading.Thread(target=run_flask)
flask_thread.start()
bot.run(TOKEN)

