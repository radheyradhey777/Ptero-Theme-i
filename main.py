import os
import discord
import google.generativeai as genai
from dotenv import load_dotenv
import asyncio
import logging
import re # Regular expressions for parsing user messages
from flask import Flask # Import Flask for the web server
from threading import Thread # Import Thread for running the web server in a separate thread

# --- 1. Logging Setup ---
# Sets up a basic logger to show informational messages and errors in the console.
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 2. Environment Variables Loading ---
# Loads sensitive keys from a .env file for security.
load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Error handling if the tokens are not found in the .env file.
if not DISCORD_BOT_TOKEN:
    logger.error("CRITICAL: DISCORD_BOT_TOKEN environment variable is not set. Please check your .env file.")
    exit(1)

if not GEMINI_API_KEY:
    logger.error("CRITICAL: GEMINI_API_KEY environment variable is not set. Please check your .env file.")
    exit(1)

logger.info("Environment variables loaded successfully.")

# --- 3. Gemini API Configuration ---
# Configures the Generative AI model from Google.
try:
    genai.configure(api_key=GEMINI_API_KEY)
    # Using 'gemini-1.5-flash' which is a fast and capable model for chat applications.
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
    logger.info("Gemini API configured successfully with 'gemini-1.5-flash' model.")
except Exception as e:
    logger.error(f"Error configuring Gemini API: {e}")
    logger.error("Please verify your GEMINI_API_KEY is correct and has not expired.")
    exit(1)

# --- 4. Discord Bot Client Setup ---
# Defines the bot's permissions (intents). It needs to read message content.
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

# --- ZTX Team Members' Discord Usernames (CASE-INSENSITIVE) ---
# IMPORTANT: Replace these with the actual Discord usernames (without the #tag) of your team.
# These must be in lowercase.
ZTX_TEAM_MEMBERS = [
    "bibek mondal",
    "jeteex",
    "akshay thakur",
    "progamer"
    # Add other lowercase Discord usernames here, e.g., "john.doe"
]

# --- Plan Data (Verified with ztxhosting.site on July 2024) ---

# Minecraft Plans
MINECRAFT_PLANS = [
    {"name": "Grass", "price": "₹100", "ram": 2, "cpu_percent": 100, "disk_gb": 5, "backup_slots": 1, "emoji": "🌱", "players_min": 2, "players_max": 10, "plugins": "Basic Plugins"},
    {"name": "Dirt", "price": "₹200", "ram": 4, "cpu_percent": 150, "disk_gb": 10, "backup_slots": 2, "emoji": "🟫", "players_min": 2, "players_max": 20, "plugins": "Basic Plugins"},
    {"name": "Stone", "price": "₹300", "ram": 6, "cpu_percent": 160, "disk_gb": 15, "backup_slots": 2, "emoji": "🪨", "players_min": 10, "players_max": 30, "plugins": "Essentials+"},
    {"name": "Wood", "price": "₹400", "ram": 8, "cpu_percent": 200, "disk_gb": 20, "backup_slots": 2, "emoji": "🪵", "players_min": 10, "players_max": 40, "plugins": "Essentials+"},
    {"name": "Iron", "price": "₹600", "ram": 12, "cpu_percent": 250, "disk_gb": 30, "backup_slots": 3, "emoji": "⚙️", "players_min": 25, "players_max": 60, "plugins": "Essentials+ & Dynmap"},
    {"name": "Gold", "price": "₹800", "ram": 16, "cpu_percent": 350, "disk_gb": 40, "backup_slots": 4, "emoji": "🟨", "players_min": 25, "players_max": 80, "plugins": "Premium Plugin Pack"},
    {"name": "Diamond", "price": "₹1300", "ram": 24, "cpu_percent": 450, "disk_gb": 50, "backup_slots": 8, "emoji": "💎", "players_min": 50, "players_max": 120, "plugins": "Premium + Anti-Lag"},
    {"name": "Netherite", "price": "₹1760", "ram": 32, "cpu_percent": 550, "disk_gb": 70, "backup_slots": 10, "emoji": "🔥", "players_min": 50, "players_max": 150, "plugins": "Full Plugin Suite"},
    {"name": "Bedrock", "price": "₹3500", "ram": 64, "cpu_percent": 950, "disk_gb": 100, "backup_slots": 10, "emoji": "🗿", "players_min": 200, "players_max": None, "plugins": "Bedrock + Java + Full Suite"}, # For 200+ players
]

# NEW: VPS Plans
VPS_PLANS = [
    {"name": "VPS-1", "price": "₹499", "cpu_cores": 2, "ram_gb": 4, "disk_gb": 60, "bandwidth_tb": 2, "emoji": "☁️"},
    {"name": "VPS-2", "price": "₹799", "cpu_cores": 4, "ram_gb": 8, "disk_gb": 100, "bandwidth_tb": 4, "emoji": "☁️"},
    {"name": "VPS-3", "price": "₹1499", "cpu_cores": 6, "ram_gb": 12, "disk_gb": 160, "bandwidth_tb": 6, "emoji": "☁️"},
    {"name": "VPS-4", "price": "₹1999", "cpu_cores": 8, "ram_gb": 16, "disk_gb": 240, "bandwidth_tb": 8, "emoji": "☁️"},
]

# NEW: Dedicated Server Plans
DEDICATED_PLANS = [
    {"name": "DS-1", "price": "₹3999", "cpu": "Ryzen 5 5600X", "cpu_details": "6 Cores / 12 Threads", "ram": "32 GB DDR4", "disk": "512 GB NVMe", "location": "Germany", "emoji": "🖥️"},
    {"name": "DS-2", "price": "₹5999", "cpu": "Ryzen 7 5700X", "cpu_details": "8 Cores / 16 Threads", "ram": "64 GB DDR4", "disk": "1 TB NVMe", "location": "Germany", "emoji": "🖥️"},
    {"name": "DS-3", "price": "₹7999", "cpu": "Ryzen 9 5900X", "cpu_details": "12 Cores / 24 Threads", "ram": "128 GB DDR4", "disk": "2 TB NVMe", "location": "Germany", "emoji": "🖥️"},
]


# --- 5. Bot Event Handlers ---

@client.event
async def on_ready():
    """This function runs when the bot successfully connects to Discord."""
    logger.info(f'Bot logged in as: {client.user.name} (ID: {client.user.id})')
    logger.info(f'Invite URL: https://discord.com/oauth2/authorize?client_id={client.user.id}&permissions=8&scope=bot')
    # Set a custom status for the bot
    await client.change_presence(activity=discord.Game(name="ZTX Hosting | !tips for help"))
    logger.info('Bot is ready and listening for commands.')


@client.event
async def on_message(message: discord.Message):
    """This function runs for every message sent in a channel the bot can see."""
    # Ignore messages sent by the bot itself to prevent loops.
    if message.author == client.user:
        return

    # Log message for debugging purposes.
    if isinstance(message.channel, discord.DMChannel):
        logger.info(f"Received DM from {message.author.name}: {message.content}")
    else:
        logger.info(f"Received message from {message.author.name} in #{message.channel.name}: {message.content}")

    user_prompt_lower = message.content.lower()
    user_prompt_for_ai = "" # This will hold the cleaned prompt for Gemini.

    # --- Command and Mention Processing ---
    # The bot will only respond if it's mentioned, or if a command is used.
    is_command = False
    if client.user.mentioned_in(message):
        # Extracts the question from a mention (e.g., "@Bot what are your plans?")
        user_prompt_for_ai = re.sub(r'<@!?\d+>', '', message.content).strip()
        if not user_prompt_for_ai:
            embed = discord.Embed(
                title="How can I help you?",
                description="Yes, I'm here to assist you. Feel free to ask me anything about ZTX Hosting! Try `!tips` for Minecraft server advice.",
                color=discord.Color.blue()
            )
            await message.channel.send(embed=embed)
            return
        is_command = True
        logger.info(f"Extracted prompt from mention: '{user_prompt_for_ai}'")
    elif user_prompt_lower.startswith("!ask ") or user_prompt_lower.startswith("!gemini ") or user_prompt_lower.startswith("!tips"):
        # Extracts the question from a command (e.g., "!ask what are your plans?")
        if user_prompt_lower.startswith('!ask '):
            user_prompt_for_ai = message.content[5:].strip()
        elif user_prompt_lower.startswith('!gemini '):
            user_prompt_for_ai = message.content[7:].strip()
        else: # Handles !tips
             user_prompt_for_ai = message.content[5:].strip() if len(message.content) > 5 else "general tips"


        is_command = True
        logger.info(f"Extracted prompt from command: '{user_prompt_for_ai}'")
    elif user_prompt_lower == "!ping":
        latency = round(client.latency * 1000)
        embed = discord.Embed(title="Pong! 🏓", description=f"My latency is {latency}ms.", color=discord.Color.green())
        await message.channel.send(embed=embed)
        logger.info(f"Responded to !ping from {message.author.name} with latency {latency}ms.")
        return # Exit after handling ping

    if not is_command:
        return # If it's not a command or mention, do nothing.

    user_prompt_lower = user_prompt_for_ai.lower() # Use the cleaned prompt for keyword checks

    # --- ZTX Hosting Specific Keyword Handling ---
    # This section provides hardcoded, instant answers for common questions.

    # NEW: Minecraft Server Tips (Plugins & Lag Fixes)
    tips_keywords = ["tips", "plugin", "lag fix", "lag", "optimize", "performance", "features"]
    if any(keyword in user_prompt_lower for keyword in tips_keywords):
        embed = discord.Embed(
            title="Minecraft Server Optimization & Plugin Tips 🛠️",
            description="Here are some essential tips for running a smooth and feature-rich Minecraft server.",
            color=discord.Color.orange()
        )
        embed.add_field(
            name="✅ Tip 1: Use Optimized Server Software",
            value="Don't use vanilla server software. Instead, use **PaperMC** or its forks like **Purpur**. They are highly optimized for performance and fix many of Mojang's inefficiencies, while still supporting all your favorite plugins.",
            inline=False
        )
        embed.add_field(
            name="📉 Tip 2: Reduce Server Lag",
            value=(
                "**- Adjust `view-distance`:** In `server.properties`, set `view-distance` to `6` or `7`. This has the biggest impact on performance.\n"
                "**- Pre-generate Your World:** Use a plugin like Chunky to pre-generate chunks so the server doesn't have to do it when players explore.\n"
                "**- Limit Entities:** Use plugins to clear excessive mobs or items on the ground. High entity counts are a major cause of lag.\n"
                "**- Choose the Right Plan:** Ensure your ZTX Hosting plan has enough RAM and CPU for your player count and plugins."
            ),
            inline=False
        )
        embed.add_field(
            name="💡 Tip 3: Must-Have Plugin Features",
            value=(
                "**- Essentials:** Use **EssentialsX** for basic commands like `/sethome`, `/spawn`, `/tpa`, and economy.\n"
                "**- Permissions:** **LuckPerms** is the standard for managing what commands and abilities different player ranks have.\n"
                "**- World Protection:** **WorldGuard** lets you protect your spawn and other important areas from griefing.\n"
                "**- Backups/Logging:** **CoreProtect** is essential. It logs every action and lets you roll back any damage.\n"
                "**- Performance Monitoring:** Use **Spark** to profile your server and find out exactly what is causing lag."
            ),
            inline=False
        )
        embed.set_footer(text="A well-configured server on a good host makes all the difference!")
        await message.channel.send(embed=embed)
        logger.info(f"Provided Minecraft tips to {message.author.name}.")
        return # Handled

    # Keyword: Who am I?
    who_am_i_keywords = ["who am i", "main kaun hu", "am i staff", "am i a team member"]
    if any(keyword in user_prompt_lower for keyword in who_am_i_keywords):
        user_discord_name_lower = message.author.name.lower()
        if user_discord_name_lower in ZTX_TEAM_MEMBERS:
            description = f"Hello {message.author.mention}, you are recognized as a member of the ZTX Hosting team! I'm here to support you."
            embed = discord.Embed(title="ZTX Team Member Verified! 🌟", description=description, color=discord.Color.green())
        else:
            description = f"Hello {message.author.mention}, you are a valued member of our community. My records don't show you as a staff member. If this is incorrect, please contact an administrator."
            embed = discord.Embed(title="Valued Community Member", description=description, color=discord.Color.orange())
        await message.channel.send(embed=embed)
        logger.info(f"Answered 'who am I' for {message.author.name}.")
        return # Handled

    # Keyword: Greetings
    greeting_keywords = ["kaise ho", "how are you", "kya haal hai", "whats up"]
    if any(keyword in user_prompt_lower for keyword in greeting_keywords):
        description = "I am an AI assistant, so I don't have feelings, but I'm fully operational and ready to help you with any questions about ZTX Hosting. Thanks for asking!"
        embed = discord.Embed(title="Hello! 👋", description=description, color=discord.Color.blurple())
        await message.channel.send(embed=embed)
        logger.info(f"Responded to a greeting from {message.author.name}.")
        return # Handled

    # Keyword: ZTX Team Info
    team_keywords = ["team", "founder", "owner", "developer", "admin", "ztx team", "who is"]
    if any(keyword in user_prompt_lower for keyword in team_keywords):
        team_info = (
            "**Founder:** Bibek Mondal\n"
            "**Co-founder:** Jeteex\n"
            "**System Administrator/Technical Lead:** Mr. Akshay Thakur\n"
            "**Lead Developer:** Progamer"
        )
        embed = discord.Embed(title="Meet the ZTX Hosting Team 🧑‍💻", description=team_info, color=discord.Color.blue())
        await message.channel.send(embed=embed)
        logger.info(f"Provided ZTX team info to {message.author.name}.")
        return # Handled

    # Keyword: All Minecraft Plans
    if any(k in user_prompt_lower for k in ["minecraft plans", "game plans", "all plans"]):
        embed = discord.Embed(
            title="ZTX Hosting - Minecraft Plans 🎮",
            description="Here are all our available Minecraft hosting plans. All plans include DDoS Protection and full mod/plugin support.",
            color=discord.Color.dark_green()
        )
        for plan in MINECRAFT_PLANS:
            player_range = f"{plan['players_min']}-{plan['players_max']}" if plan['players_max'] else f"{plan['players_min']}+"
            embed.add_field(
                name=f"{plan['emoji']} {plan['name']} Plan - {plan['price']}/month",
                value=f"**RAM:** {plan['ram']} GB | **CPU:** {plan['cpu_percent']}% | **Disk:** {plan['disk_gb']} GB NVMe\n"
                      f"**Recommended Players:** {player_range}",
                inline=False
            )
        embed.set_footer(text="For more details or to order, visit ztxhosting.site")
        await message.channel.send(embed=embed)
        logger.info(f"Displayed all Minecraft plans for {message.author.name}.")
        return # Handled
        
    # NEW: Keyword: All VPS Plans
    if any(k in user_prompt_lower for k in ["vps plans", "vps hosting", "virtual private server"]):
        embed = discord.Embed(
            title="ZTX Hosting - VPS Plans ☁️",
            description="Our powerful and reliable KVM VPS plans. All plans come with full root access and DDoS protection.",
            color=discord.Color.from_rgb(114, 137, 218) # Discord Blurple
        )
        for plan in VPS_PLANS:
            embed.add_field(
                name=f"{plan['emoji']} {plan['name']} - {plan['price']}/month",
                value=f"**CPU:** {plan['cpu_cores']} Cores | **RAM:** {plan['ram_gb']} GB | **Disk:** {plan['disk_gb']} GB NVMe | **Bandwidth:** {plan['bandwidth_tb']} TB",
                inline=False
            )
        embed.set_footer(text="For more details or to order, visit ztxhosting.site/vps")
        await message.channel.send(embed=embed)
        logger.info(f"Displayed all VPS plans for {message.author.name}.")
        return # Handled

    # NEW: Keyword: All Dedicated Server Plans
    if any(k in user_prompt_lower for k in ["dedicated plans", "dedicated server", "bare metal"]):
        embed = discord.Embed(
            title="ZTX Hosting - Dedicated Servers 🖥️",
            description="Get ultimate performance with our dedicated bare metal servers. All plans are located in Germany.",
            color=discord.Color.dark_grey()
        )
        for plan in DEDICATED_PLANS:
            embed.add_field(
                name=f"{plan['emoji']} {plan['name']} - {plan['price']}/month",
                value=f"**CPU:** {plan['cpu']} ({plan['cpu_details']})\n"
                      f"**RAM:** {plan['ram']} | **Disk:** {plan['disk']}",
                inline=False
            )
        embed.set_footer(text="For more details or to order, visit ztxhosting.site/dedicated")
        await message.channel.send(embed=embed)
        logger.info(f"Displayed all Dedicated Server plans for {message.author.name}.")
        return # Handled


    # Keyword: Specific Minecraft Plan Request (e.g., "grass plan", "10 players", "8gb ram")
    minecraft_keywords = [
        "minecraft", "game hosting", "server plan", "price", "ram", "cpu", "gb", "%", "player"
    ] + [plan['name'].lower() for plan in MINECRAFT_PLANS]

    if any(keyword in user_prompt_lower for keyword in minecraft_keywords):
        # Extract specific requirements from the prompt
        requested_ram = int(re.search(r'(\d+)\s*gb', user_prompt_lower).group(1)) if re.search(r'(\d+)\s*gb', user_prompt_lower) else None
        requested_players = int(re.search(r'(\d+)\s*(player|banda|log)', user_prompt_lower).group(1)) if re.search(r'(\d+)\s*(player|banda|log)', user_prompt_lower) else None

        # Check for a specific plan name in the prompt
        found_plan = next((plan for plan in MINECRAFT_PLANS if plan['name'].lower() in user_prompt_lower), None)

        # Find a suitable plan based on RAM or players if no specific name was mentioned
        if not found_plan:
            suitable_plans = []
            for plan in MINECRAFT_PLANS:
                ram_ok = requested_ram is None or plan['ram'] >= requested_ram
                players_ok = requested_players is None or (plan['players_min'] <= requested_players and (plan['players_max'] is None or plan['players_max'] >= requested_players))
                if ram_ok and players_ok:
                    suitable_plans.append(plan)
            if suitable_plans:
                found_plan = suitable_plans[0] # The first plan that meets the criteria

        if found_plan:
            player_range = f"{found_plan['players_min']}-{found_plan['players_max']}" if found_plan['players_max'] else f"{found_plan['players_min']}+"
            embed = discord.Embed(
                title=f"{found_plan['emoji']} Minecraft {found_plan['name']} Plan",
                description=f"This plan is a great choice! Here are the details.",
                color=discord.Color.dark_green()
            )
            embed.add_field(name="Price", value=f"{found_plan['price']}/month", inline=True)
            embed.add_field(name="RAM", value=f"{found_plan['ram']} GB", inline=True)
            embed.add_field(name="CPU", value=f"{found_plan['cpu_percent']}%", inline=True)
            embed.add_field(name="Disk", value=f"{found_plan['disk_gb']} GB NVMe", inline=True)
            embed.add_field(name="Backups", value=f"{found_plan['backup_slots']} Slots", inline=True)
            embed.add_field(name="Recommended Players", value=player_range, inline=True)
            embed.add_field(name="Key Features", value=found_plan['plugins'], inline=False)
            embed.set_footer(text="Order now at ztxhosting.site")
            await message.channel.send(embed=embed)
        else:
            # If no suitable plan is found, suggest a custom plan or contact support
            description = "I couldn't find a standard plan that fits your exact needs. For high-player counts or specific requirements, we offer custom plans!\n\nPlease contact our support team for a personalized quote."
            embed = discord.Embed(title="Custom Plan Recommendation 🛠️", description=description, color=discord.Color.gold())
            await message.channel.send(embed=embed)
        logger.info(f"Handled Minecraft plan request for {message.author.name}.")
        return # Handled

    # --- Fallback to Gemini AI for other questions ---
    # If no specific keyword is matched, use the Gemini model to generate a response.
    try:
        # Provide context to the Gemini model about ZTX Hosting and its services.
        # This helps the AI generate more relevant and accurate responses.
        context = (
            "You are a helpful AI assistant for ZTX Hosting, a server hosting provider. "
            "You provide information about Minecraft server plans, VPS plans, and Dedicated Server plans. "
            "You also offer general tips for Minecraft server optimization. "
            "Always be polite and helpful. If a question is outside the scope of ZTX Hosting services "
            "or general server advice, politely state that you cannot assist with that specific query. "
            "Do not make up information about plans or services that are not listed in the provided data. "
            "Current Minecraft Plans: " + str(MINECRAFT_PLANS) + "\n"
            "Current VPS Plans: " + str(VPS_PLANS) + "\n"
            "Current Dedicated Server Plans: " + str(DEDICATED_PLANS) + "\n"
            "ZTX Team Members: Bibek Mondal (Founder), Jeteex (Co-founder), Akshay Thakur (System Administrator/Technical Lead), Progamer (Lead Developer)."
        )
        
        # Start a chat session with the model, providing the context
        chat_session = gemini_model.start_chat(history=[
            {"role": "user", "parts": [context]},
            {"role": "model", "parts": ["Understood. I am ready to assist with ZTX Hosting related queries."]}
        ])
        
        # Send the user's cleaned prompt to the Gemini model
        response = await asyncio.to_thread(chat_session.send_message, user_prompt_for_ai)
        
        # Check if the response is valid and send it to Discord
        if response and response.text:
            await message.channel.send(response.text)
            logger.info(f"Gemini responded to {message.author.name}: {response.text}")
        else:
            await message.channel.send("I'm sorry, I couldn't generate a response. Please try again later.")
            logger.warning(f"Gemini returned an empty or invalid response for {message.author.name}.")

    except Exception as e:
        logger.error(f"Error communicating with Gemini API for {message.author.name}: {e}")
        await message.channel.send("I'm sorry, I'm having trouble connecting to my AI brain right now. Please try again in a moment!")

# === Keep Alive Server ===
# This section runs a simple Flask web server in a separate thread.
# This is useful for hosting services (like Replit) that require a web server
# to be running to keep the application alive 24/7.
app = Flask('')

@app.route('/')
def home():
    """Defines the home route for the Flask app."""
    return "ZTX Hosting Bot is Online!"

def run_web():
    """Runs the Flask web server."""
    # Host on 0.0.0.0 to make it accessible from outside the container
    # Port 8080 is a common default for such services.
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    """Starts the Flask web server in a new thread."""
    t = Thread(target=run_web)
    t.start()
    logger.info("Keep-alive web server started.")

# --- 6. Run the Bot ---
# Start the keep-alive server before running the Discord bot.
keep_alive()
# Run the Discord bot using the token from environment variables.
client.run(DISCORD_BOT_TOKEN)
