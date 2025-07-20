import discord
from discord.ext import commands

# ==== Custom ZTX Hosting Info ====
ztx_info = """
ZTX Hosting offers fast and affordable hosting services for Minecraft, VPS, and websites.
Main Plans:
- Grass Plan: 2 GB RAM, ₹100/month
- Dirt Plan: 4 GB RAM, ₹200/month
- Stone Plan: 6 GB RAM, ₹300/month
All plans include NVMe SSD, DDoS protection, and high performance.

Support:
https://ztxhosting.site/support
Discord Support:
https://discord.gg/tYqgqSJMRU

Website:
https://ztxhosting.site
"""

# ==== Discord Bot Setup ====
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user}")

@bot.command()
async def ztx(ctx, *, question):
    q = question.lower()

    # Simple matching logic
    if "plan" in q or "ram" in q:
        await ctx.send("💡 Plans:\n- Grass: 2GB ₹100\n- Dirt: 4GB ₹200\n- Stone: 6GB ₹300")
    elif "price" in q:
        await ctx.send("💰 Pricing:\nGrass ₹100/mo\nDirt ₹200/mo\nStone ₹300/mo")
    elif "support" in q:
        await ctx.send("🛠️ Support:\nhttps://ztxhosting.site/support\nDiscord: https://discord.gg/tYqgqSJMRU")
    elif "website" in q:
        await ctx.send("🌐 Visit: https://ztxhosting.site")
    else:
        await ctx.send("📘 ZTX Hosting Info:\n" + ztx_info[:500] + "...")  # Short summary

bot.run("MTM4MTMyODM2MzA1MzkxMjA3NA.GcWIKl.EHEzRvMQm2x_M9p7Sjv--IdtpjPfbc-m7Q5jJo")