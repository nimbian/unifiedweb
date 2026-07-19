import os
import random
from datetime import datetime, timezone
from sqlhelper import *
from buttons import *
from PIL import Image, ImageDraw, ImageFont
import shutil
from pathlib import Path

TVtoCR = [36,67,95,121,145,167,187,206,224,241,257,272,286,299,311,322,332,341,349,356,362,367,372,376,380,384,387,390,393,395,397,399,400]

CRList = ['1/8','1/4','1/2','1','2','3','4','5','6','7','8','9','10','11','12','13','14','15','16','17','18','19','20','21','22','23','24','25','26','27','28','29','30']

GradeList = [45,65,80,90,96,101]

ValueGP = [0.50,0.68,0.90,1.16,1.49,1.93,2.51,3.22,4.16,5.39,6.94,8.92,11.45,14.68,18.82,24.13,30.84,39.36,50.16,63.76,80.88,102.34,129.20,162.50,203.52,254.10,315.75,390.07,479.97,585.41,708.93,848.60,2000.00]
ValueMulti = [1,1.2,1.5,2,3,5]

Images = "/home/bramsel/pybot-dev/mooreDnD-Bot/images/"

FF_LIST = [1214255387193245726,
           587093342102224917,
           693204053546500117,
           257535802223886339,
           752747072553484359,
           527718295751622656,
           236153107258540033,
           542406091426889731,
           222886192436215809,
           98962763174412288]

async def getDID(user):
    did = await bot.fetch_user(user)
    return did

async def sponsor(ctx):
    #if ctx.author.id in FF_LIST:
    #    return
    if random.randint(1,200) == 1:
        uid = getUserID(ctx.author.id)
        mon = random.choice(getSponsors())
        grade = random.randint(1,100)
        g = 0
        while grade > GradeList[g]:
            g += 1
        g += 5
        v = round(2000 * ValueMulti[g-5],3)
        collectMon(uid, mon[0], g, 1, v, datetime.now())
        tmp = createCardImg(mon[0], 10, 1, 'Item')
        #resp = '''
        #Congratulations is in order to {} from @everyone here for being the first adventurer to uncover the legendary Dungeon Alchemist sponsor card. As a reward for your bold fortune {}, you've’ve earned a FREE copy of Dungeon Alchemist, the 3D generative mapmaking tool that brings imagination to life!

#While the event has now ended, your collections may forever grow! Continue to look out for the legendary Dungeon Alchemist card in every pack and keep an eye out for new cards in the future. Happy hunting everyone!'''
        resp = '''{} pulled a bonus sponsor card worth {} GP!'''
        await ctx.respond(resp.format(ctx.author.name.replace('_','\_').replace('*','\*'), v), file=discord.File(tmp))




def holo_multi(cr):
    return 11.3 - (cr * .3)

def createD10img(num, c):
    genImg = os.path.join(Images, "gens", '{}{}.png'.format(c, num))
    if not os.path.isfile(genImg):
        baseImg = os.path.join(Images, 'p_D10.png')
        
        f = (255,255,255)
        shutil.copyfile(baseImg, genImg)
        img = Image.open(genImg)
        I1 = ImageDraw.Draw(img)
        size = 300
        if c == 't':
            if  num < 10 or num == 100:
                p = (350,330)
            elif  num >= 20:
                p = (360,330)
            else:
                p = (375,330)
        else:
            p = (430,330)
            if num % 10 == 1:
                p = (450,330)
        myFont = ImageFont.truetype('/home/bramsel/pybot/fonts/d20.tff', size)
        if c == 't':
            if num < 10 or num == 100:
                txt = '00'
            else:
                txt = ((num // 10) * 10)
        else:
            txt = num % 10
        I1.text(p, str(txt), font=myFont, fill = f)
        img.save(genImg)
    return genImg    

def createD20img(num, c):
    genImg = os.path.join(Images, "gens", '{}{}.png'.format(c, num))
    if not os.path.isfile(genImg):
        baseImg = os.path.join(Images, '{}_D20.png'.format(c))
        
        f = (255,255,255) if c == 'b' else (0,0,0)
        shutil.copyfile(baseImg, genImg)
        img = Image.open(genImg)
        I1 = ImageDraw.Draw(img)
        size = 300
        if num < 10:
            p = (380,315)
        elif num == 20:
            size = 250
            p = (330,330)
        elif num == 11:
            p = (355,315)
        else:
            p = (330,315)
        if num == 1:
            p = (400,315)
        myFont = ImageFont.truetype('/home/bramsel/pybot/fonts/d20.tff', size)
        I1.text(p, "{}".format(num), font=myFont, fill = f)
        img.save(genImg)
    return genImg    

def combineImgs(gd, bd, td, sd):
    tmp = os.path.join(Images, "gens", '{}{}{}{}.png'.format(Path(gd).stem, Path(bd).stem, Path(td).stem, Path(sd).stem))
    if not os.path.isfile(tmp):
        images = [Image.open(x) for x in [gd, bd, td, sd]]
        widths, heights = zip(*(i.size for i in images))
    
        total_width = sum(widths)
        max_height = max(heights)
    
        new_im = Image.new('RGBA', (total_width, max_height))
    
        x_offset = 0
        for im in images:
            new_im.paste(im, (x_offset,0))
            x_offset += im.size[0]
        new_im.save(tmp)
    return tmp

def createCardImg(cid, g, h, t):
    #cid = random.randint(1,10)
    if h:
        h = random.randint(1,16)
        if h < 13:
            hx = random.randint(0,1)
            hy = random.randint(0,1)
            hrot = random.randint(0,1)
        else:
            hx = 0
            hy = 0
            hrot = 0

    if g < 10:
        gsub = random.randint(1,3)
        gx = random.randint(0,1)
        gy = random.randint(0,1)
        grot = random.randint(0,1)
    else:
        gsub = 1
        gx = 0
        gy = 0
        grot = 0

    if h:
        genImg = os.path.join(Images, "gens", 'c{}hx{}y{}rot{}gsub{}x{}y{}rot{}.png'.format(cid,hx,hy,hrot,gsub,gx,gy,grot))
    else:
        genImg = os.path.join(Images, "gens", 'c{}gsub{}x{}y{}rot{}.png'.format(cid,gsub,gx,gy,grot))
    if not os.path.isfile(genImg) or True:
        baseImg = os.path.join(Images, 'cards', 'Cards', '{}.png'.format(cid))
        gImg = os.path.join(Images, 'cards', 'Grade', 'G{}_{}.png'.format(g,gsub))
        cImg = ''
        if t == 'Monsters':
            cImg = os.path.join(Images, 'cards', 'Color', '{}.png'.format('Red'))
        elif t == 'Item':
            cImg = os.path.join(Images, 'cards', 'Color', '{}.png'.format('Blue'))
        elif t == 'Locations':
            cImg = os.path.join(Images, 'cards', 'Color', '{}.png'.format('Green'))
        shutil.copyfile(baseImg, genImg)
        img = Image.open(genImg)
        img = img.convert("RGBA")
        gimg = Image.open(gImg)
        cimg = Image.open(cImg)
        cimg = cimg.convert("RGBA")
        if h:
            hImg = os.path.join(Images, 'cards', 'Holo', 'H{}.png'.format(h))
            himg = Image.open(hImg)
            if hx:
                himg = himg.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            if hy:
                himg = himg.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            if hrot:
                himg = himg.transpose(Image.Transpose.ROTATE_180)
            himg = himg.convert("RGBA")
            cimg = Image.alpha_composite(cimg, himg)

        if gx:
            gimg = gimg.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if gy:
            gimg = gimg.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        if grot:
            gimg = gimg.transpose(Image.Transpose.ROTATE_180)
        gimg = gimg.convert("RGBA")
        cimg = Image.alpha_composite(cimg, img)
        cimg = Image.alpha_composite(cimg, gimg)
        cimg.save(genImg)
    return genImg


def puller(t):
    GD = random.randint(1,20)
    BD = random.randint(1,20)
    TV = (GD - 1) * 20 + BD
    CR = 0
    while TV > TVtoCR[CR]:
        CR += 1
    grade = random.randint(1,100)
    g = 0
    while grade > GradeList[g]:
        g += 1
    g += 5
    holo = 0
    if TV in TVtoCR:
        holo = 1
    newCR = CRList[CR]
    mon = random.choice(getMonsFromCR(newCR,t))
    if '*' in mon[1]:
        holo = 1
    multi = 1
    if holo:
        if CR == 32:
            multi = 1 
        else: 
            multi = holo_multi(CR)
    v = round(ValueGP[CR] * ValueMulti[g-5] * multi,3)
    gd20 = os.path.join(Images, createD20img(GD,'g'))
    bd20 = os.path.join(Images, createD20img(BD,'b'))
    td10 = os.path.join(Images, createD10img(grade,'t'))
    sd10 = os.path.join(Images, createD10img(grade,'s'))
    #tmp = createCardImg(mon[0], g, holo, t)
    tmp = combineImgs(gd20, bd20, td10, sd10)
    combine = discord.File(tmp)
    return [mon, g, holo, v, combine, CR]
