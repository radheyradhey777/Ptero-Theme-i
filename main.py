import os
import discord
import google.generativeai as genai
from dotenv import load_dotenv
import asyncio
import logging
import re # Regular expressions for parsing user messages

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

# --- Minecraft Plans Data (Verified with ztxhosting.site on July 2024) ---
# This list contains all Minecraft hosting plans, used for providing specific details to users.
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

    # Keyword: Specific Plan Request (e.g., "grass plan", "10 players", "8gb ram")
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
        logger.info(f"Provided specific Minecraft plan info to {message.author.name}.")
        return # Handled

    # --- Fallback to Gemini AI ---
    # If the query was not handled by any specific keywords, send it to Gemini.
    try:
        await message.channel.typing()
        # Create a more detailed context prompt for the AI
        context_prompt = (
            "You are ZTX-AI, a helpful and friendly assistant for ZTX Hosting, a company that provides Minecraft, VPS, and Dedicated server hosting. "
            "Your persona is professional yet approachable. Answer in a clear, concise, and helpful manner. "
            "If you don't know the answer, say that you don't have information on that topic and suggest contacting ZTX support. "
            "Do not answer questions unrelated to web hosting, gaming, servers, or ZTX Hosting. "
            f"The user '{message.author.name}' has asked the following question: '{user_prompt_for_ai}'"
        )

        response = await asyncio.to_thread(gemini_model.generate_content, context_prompt)

        # Send the AI's response
        embed = discord.Embed(
            title="ZTX AI Assistant",
            description=response.text,
            color=discord.Color.purple()
        )
        embed.set_footer(text=f"AI response for {message.author.name}")
        await message.channel.send(embed=embed)
        logger.info(f"Responded to '{user_prompt_for_ai}' using Gemini for {message.author.name}.")

    except Exception as e:
        logger.error(f"An error occurred while generating a response from Gemini: {e}")
        error_embed = discord.Embed(
            title="An Error Occurred",
            description="I'm sorry, I encountered a problem while trying to process your request. Please try again later.",
            color=discord.Color.red()
        )
        await message.channel.send(embed=error_embed)

# --- 6. Run the Bot ---
try:
    client.run(DISCORD_BOT_TOKEN)
except discord.errors.LoginFailure:
    logger.error("CRITICAL: Login failed. The DISCORD_BOT_TOKEN is likely invalid. Please check your .env file.")
except Exception as e:
    logger.error(f"An unexpected error occurred while running the bot: {e}")


