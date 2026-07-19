from sqlhelper import *
import discord
Images = "/home/bramsel/pybot/images/"

async def auditPost(bot, resp, t):
    if t == 'trade':
        out = discord.File('{}{}'.format(Images,'New_Trade_Alert.png'))
    if t == 'add':
        out = discord.File('{}{}'.format(Images,'New_Title_Acquisition_Alert.png'))
    if t == 'sell':
        out = discord.File('{}{}'.format(Images,'New_Card_Sale_Alert.png'))
    if t == 'del':
        out = discord.File('{}{}'.format(Images,'New_Title_Revocation_Alert.png'))
    if t == 'buy':
        out = discord.File('{}{}'.format(Images,'New_Shop_Purchase_Alert.png'))
    ac = bot.get_channel(int(getOption('audit')))
    await ac.send(resp,file=out)
