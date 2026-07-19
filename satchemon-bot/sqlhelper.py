from datetime import datetime, timezone, timedelta
import random
from os import path
from table2ascii import table2ascii as t2a, PresetStyle
import mydb

def getUserName(did):
    with mydb.db_cursor() as cur:
        cur.execute("SELECT name from users where did = %s", (did,))
        return cur.fetchone()

def donateCards(uid, cards):
    power = 0
    for c in cards:
        removeTradesWithCard(c)
    for c in cards:
        with mydb.db_cursor() as cur:
            cur.execute("select value from collections where collections.rwid = %s", (c,))
            power += cur.fetchone()[0]
            cur.execute("update collections set uid = 0 where rwid = %s", (c,))
            cur.execute("INSERT into donations(uid, cid) values(%s,%s)", (uid, c))
    with mydb.db_cursor() as cur:
        cur.execute("update power set power = power + %s", (power,))
    return

def sellCards(uid, cards):
    for c in cards:
        removeTradesWithCard(c)
    for c in cards:
        with mydb.db_cursor() as cur:
            cur.execute("update collections set uid = 0 where rwid = %s", (c,))
    return

def getDID(uid):
    with mydb.db_cursor() as cur:
         cur.execute("select did from users where rwid = '%s'",(uid,))
         return cur.fetchone()[0]

def hasCard(did, monid):
    uid = getUserID(did)
    with mydb.db_cursor() as cur:
         cur.execute("SELECT rwid from collections where uid = '%s' and monid = %s", (uid, monid))
         return cur.fetchone()

def getCard(cid):
    with mydb.db_cursor() as cur:
        cur.execute("SELECT mons.name, grade, holo, value from collections join mons on mons.rwid = collections.monid"+
                    " where collections.rwid = %s",(cid,))
        return cur.fetchone()

def sameOwner(cards):
    with mydb.db_cursor() as cur:
        cur.execute("SELECT DISTINCT(uid) from collections where rwid in ({})".format(",".join(["%s"]*len(cards))), list(cards))
        return cur.fetchall()

def getPulls(did):
    with mydb.db_cursor() as cur:
        cur.execute("SELECT pulls from users where did = %s",(did,))
        return cur.fetchone()[0]

def usePull(did):
    with mydb.db_cursor() as cur:
        cur.execute("update users set pulls = pulls - 1 where did = %s",(did,))
    return 

def createUser(user, did):
    """Resolve-or-create the users row for a Discord id; return its rwid.

    Idempotent (PLAN §6.1): ``ON CONFLICT (did) DO NOTHING`` (backed by the
    ``undid`` unique constraint) turns a repeat call — or a row the bot didn't
    know already existed, e.g. a web-first account that has since linked
    Discord — into a no-op instead of a unique-constraint crash, and never
    clobbers that existing row's data. Always re-selects the rwid afterward so
    callers never assume the INSERT is what created the row.
    """
    with mydb.db_cursor() as cur:
        cur.execute("INSERT into users(name,did,gp,pulls,yt,tt) values (%s,%s,0,3,1,1)"
                    " ON CONFLICT (did) DO NOTHING",(user,did))
        cur.execute("SELECT rwid from users where did = %s",(did,))
        row = cur.fetchone()
        return row[0] if row else None

def getUserID(user):
    with mydb.db_cursor() as cur:
        try:
            cur.execute("SELECT rwid from users where did = %s",(user,))
            return cur.fetchone()[0]
        except:
            return None

def getSponsors():
    with mydb.db_cursor() as cur:
        try:
            cur.execute("SELECT rwid,name,exp from mons where exp = 'SPONS'")
            return cur.fetchall()
        except:
            return None


def giveTTEntries(uid, es, un):
    with mydb.db_cursor() as cur:
        cur.execute("update users set ttentries = %s, tt = 0, ttusername = %s where rwid = %s",(es,un,uid))

def giveYTEntries(uid, es, un):
    with mydb.db_cursor() as cur:
        cur.execute("update users set ytentries = %s, yt = 0, ytusername = %s where rwid = %s",(es,un,uid))

def hasTT(uid):
    with mydb.db_cursor() as cur:
        cur.execute("select tt from users where rwid = %s",(uid,))
        return int(cur.fetchone()[0])

def hasYT(uid):
    with mydb.db_cursor() as cur:
        cur.execute("select yt from users where rwid = %s",(uid,))
        return int(cur.fetchone()[0])

def getTravelers():
    with mydb.db_cursor() as cur:
        try:
            cur.execute("select * from (select name, (select value from options where key = 'pir')::int - sum(value) "+
                        "as dist from eventcollections join users on eventcollections.uid = users.rwid group by name order by dist) as A where dist > 0")
            return cur.fetchall()
        except:
            return None



def eventCollectMon(uid, monid, grade, holo, value, date):
    with mydb.db_cursor() as cur:
        cur.execute("INSERT into eventCollections(uid, monid, grade, holo, value, date)"+
                    " values('%s',%s,'%s','%s','%s',%s)",(uid,monid,grade,holo,value,date))
    return

def delEvCollection():
    with mydb.db_cursor() as cur:
        cur.execute("DELETE from eventCollections")
        cur.execute("DELETE from eventTreasures")
    return

def getEvCollection():
    with mydb.db_cursor() as cur:
        cur.execute("select users.name, mons.name, grade, holo, value from eventcollections as ec join users on ec.uid = users.rwid join mons on ec.monid=mons.rwid")
        return cur.fetchall()

def getEvTreCol():
    with mydb.db_cursor() as cur:
        cur.execute("select users.name, treasures.name,value from eventtreasures as et join users on users.rwid = et.uid join treasures on treasures.rwid = et.treasure")
        return cur.fetchall()

def collectMon(uid, monid, grade, holo, value, date):
    with mydb.db_cursor() as cur:
        cur.execute("INSERT into collections(uid, monid, grade, holo, value, date)"+
                    " values('%s',%s,'%s','%s','%s',%s)",(uid,monid,grade,holo,value,date))
    return

def getMonsFromCR(CR, t):
    with mydb.db_cursor() as cur:
        cur.execute("SELECT rwid,name,exp from mons where CR = %s and exp != 'Promo' and exp != 'SPONS' and class = %s",(CR,t))
        return cur.fetchall()

def getEvColValue(did):
    with mydb.db_cursor() as cur:
        cur.execute("SELECT sum(value) from eventCollections inner join users on eventCollections.uid = users.rwid where did = %s",(did,))
        return cur.fetchone()

def getBBEGdmg():
    with mydb.db_cursor() as cur:
        cur.execute("SELECT sum(value) from eventCollections")
        return cur.fetchone()

def mostValuableCollection():
    with mydb.db_cursor() as cur:
        cur.execute("SELECT users.name, sum(value), users.did from collections inner join users"+
                    " on collections.uid = users.rwid where users.rwid > 0 group by (users.name, users.did)"+
                    " order by sum(value) desc limit 3")
        return cur.fetchall()

def getCollection(user, limit=10):
    with mydb.db_cursor() as cur:
        cur.execute("select collections.rwid, mons.cr, mons.name, mons.exp, grade, holo, ed, value, collections.date, mons.rwid"+
                    " from collections inner join users on collections.uid = users.rwid inner join mons"+
                    " on collections.monid=mons.rwid where users.did = %s order by value desc LIMIT %s",(user, limit))
        return cur.fetchall()

def getAllUsers():
    with mydb.db_cursor() as cur:
        cur.execute("select name, did, count(value), sum(value), gp from users join collections on users.rwid = collections.uid"+
                    " group by (name, did, gp)")
        return cur.fetchall()
    
def deactivateEvent():
    with mydb.db_cursor() as cur:
        tmp = getActiveEvent()[0]
        cur.execute("update events set active = '%s'",(0,))
    return tmp

def activateEvent(event):
    with mydb.db_cursor() as cur:
        cur.execute("update events set active = '%s' where event = %s",(1,event))
    return

def getActiveEvent():
    with mydb.db_cursor() as cur:
        cur.execute("select event from events where active = 1")
        return cur.fetchone()

def getGold(user):
    with mydb.db_cursor() as cur:
        cur.execute("select gp from users where did = %s", (user,))
        return cur.fetchone()[0]

def spendGold(user, gold):
    with mydb.db_cursor() as cur:
        cur.execute("update users set gp = gp - '%s' where did = '%s'", (gold, user))
    return

def giveToken(user):
    with mydb.db_cursor() as cur:
        cur.execute("update users set pulls = pulls + 1 where did = %s", (user,))
    return

def giveGold(user, gold):
    with mydb.db_cursor() as cur:
        cur.execute("update users set gp = gp + %s where did = %s", (gold, user))
    return

def getPromos(promo):
    with mydb.db_cursor() as cur:
        cur.execute("select * from promos where code = %s", (promo,))
        try:
            return cur.fetchone()
        except:
            return None

def pTracker(did, code):
    with mydb.db_cursor() as cur:
        cur.execute("insert into ptracker values(%s, %s)", (did, code))
    return

def addPromo(code, gold):
    with mydb.db_cursor() as cur:
        cur.execute("insert into promos values(-1, %s, %s, 0, 0, 'Y')", (code.upper(), gold))
    return

def getMMS():
    with mydb.db_cursor() as cur:
        cur.execute("select did from MMS")
        return cur.fetchall()

def getCSS():
    with mydb.db_cursor() as cur:
        cur.execute("select did from CSS")
        return cur.fetchall()

def addMMS(did):
    with mydb.db_cursor() as cur:
        cur.execute("insert into MMS values(%s)", (did,))
        return

def addCSS(did):
    with mydb.db_cursor() as cur:
        cur.execute("insert into CSS values(%s)", (did,))
        return

def delMMS(did):
    with mydb.db_cursor() as cur:
        cur.execute("delete from MMS where did = %s", (did,))
        return

def delCSS(did):
    with mydb.db_cursor() as cur:
        cur.execute("delete from CSS where did = %s", (did,))
        return

def getColAbove(gold):
    with mydb.db_cursor() as cur:
        cur.execute("select * from (select did, sum(value) from users join collections on users.rwid = collections.uid where did > 0 group by did)as a where sum > %s", (gold, ))
        return cur.fetchall()

def getBestCards():
    d = datetime.now()
    d7 = d - timedelta(days=7)
    base = ("select users.name, mons.name, grade, holo, value from collections inner join users on users.rwid="
           "collections.uid inner join mons on collections.monid=mons.rwid where users.rwid > 0 and value ="
           " (SELECT MAX(value) from collections")
    with mydb.db_cursor() as cur:
        cur.execute(base + ")") 
        alltime = cur.fetchall()
        tmp = str(datetime.strftime(d,"%Y-%m-01"))
        cur.execute(base + " where date > %s::date and uid > 0) and date > %s::date and uid > 0",(tmp,tmp))
        month = cur.fetchall()
        tmp = str(datetime.strftime(d7,"%Y-%m-%d")) 
        cur.execute(base + " where date >= %s::date and uid > 0) and date >= %s::date and uid > 0",(tmp,tmp))
        days7 = cur.fetchall()
        tmp = str(datetime.strftime(d,"%Y-%m-%d"))
        cur.execute(base + " where date >= %s::date and uid > 0) and date >= %s::date and uid > 0",(tmp,tmp))
        today = cur.fetchall()
        return [alltime, month, days7, today]

def yourCard(card, name):
    with mydb.db_cursor() as cur:
        try:
            cur.execute("select 1 from collections inner join users on collections.uid = users.rwid"+
                        " where collections.rwid = %s and users.did = '%s'",(card, name))
            res = cur.fetchone()
        except:
            res = None
        return res

def usedPromo(did, code):
    with mydb.db_cursor() as cur:
        try:
            cur.execute("select 1 from ptracker where did = '%s' and code = %s",(did, code))
            res = cur.fetchone()
        except:
            res = False
        return res



def cardExists(card):
    with mydb.db_cursor() as cur:
        try:
            cur.execute("select 1 from collections where rwid = %s",(card,))
            res = cur.fetchone()
        except:
            res = None
        return res

def createTrade(pid, rid, mcards, wcards, mmoney, wmoney, d):
    with mydb.db_cursor() as cur:
        cur.execute("INSERT into trades (pid, rid, date) values ('%s','%s',%s)", (pid, rid, d))
        cur.execute("SELECT currval('public.trades_rwid_seq')")
        tid = cur.fetchone()[0]
        for m in mcards:
            cur.execute("INSERT into ptrades(tid, cid) values('%s',%s)",(tid, m))
        for w in wcards:
            cur.execute("INSERT into rtrades(tid, cid) values('%s',%s)",(tid, w))
            cur.execute("INSERT into pmoney(tid, money) values('%s','%s')",(tid, mmoney))
            cur.execute("INSERT into rmoney(tid, money) values('%s','%s')",(tid, wmoney))
        spendGold(getDID(pid), mmoney)
    return

def listProposedTrades(name):
    with mydb.db_cursor() as cur:
        cur.execute("select trades.rwid from trades join users on trades.pid = users.rwid"+
                    " where users.did = '%s' order by date limit 5", (name,))
        res = cur.fetchall()
        tmp = {}
        for r in res:
            tmp.setdefault(r[0], {})
            tmp[r[0]].setdefault("p",[])
            cur.execute("select money from pmoney where tid = '%s'",(r[0],))
            tmp[r[0]]["p"] += [["Gold","","",cur.fetchone()[0]]]
            cur.execute("select mons.name, collections.grade, collections.holo, collections.value"+
                        " from trades join ptrades on trades.rwid=ptrades.tid join collections"+
                        " on ptrades.cid = collections.rwid join mons on collections.monid=mons.rwid where trades.rwid = '%s'",(r[0],))
            tmp[r[0]]["p"] += cur.fetchall()
        for r in res:
            tmp[r[0]].setdefault("r",[])
            cur.execute("select money from rmoney where tid = '%s'",(r[0],))
            tmp[r[0]]["r"] += [["Gold","","",cur.fetchone()[0]]]
            cur.execute("select mons.name, collections.grade, collections.holo, collections.value from trades"+
                        " join rtrades on trades.rwid=rtrades.tid join collections on rtrades.cid = collections.rwid"+
                        " join mons on collections.monid=mons.rwid where trades.rwid = '%s'",(r[0],))
            tmp[r[0]]["r"] += cur.fetchall()
        return tmp

def listRequestedTrades(name):
    with mydb.db_cursor() as cur:
        cur.execute("select trades.rwid from trades join users on trades.rid = users.rwid where"+
                    " users.did = '%s' order by date limit 5", (name,))
        res = cur.fetchall()
        tmp = {}
        for r in res:
            tmp.setdefault(r[0], {})
            tmp[r[0]].setdefault("p",[])
            cur.execute("select money from rmoney where tid = '%s'",(r[0],))
            tmp[r[0]]["p"] += [["Gold","","",cur.fetchone()[0]]]
            cur.execute("select mons.name, collections.grade, collections.holo, collections.value from trades join rtrades"+
                        " on trades.rwid=rtrades.tid join collections on rtrades.cid = collections.rwid join mons"+
                        " on collections.monid=mons.rwid where trades.rwid = '%s'",(r[0],))
            tmp[r[0]]["p"] += cur.fetchall()

        for r in res:
            tmp[r[0]].setdefault("r",[])
            cur.execute("select money from pmoney where tid = '%s'",(r[0],))
            tmp[r[0]]["r"] += [["Gold","","",cur.fetchone()[0]]]
            cur.execute("select mons.name, collections.grade, collections.holo, collections.value from trades join ptrades"+
                        " on trades.rwid=ptrades.tid join collections on ptrades.cid = collections.rwid join mons"+
                        " on collections.monid=mons.rwid where trades.rwid = '%s'",(r[0],))
            tmp[r[0]]["r"] +=     cur.fetchall()

        return tmp

def acceptTrade(tid,bot):
    with mydb.db_cursor() as cur:
        cur.execute("select pid, rid from trades where trades.rwid = '%s'",(tid,))
        try:
            pid, rid = cur.fetchone()
        except:
            return
        puser = getUserName(getDID(pid))[0]
        ruser = getUserName(getDID(rid))[0]
        cur.execute("select cid from rtrades where rtrades.tid = '%s'",(tid,))
        rcids = cur.fetchall()
        cur.execute("select cid from ptrades where ptrades.tid = '%s'",(tid,))
        pcids = cur.fetchall()
        cur.execute("select money from rmoney where tid = '%s'",(tid,))
        mb = cur.fetchone()[0]
        cur.execute("select money from pmoney where tid = '%s'",(tid,))
        rb = cur.fetchone()[0]
        cur.execute("update users set gp = gp - '%s' where rwid = (SELECT rid from trades where rwid = '%s')",(mb, tid))
        cur.execute("update users set gp = gp + '%s' where rwid = (SELECT pid from trades where rwid = '%s')",(mb, tid))
        cur.execute("update users set gp = gp + '%s' where rwid = (SELECT rid from trades where rwid = '%s')",(rb, tid))
        rc = []
        for c in rcids:
            rc += [list(getCard(c))]
            cur.execute("update collections set uid = '%s' where rwid = '%s'",(pid,c[0]))
        pc = []
        for c in pcids:
            pc += [list(getCard(c))]
            cur.execute("update collections set uid = '%s' where rwid = '%s'",(rid,c[0]))
        cur.execute("select cid from ptrades where tid = '%s' union select cid from rtrades where tid = '%s'",(tid,tid))
        tmp = cur.fetchall()
        cur.execute("select trades.rwid from trades join rtrades on trades.rwid = rtrades.tid where cid IN"+
                    " (SELECT cid from rtrades where rtrades.tid = '%s')",(tid,))
        rtids = cur.fetchall()
        for r in rtids:
            deleteTrade(r[0], Accept=True)
        cur.execute("select trades.rwid from trades join ptrades on trades.rwid = ptrades.tid where cid IN"+
                    " (SELECT cid from ptrades where ptrades.tid = '%s')",(tid,))
        ptids = cur.fetchall()
    for p in ptids:
        deleteTrade(p[0], Accept=True)
    deleteTrade(tid, Accept=True)
    for t in tmp:
        removeTradesWithCard(t)
    output1 = t2a(
            header=['Card','Grade','Holo','Value'],
            body = rc,
            style = PresetStyle.thin_compact
    )
    output2 = t2a(
            header=['Card','Grade','Holo','Value'],
            body = pc,
            style = PresetStyle.thin_compact
    )
    resp = f"```{puser} has traded {rb} gp and:\n{output2}\n to {ruser} for {mb} gp and:\n{output1}```"
    return [getDID(pid), getDID(rid), resp]

def removeTradesWithCard(cid):
    with mydb.db_cursor() as cur:
        cur.execute("select trades.rwid from trades join rtrades on trades.rwid = rtrades.tid where cid = %s",(cid,))
        rtids = cur.fetchall()
        for r in rtids:
            deleteTrade(r[0])
        cur.execute("select trades.rwid from trades join ptrades on trades.rwid = ptrades.tid where cid = %s",(cid,))
        ptids = cur.fetchall()
        for p in ptids:
            deleteTrade(p[0])
    return

def deleteTrade(tradeID, Accept=False):
    with mydb.db_cursor() as cur:
        if not Accept:
            cur.execute("select money from pmoney where tid = '%s'",(tradeID,))
            mb = cur.fetchone()[0]
            cur.execute("update users set gp = gp + '%s' where rwid = (SELECT pid from trades where rwid = '%s')",(mb, tradeID))
        cur.execute("delete from trades where rwid = '%s'",(tradeID,))
    return

def shopCards():
    with mydb.db_cursor() as cur:
        res = cur.execute("select shop.rwid, mons.cr, mons.name, mons.exp, shop.grade, shop.holo, shop.value"+
                          " from shop join mons on shop.monid = mons.rwid order by shop.rwid")
        return cur.fetchall()


def performTrade(uid, c1, c2):
    with mydb.db_cursor() as cur:
        cur.execute("select uid from collections where rwid = '%s'",(c1,))
        res = cur.fetchone()
        cur.execute("update collections set uid = '%s' where rwid = '%s'",(uid, c1))
        cur.execute("update collections set uid = '%s' where rwid = '%s'",(res[0],c2))
        cur.execute("delete from trades where mcardid = '%s' or wcardid = '%s' or mcardid = '%s' or wcardid = '%s'",(c1, c1, c2, c2))
    return

def addToShop(monid, grade, holo, value, av, colid):
    with mydb.db_cursor() as cur:
        cur.execute("insert into shop VALUES ('%s', '%s', '%s', '%s', '%s', '%s')",(monid, grade, holo, value, av, colid))
    return

def delShop():
    with mydb.db_cursor() as cur:
        cur.execute("delete from shop")
        cur.execute("select setval('public.shop_rwid_seq', 1, false)")
    return

def delFromShop(sid, did):
    with mydb.db_cursor() as cur:
        if int(sid) > 10:
            cur.execute("select colid from shop where rwid = %s",(sid,))
            tmp = cur.fetchone()[0]
            cur.execute("update collections set uid = '%s' where rwid = %s",(getUserID(did), tmp))
        cur.execute("delete from shop where rwid = %s",(sid,))
    return

def getOption(opt):
    with mydb.db_cursor() as cur:
        cur.execute("select value from options where key = %s", (opt,))
        return cur.fetchone()[0]

def getSoldCards():
    with mydb.db_cursor() as cur:
        cur.execute("select * FROM (SELECT DISTINCT ON (monid) * from collections where uid = 0)as a order by RANDOM() LIMIT 3")
        return cur.fetchall()

def getShopCard(sid):
    with mydb.db_cursor() as cur:
        cur.execute("select shop.rwid, mons.cr, mons.name, mons.exp, shop.grade, shop.holo, shop.value, shop.av, mons.rwid"+
                    " from shop join mons on shop.monid = mons.rwid where shop.rwid = %s", (sid,))
        return cur.fetchone()

def hasSets():
    with mydb.db_cursor() as cur:
        cur.execute("select setid, count(cardsinsets.rwid), sets.role from cardsinsets join sets on cardsinsets.setid = sets.rwid"+
                    " group by (setid, role)")
        sets = cur.fetchall()
        out = {}
        for s in sets:
            out[s[2]] = []
            cur.execute("select did, count(distinct(monid)) from collections join users on collections.uid = users.rwid where monid"+
                        " in (select monid from cardsinsets where setid = '%s') and users.rwid > 0 group by (did)", (s[0],))
            tmp = cur.fetchall()
            for t in tmp:
                if int(s[1]) == int(t[1]):
                    out[s[2]].append(t[0])
        return out

def addToCS(did, s):
    with mydb.db_cursor() as cur:
        cur.execute("insert into completedSets values(%s,%s)",(s,did))
    return

def delFromCS(did, s):
    with mydb.db_cursor() as cur:
        cur.execute("delete from completedSets where setName = %s and did = %s",(s, did))
    return

def getCompletedSets():
    with mydb.db_cursor() as cur:
        cur.execute("select * from completedSets")
        return cur.fetchall()

def getTreasureChance(name):
    with mydb.db_cursor() as cur:
        cur.execute("select cr from mons where name = %s",(name,))
        cr = cur.fetchone()[0]
        cur.execute("select cr, count(cr) from mons where cr = %s group by cr",(cr,))
        return cur.fetchone()

def getTreasure(cr):
    with mydb.db_cursor() as cur:
        cur.execute("select * from treasures where cr = %s",(cr,))
        return cur.fetchone()


def addTreasure(uid, t):
    with mydb.db_cursor() as cur:
        cur.execute("insert into eventTreasures values(%s,%s)",(uid,t))
    return

def buyCards(did, cids):
    with mydb.db_cursor() as cur:
        for c in cids:
            cur.execute("update collections set uid = (SELECT rwid from users where did = %s) where rwid = %s", (did, c))
    return
            
def generate_lotto(did, amount):
    with mydb.db_cursor() as cur:
        tmp = random.sample(range(0,10000), amount)
        for x in tmp:
            ticket = ','.join(list("{:04d}".format(x)))
            cur.execute("insert into lotto values(%s,%s)", (did, ticket))
        return

def jackpot():
    with mydb.db_cursor() as cur:
        cur.execute("SELECT * from jackpot")
        return cur.fetchone()[0]

async def execute_lotto(bot):
    with mydb.db_cursor() as cur:
        cur.execute("SELECT exec from exec_lotto")
        exe = cur.fetchone()[0]
        if exe:
            tmp = random.sample(range(0,10000), 1)
            num = list("{:04d}".format(tmp[0]))
            cur.execute("SELECT * FROM lotto")
            tmp = cur.fetchall()
            d = dict()
            flag = False
            for t in tmp:
                matches = sum(c1 == c2 for c1, c2 in zip(num, t[1].split(',')))
                if matches == 4:
                    flag = True
                    cur.execute("INSERT INTO jackpot_winners values (%s)", (t[0],))
                elif matches == 3:
                    amount = 2000
                elif matches == 2:
                    amount = 80
                elif matches == 1:
                    amount = 5
                if matches > 0 and matches != 4:
                    cur.execute("UPDATE users set gp = gp + %s where did = %s", (amount, t[0]))
                    if t[0] in d:
                        d[t[0]] += amount
                    else:
                        d[t[0]] = amount
            winners = []
            if flag:
                cur.execute("SELECT * from jackpot_winners")
                winners = cur.fetchall()
                c = len(winners)
                jp = jackpot()
                for w in winners:
                    cur.execute("UPDATE users set gp = gp + %s where did = %s", (jp / c, w[0]))
                cur.execute("UPDATE jackpot set amount = 40000")
            else:
                add = len(tmp) * 2.5
                cur.execute("UPDATE jackpot set amount = amount + %s", (add,))
            cur.execute("DELETE FROM jackpot_winners")
            cur.execute("DELETE FROM lotto")
            cur.execute("UPDATE exec_lotto set exec = FALSE")
            lc = bot.get_channel(int(getOption('lottoChannel')))
            await lc.send("The winning numbers were {}".format('-'.join(num)), delete_after=604700)
            if flag:
                jp_msg = "WE HAVE A WINNER\nThe following individual(s) have each won {}gp:\n".format(jp /c)
                for w in winners:
                    jp_msg += "{}\n".format(getUserName(w)[0], delete_after=604700)
                await lc.send(jp_msg)
            else:
                await lc.send("There were no Jackpot Winners", delete_after=604700)
            if d:
                win_msg = "The following have won:\n"
                for x in d:
                    win_msg += "{} has won {}gp\n".format(getUserName(x)[0], d[x])
                await lc.send(win_msg, delete_after=604700)
            else:
                await lc.send("No winners today", delete_after=604700)

def update_lotto():
    with mydb.db_cursor() as cur:
        cur.execute("UPDATE exec_lotto set exec = TRUE")
    
def addWager(uid, team, wager):
    spendGold(uid, wager)
    with mydb.db_cursor() as cur:
        cur.execute("INSERT into wager values (%s, %s, %s)", (uid, team, wager))

def resolveWager(team):
    tmp = []
    with mydb.db_cursor() as cur:
        cur.execute("SELECT uid, wager FROM wager WHERE team = %s", (team,))
        try:
            tmp = cur.fetchall()
        except:
            pass
        cur.execute("DELETE FROM wager")
    for t in tmp:
        spendGold(t[0], t[1] * -1.8)

            


