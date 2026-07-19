import discord
import os
import random
from table2ascii import table2ascii as t2a, PresetStyle
from sqlhelper import *
from buttons import *
from imgStuff import *

async def tradeIt(ctx, wantedcard, mycard=None, mymoney=0, wantedmoney=0):
    if ctx.author.bot:
        return
    try:
        if float(mymoney) < 0 or float(wantedmoney) < 0:
            await ctx.respond("Gold has to be positive", ephemeral=True)
            return
    except:
        await ctx.respond("Gold has to be a number", ephemeral=True)
        return

    mcard = mycard
    wcard = wantedcard
    if mcard:
        mcards = set(mcard.split(','))
    else:
        mcards = []
    wcards = set(wcard.split(','))
    gp = float(getGold(ctx.author.id))
    if float(mymoney) > gp:
        await ctx.respond("You do not have that much gold", ephemeral=True)
        return
    for c in mcards:
        res = yourCard(c, ctx.author.id)
        if res is None:
            await ctx.respond("This is not your card(s)", ephemeral=True)
            return
    for c in wcards:
        res = cardExists(c)
        if res is None:
            await ctx.respond("Wanted card does not exist", ephemeral=True)
            return
        if wcard:
            res = sameOwner(wcards)
            if len(res) > 1:
                await ctx.respond("Wanted cards not owned by same collector", ephemeral=True)
                return
    else:
        ouid = res[0][0]
    for c in wcards:
        res = yourCard(c, ctx.author.id)
        if res:
            await ctx.respond("You can't trade for your own card", ephemeral=True)
            return
    tmpview = discord.ui.View(timeout=60)
    tmpview.add_item(c_button(ctx.author.id, ouid, mcards, wcards, float(mymoney), float(wantedmoney)))
    mcards = list(mcards)
    wcards = list(wcards)
    plen = len(mcards)
    rlen = len(wcards)
    m = max(plen, rlen)
    tmp = []
    for i in range(m):
        t = []
        if i >= plen:
            t += ['','','','']
        else:
            t += getCard(mcards[i])
        if i >= rlen:
            t += ['','','','']
        else:
            t += getCard(wcards[i])
        tmp += [t]
    tmp += [['Gold','','', mymoney, 'Gold', '', '', wantedmoney]]

    output = t2a(
        header=["My Card", "Grade", "Holo", "Value", "Asking Card", "Grade", "Holo", "Value"],
        body = tmp,
        style = PresetStyle.thin_compact
    )
    
    resp = f"Proposed trades:\n```\n{output}\n```"
    await ctx.respond(resp, view=tmpview, ephemeral=True)
    #TODO Send message to user

async def ptrades(ctx):
    if ctx.author.bot:
        return
    res = listProposedTrades(ctx.author.id)
    if not res:
        await ctx.respond("No Proposed Trades", ephemeral=True)
        return
    for r in res:
        plen = len(res[r]['p'])
        rlen = len(res[r]['r'])
        m = max(len(res[r]['p']),len(res[r]['r']))
        tmp = []
        for i in range(m):
            t = []
            if i >= plen:
                t += ['','','','']
            else:
                t += [res[r]['p'][i][0],res[r]['p'][i][1],res[r]['p'][i][2],res[r]['p'][i][3]]
            if i >= rlen:
                t += ['','','','']
            else:
                t += [res[r]['r'][i][0],res[r]['r'][i][1],res[r]['r'][i][2],res[r]['r'][i][3]]
            tmp += [t]

        output = t2a(
            header=["My Card", "Grade", "Holo", "Value", "Asking Card", "Grade", "Holo", "Value"],
            body = tmp,
            style = PresetStyle.thin_compact
        )
        resp = f"Proposed trades:\n```\n{output}\n```"
        tmpview = discord.ui.View(timeout=60)
        tmpview.add_item(w_button(r))
        
        await ctx.respond(resp[:1950], view=tmpview, ephemeral=True)
    return
        

async def rtrades(ctx, bot):
    if ctx.author.bot:
        return
    res = listRequestedTrades(ctx.author.id)
    if not res:
        await ctx.respond("No Requested Trades", ephemeral=True)
        return
    for r in res:
        plen = len(res[r]['p'])
        rlen = len(res[r]['r'])
        m = max(len(res[r]['p']),len(res[r]['r']))
        tmp = []
        for i in range(m):
            t = []
            if i >= plen:
                t += ['','','','']
            else:
                t += [res[r]['p'][i][0],res[r]['p'][i][1],res[r]['p'][i][2],res[r]['p'][i][3]]
            if i >= rlen:
                t += ['','','','']
            else:
                t += [res[r]['r'][i][0],res[r]['r'][i][1],res[r]['r'][i][2],res[r]['r'][i][3]]
            tmp += [t]

        output = t2a(
            header=["Your Card", "Grade", "Holo", "Value", "Their Card", "Grade", "Holo", "Value"],
            body = tmp,
            style = PresetStyle.thin_compact
        )
        
        resp = f"Requested trades:\n```\n{output}\n```"
        tmpview = discord.ui.View(timeout=60)
        tmpview.add_item(a_button(r,tmpview,bot))
        tmpview.add_item(r_button(r,tmpview))

        
        await ctx.respond(resp[:1950], view=tmpview, ephemeral=True)
    return
