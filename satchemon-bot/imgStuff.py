import discord
from PIL import Image, ImageDraw, ImageFont
import shutil
from pathlib import Path
import os

Images = "/home/bramsel/pybot/images/"

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

def createLeader(tmp, h):
    height = 0
    header = Image.open(os.path.join(Images, 'leader', '{}Header.png'.format(h)))
    height += header.size[1]
    tmpblank = os.path.join(Images, 'leader', 'tmpblank.png')
    tmpblank2 = os.path.join(Images, 'leader', 'tmpblank2.png')
    if h == 'c':
        height += len(tmp) * Image.open(os.path.join(Images, 'leader', 'blank.png')).size[1]
    else:
        height += 2 * len(tmp) * Image.open(os.path.join(Images, 'leader', 'blank.png')).size[1]
    bb = Image.open(os.path.join(Images, 'leader', 'bb.png'))
    height += bb.size[1]
    width = bb.size[0]
    complete = os.path.join(Images, 'leader', 'tmpcomplete.png')
    new_im = Image.new('RGBA', (width, height))
    new2_im = Image.new('RGBA', (width, height))
    y_offset = 0
    new_im.paste(header, (0, y_offset))
    y_offset += header.size[1]
    f = (255,255,255)
    size = 36
    p = (70,15)
    myFont = ImageFont.truetype('/home/bramsel/pybot/fonts/bitwise.ttf', size)
    for t in tmp:
        p = (70,15)
        baseImg = os.path.join(Images, 'leader', 'blank.png')
        shutil.copyfile(baseImg, tmpblank)
        img = Image.open(tmpblank)
        I1 = ImageDraw.Draw(img)
        if isinstance(t[1], float):
            tmpv = round(t[1],3)
        else:
            tmpv = t[1]
        I1.text(p, "{} | {}".format(t[0].upper(),tmpv), font=myFont, fill = f)
        new_im.paste(img, (0, y_offset))
        y_offset += img.size[1]
        if h == 'c':
            pass
        else:
            baseImg2 = os.path.join(Images, 'leader', 'blank.png')
            shutil.copyfile(baseImg, tmpblank2)
            img2 = Image.open(tmpblank2)
            I2 = ImageDraw.Draw(img2)
            p = (90,15)
            I2.text(p, "{} GP   |   GRADE: {}   |   {}Holographic".format(t[4], t[2], '' if t[3] else 'Non-'), font=myFont, fill = f)
            new_im.paste(img2, (0, y_offset))
            y_offset += img.size[1]
    new_im.paste(bb, (0, y_offset))
    new_im.save(complete)
    return discord.File(complete)

