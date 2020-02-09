from __future__ import division
from scipy import stats
import numpy as np
import cPickle as pickle
from definedataclass import GamePitchData
import sys
import math
import time
from functools import reduce

np.set_printoptions(precision=3)

def fixstand(stand):
    if 'R' in stand:
        ost = 1
    else:
        ost = 0
    return ost

def getcount(pitches):

    count = np.zeros([6,1])
    for i in range(0,6):
        count[i] = len(np.where(pitches == i+1)[0])

    if len(pitches) > 0:
        return np.ceil(10000*count.T/np.sum(count))/10000
    else:
        return count.T


def eventscore(event):
    if 'Strikeout' in event or 'Strikeout - DP' in event:
        esc = 1
    elif 'Pop Out' in event or 'Groundout' in event or 'Grounded Into D' in event or 'Flyout' in event or 'Fielders Choice' in event or 'Bunt Pop Out' in event or 'Bunt Groundout' in event or 'Double Play' in event or 'Forceout' in event:
        esc = 2
    elif 'Sac Bunt' in event or 'Sac Fly' in event or 'Sacrifice Bunt ' in event or 'Lineout' in event or 'Sac Fly DP' in event or 'Field Error' in event:
        esc = 3
    elif 'Intent Walk' in event or 'Single' in event:
        esc = 4
    elif 'Hit By Pitch' in event or 'Double' in event or 'Triple' in event or 'Walk' in event:
        esc = 5
    elif 'Home Run' in event:
        esc = 6
    elif '0' in event:
        esc = 0
    else:
        esc = 3
    return esc
    
def desscore(des):
    if 'In play, no out' in des or 'Hit By Pitch' in des or 'In play, run(s)' in des or 'In play, out(s)' in des:
        dsc = 1
        
    elif 'Ball' in des or 'Automatic Ball'in des or 'Ball In Dirt' in des:
        dsc = 2
        
    elif 'Foul' in des or 'Foul (Runner Going)' in des or 'Foul Bunt' in des or 'Foul Pitchout' in des or 'Foul Tip' in des or 'Intent Ball' in des or 'Pitchout' in des:
        dsc = 3
        
    elif 'Called Strike' in des or 'Missed Bunt' in des or 'Swinging Pitchout' in des or 'Swinging Strike' in des or 'Swinging Strike (Blocked)' in des:
        dsc = 4

    elif '0' in des:
        dsc = 0
    else:
        dsc = 3
    return dsc

def destoballsstrikes(desall):
    #print 'deslength ' + str(len(desall))
    if type(desall) == str:
        des = desall
        if 'In play, no out' in des or 'In play, run(s)' in des or 'In play, out(s)' in des:
                bs = 'X'
        elif 'Ball' in des or 'Automatic Ball' in des or 'Ball In Dirt' in des or 'Hit By Pitch' in des or 'Intent Ball' in des or 'Pitchout' in des:
            bs = 'B'
        elif '0' in des:
            bs = '0'
        else:
            bs = 'S'
    else:
        bs = np.empty([len(desall),1],dtype=str)
        bs[:] = 'S'
        Xinds = np.concatenate((np.asarray(np.where(desall == 'In play, no out')[0]),np.asarray(np.where(desall == 'In play, run(s)')[0]),np.asarray(np.where(desall == 'In play, out(s)')[0])))
        Binds = np.concatenate((np.asarray(np.where(desall == 'Ball')[0]),np.asarray(np.where(desall == 'Automatic Ball')[0]),np.asarray(np.where(desall == 'Ball in Dirt')[0]),np.asarray(np.where(desall == 'Hit By Pitch')[0]),np.asarray(np.where(desall == 'Intent Ball')[0]),np.asarray(np.where(desall == 'Pitchout')[0])))
        Zinds = np.asarray(np.where(desall == '0'))
        bs[Binds] = 'B'
        bs[Xinds] = 'X'
        bs[Zinds] = '0'

    """else:
        bs = np.empty([len(desall),1],dtype=str)
        for i in range(0,len(desall)):
            des = desall[i]
            if 'In play, no out' in des or 'In play, run(s)' in des or 'In play, out(s)' in des:
                bs[i] = 'X'
            elif 'Ball' in des or 'Automatic Ball' in des or 'Ball In Dirt' in des or 'Hit By Pitch' in des or 'Intent Ball' in des or 'Pitchout' in des:
                bs[i] = 'B'
            elif '0' in des:
                bs[i] = '0'
            else:
                bs[i] = 'S'"""
    return bs
    
def pitchscore(pitchall):
    #print len(pitchall)
    if type(pitchall) == str:
        pitch = pitchall
        #pt = np.zeros([1,1])
        if 'FA' in pitch or 'FF' in pitch or 'FT' in pitch or 'FC' in pitch or 'FS' in pitch or 'SF' in pitch:
                pt=1
        elif 'SI' in pitch:
            pt=2
        elif 'SL' in pitch:
            pt=3
        elif 'CH' in pitch:
            pt=5
        elif 'CB' in pitch or 'CU' in pitch or 'KC' in pitch or 'SC' in pitch:
            pt=4
        elif 'KN' in pitch or 'EP' in pitch:
            pt = 6
        elif '0' in pitch:
            pt = 0
        else:
            pt=-1
    else:
        pt = np.zeros([len(pitchall),1])
        pt = pt - np.ones([len(pitchall),1])
        pitches = pitchall
        FBinds = np.concatenate((np.asarray(np.where(pitches == 'FA')[0]),np.asarray(np.where(pitches == 'FF')[0]),np.asarray(np.where(pitches == 'FT')[0]) ,np.asarray(np.where(pitches == 'FC')[0]),np.asarray(np.where(pitches == 'FS')[0]),np.asarray(np.where(pitches == 'SF')[0])))
        SIinds = np.asarray(np.where(pitches == 'SI'))
        SLinds = np.asarray(np.where(pitches == 'SL'))
        CBinds = np.concatenate((np.asarray(np.where(pitches == 'CU')[0]),np.asarray(np.where(pitches == 'KC')[0]),np.asarray(np.where(pitches == 'SC')[0])))
        CHinds = np.asarray(np.where(pitches == 'CH'))
        KNinds = np.concatenate((np.asarray(np.where(pitches == 'KN')[0]),np.asarray(np.where(pitches == 'EP')[0])))
        Zinds = np.asarray(np.where(pitches == '0'))
        pt[FBinds] = 1
        pt[SIinds] = 2
        pt[SLinds] = 3
        pt[CBinds] = 4
        pt[CHinds] = 5
        pt[KNinds] = 6
        pt[Zinds] = 0
    return pt

def timeofday(tp,gid):
    gid = str(gid)
    ht = int(gid[10:12])
    if ht == 2 or ht == 10:
        adj = 6
    elif ht == 6 or ht == 7 or ht == 12 or ht == 13 or ht == 16 or ht == 17 or ht == 26:
        adj = 5
    elif ht == 1 or ht == 14 or ht == 20 or ht == 23 or ht == 24 or ht == 25:
        adj = 7
    else:
        adj = 4
    newt = (tp - adj*10000)/10000

    if newt > 9 and newt < 17:
        td = 1
    elif newt >= 17 and newt < 20:
        td = 2
    else:
        td = 3
    return td

def strikesballs(typebs):
    zInds = [i for i,s in enumerate(typebs) if '0' in s]
    zInds.append(len(typebs))
    ballcount = [0]; strikecount = [0]
    cnt = 0
    #print zInds
    for i in range(1,len(typebs)):
        #try:
        if i == zInds[cnt+1]:
            cnt += 1
            ballcount.append(0)
            strikecount.append(0)
        else:
            st = zInds[cnt]
            temp = typebs[st:i+1]
            bctemp = len([k for k,s in enumerate(temp) if 'B' in s])
            if bctemp > 3:
                ballcount.append(3)
            else:
                ballcount.append(bctemp)
            sctemp = len([p for p,s in enumerate(temp) if 'S' in s])
            if sctemp > 2:
                strikecount.append(2)
            else:
                strikecount.append(sctemp)

    return (ballcount,strikecount)

def getplaceinorder(abn):
    if abn < 10:
        ord = abn % 10
    elif abn % 9 == 0:
        ord = 9
    else:
        ord = abn % 9
    return ord

def findInds(lst,thing):
    if isinstance(lst[0],str):
        inds = [i for i,s in enumerate(lst) if thing in s]
    else:
        inds = [i for i,s in enumerate([str(x) for x in lst]) if thing in s]
    return inds

def gamepreturn(pitches,strikes,gameinds,batinds,battot,bcount,scount):
    outmat = np.zeros([len(pitches),42])
    bmat = np.zeros([len(pitches),6])
    countmat = np.zeros([len(pitches),6])
    for i in range(1,len(pitches)):
        bspot = sorted(set(battot)).index(battot[i])
        cbinds = batinds[bspot]
        bmat[i,:] = getcount(pitches[np.intersect1d(range(0,i),cbinds)])
    
        btemp = int(bcount[i]); stemp = int(scount[i])
        ctinds = reduce(np.intersect1d,(range(0,i),np.where(bcount == btemp)[0],np.where(scount == stemp)[0]))
    
        countmat[i,:] = getcount(pitches[ctinds])

    for game in gameinds:
        for i in range(1,len(game)):
            if i < 5:
                temp1 = getcount(pitches[game[0:i]])
                temp1s = getcount(pitches[np.intersect1d(game[0:i],strikes)])
            else:
                temp1 = getcount(pitches[game[i-5:i]])
                temp1s = getcount(pitches[np.intersect1d(game[i-5:i],strikes)])
            if i < 10:
                temp2 = getcount(pitches[game[0:i]])
                temp2s = getcount(pitches[np.intersect1d(game[0:i],strikes)])
            else:
                temp2 = getcount(pitches[game[i-10:i]])
                temp2s = getcount(pitches[np.intersect1d(game[i-10:i],strikes)])
            if i < 20:
                temp3 = getcount(pitches[game[0:i]])
                temp3s = getcount(pitches[np.intersect1d(game[0:i],strikes)])
            else:
                temp3 = getcount(pitches[game[i-20:i]])
                temp3s = getcount(pitches[np.intersect1d(game[i-20:i],strikes)])
            
            #print [np.shape(temp1), np.shape(temp2), np.shape(temp3), np.shape(temp1s), np.shape(temp2s), np.shape(temp3s)]
            ovr = getcount(pitches[0:game[i]])
            outmat[game[i],:] = np.column_stack((temp1,temp2,temp3,temp1s,temp2s,temp3s,ovr))
    return np.column_stack((outmat,countmat,bmat))

def getbatterstats(bID,allbats,bpt,btypebs,pInd,strikes,balls,inplay):
    #st = time.clock()
    outmat = np.zeros([1,18])
    bInds = np.where(allbats == bID)[0]
    inds = np.where(np.asarray(bInds) < pInd)[0]
    
    try:
        temp1 = getcount(bpt[np.intersect1d(inds,inplay)])
    except TypeError:
        temp1 = np.zeros([1,6])
    try:
        temp2 = getcount(bpt[np.intersect1d(inds,strikes)])
    except TypeError:
        temp2 = np.zeros([1,6])
    try:
        temp3 = getcount(bpt[np.intersect1d(inds,balls)])
    except TypeError:
        temp3 = np.zeros([1,6])
    outmat = np.column_stack((temp1,temp2,temp3))

    return outmat
mainstart = time.clock()

pID = sys.argv[1]

print 'Loading...'

#with open('MLBData2010throughJul2014.pkl','rb') as input:
start = time.clock()
#with open('MLBData2010throughJun2016.pkl','rb') as input:
#with open('MLBData1011.pkl','rb') as input:
with open('MLBDataOD2010thruASB2016.pkl','rb') as input:
#with open('MLBDataJuly2016.pkl','rb') as input:
    Data = pickle.load(input)
print time.clock() - start

print 'Loaded'

print len(Data.Inning)

pInds = findInds(Data.pitcher,pID)

print len(pInds)

Inningp = []; abnp = []; spreadp = []; outsp = []; batterp = []; stancep = []; bheightp = []; eventp = []; res_eventp = []; desp = []; res_desp = []; pnump = []; typebsp = []; res_typebsp = []; timep = []; prevspp = []; breakyp = []; breakanglep = [];breaklengthp = []; on1p = []; on2p = []; on3p = []; pr_pitch_typep = []; pr_type_confp = []; nastyp = []; outpitchp = []; out_type_confp = []; outspdp = []; gidp = []; pr_zonep = []; cur_zonep = []; ordernum = []
num = 0

#destoballsstrikes(Data.res_des[0:3])

for i in pInds:
    num += 1
    Inningp.append(Data.Inning[i])
    abnp.append(Data.at_bat_num[i])
    spreadp.append(Data.spread[i])
    outsp.append(Data.outs[i])
    batterp.append(Data.batter[i])
    stancep.append(fixstand(Data.stance[i]))
    bheightp.append(Data.bheight[i])
    eventp.append(eventscore(Data.pr_event[i]))
    desp.append(desscore(Data.pr_des[i]))
    pnump.append(Data.pnum[i])
    typebsp.append(destoballsstrikes(Data.pr_des[i]))
    timep.append(timeofday(Data.tfs[i],Data.gameID[i]))
    prevspp.append(.5*(Data.stspd[i] + Data.endspd[i]))
    breakyp.append(Data.breaky[i])
    breakanglep.append(Data.breakangle[i])
    breaklengthp.append(Data.breaklength[i])
    on1p.append(Data.on1[i])
    on2p.append(Data.on2[i])
    on3p.append(Data.on3[i])
    pr_pitch_typep.append(pitchscore(Data.pr_pitch_type[i]))#[0])
    pr_type_confp.append(Data.pr_type_conf[i])
    nastyp.append(Data.nasty[i])
    outpitchp.append(pitchscore(Data.outpitch[i]))
    out_type_confp.append(Data.outc[i])
    outspdp.append(.5*(Data.outstspd[i] + Data.outenspd[i]))
    pr_zonep.append(Data.pr_zones[i])
    cur_zonep.append(Data.cur_zones[i])
    gidp.append(Data.gameID[i])
    res_eventp.append(eventscore(Data.res_event[i]))
    res_desp.append(desscore(Data.res_des[i]))
    res_typebsp.append(destoballsstrikes(Data.res_des[i]))#[0])
    ordernum.append(getplaceinorder(Data.at_bat_num[i]))

#print typebsp[0:100]
#print pr_pitch_typep[0:100]

tempprp = []
tempprz = []
tempsp = []; tempby = []; tempba = []; tempbl = []; tempn = []

for i in range(0,len(pInds)):
    #print[desp[i], typebsp[i], pr_pitch_typep[i], pr_zonep[i]]
    if desp[i] == 0 and '0' in typebsp[i]:
        tempprp.append(0)
        tempprz.append(0)
        tempsp.append(0)
        tempby.append(0)
        tempba.append(0)
        tempbl.append(0)
        tempn.append(0)
    elif desp[i] > 0 and '0' not in typebsp[i]:
        tempprp.append(outpitchp[i-1])
        tempprz.append(cur_zonep[i-1])
        tempsp.append(outspdp[i-1])
        tempby.append(breakyp[i-1])
        tempba.append(breakanglep[i-1])
        tempbl.append(breaklengthp[i-1])
        tempn.append(nastyp[i-1])
    else:
        tempprp.append(pr_pitch_typep[i])
        tempprz.append(pr_zonep[i])
        tempsp.append(prevspp[i])
        tempby.append(breakyp[i-1])
        tempba.append(breakanglep[i-1])
        tempbl.append(breaklengthp[i-1])
        tempn.append(nastyp[i-1])

goodpinds = []; ovrallinds = []
for j in range(0,len(outpitchp)):
    if outpitchp[j] == -1:
        continue
    else:
        goodpinds.append(j)
        ovrallinds.append(pInds[j])

Inninggood = []; abngood = []; spreadgood = []; outsgood = []; battergood = []; stancegood = []; bheightgood = []; eventgood = []; res_eventgood = []; desgood = []; res_desgood = []; pnumgood = []; typebsgood = []; res_typebsgood = []; timegood = []; prevspgood = []; breakygood = []; breakanglegood = [];breaklengthgood = []; on1good = []; on2good = []; on3good = []; pr_pitch_typegood = []; pr_type_confgood = []; nastygood = []; outpitchgood = []; out_type_confgood = []; outspdgood = []; gidgood = []; pr_zonegood = []; cur_zonegood = []; ordernumgood = []; bcountgood = []; scountgood = []; bscoregood = []

(bcount,scount) = strikesballs(typebsp)

print len(goodpinds)

for k in goodpinds:

    Inninggood.append(Inningp[k])
    abngood.append(abnp[k])
    spreadgood.append(spreadp[k])
    outsgood.append(outsp[k])
    battergood.append(batterp[k])
    stancegood.append(stancep[k])
    bheightgood.append(bheightp[k])
    eventgood.append(eventp[k])
    desgood.append(desp[k])
    pnumgood.append(pnump[k])
    typebsgood.append(typebsp[k])
    timegood.append(timep[k])
    prevspgood.append(math.ceil(1000*tempsp[k])/1000)
    breakygood.append(tempby[k])
    breakanglegood.append(tempba[k])
    breaklengthgood.append(tempbl[k])
    on1good.append(on1p[k])
    on2good.append(on2p[k])
    on3good.append(on3p[k])
    pr_pitch_typegood.append(tempprp[k])
    pr_type_confgood.append(pr_type_confp[k])
    nastygood.append(tempn[k])
    outpitchgood.append(outpitchp[k])
    out_type_confgood.append(out_type_confp[k])
    outspdgood.append(math.ceil(1000*outspdp[k])/1000)
    pr_zonegood.append(tempprz[k])
    cur_zonegood.append(cur_zonep[k])
    gidgood.append(gidp[k])
    res_eventgood.append(res_eventp[k])
    res_desgood.append(res_desp[k])
    res_typebsgood.append(res_typebsp[k])
    ordernumgood.append(ordernum[k])
    bcountgood.append(bcount[k])
    scountgood.append(scount[k])
    bscoregood.append(on1p[k] + 2*on2p[k] + 3*on3p[k])

gameindexes = [];
for i,game in enumerate(sorted(set(gidgood))):
    gameindexes.append(findInds(gidgood,str(game)))
batterindexes = [];
for i,bat in enumerate(sorted(set(battergood))):
    batterindexes.append(findInds(battergood,str(bat)))

#print len(batterindexes)
#print len(gameindexes)

yrcount = np.zeros([7,1])
for i in range(0,len(gidgood)):
    if gidgood[i] < 201100000000 and gidgood[i] > 201000000000:
        yrcount[0] += 1
    elif gidgood[i] < 201200000000 and gidgood[i] > 201100000000:
        yrcount[1] += 1
    elif gidgood[i] < 201300000000 and gidgood[i] > 201200000000:
        yrcount[2] += 1
    elif gidgood[i] < 201400000000 and gidgood[i] > 201300000000:
        yrcount[3] += 1
    elif gidgood[i] < 201500000000 and gidgood[i] > 201400000000:
        yrcount[4] += 1
    elif gidgood[i] < 201600000000 and gidgood[i] > 201500000000:
        yrcount[5] += 1
    elif gidgood[i] < 201700000000 and gidgood[i] > 201600000000:
        yrcount[6] += 1

#ti = np.asarray(tempinds)
newp = np.asarray(outpitchgood)

strikes = np.asarray([i for i,s in enumerate(res_typebsgood) if 'S' in s])
balls = np.asarray([i for i,s in enumerate(res_typebsgood) if 'B' in s])
inplay = np.asarray([i for i,s in enumerate(res_typebsgood) if 'X' in s])
bcountgood = np.asarray(bcountgood)
scountgood = np.asarray(scountgood)

#print [len(strikes), len(balls), len(inplay)]

#print reduce(np.intersect1d,(strikes,np.where(newp ==1)[0],np.where(np.asarray(cur_zonegood) == 5)[0]))

print getcount(newp)

#print len(newp[ti])

print yrcount

#print out_type_confgood

#print len(out_type_confgood((np.where(np.asarray(out_type_confgood) < .8))))

"""for i in range(0,30):
    print pDataMatrix[i,:]
    print pOutMatrix[i,:]"""

batmat = np.zeros([len(newp),18])

pitches = np.asarray(pitchscore(np.asarray(Data.outpitch)))
btypebs = np.asarray(destoballsstrikes(np.asarray(Data.res_des)))
bats = np.asarray(Data.batter)

s1 = np.asarray(np.where(btypebs == 'S')[0])#np.asarray([i for i,s in enumerate(btypebs) if 'S' in s])
b1 = np.asarray(np.where(btypebs == 'B')[0])#np.asarray([i for i,s in enumerate(btypebs) if 'B' in s])
ip1 = np.asarray(np.where(btypebs == 'X')[0])

print 'making batter data'
start = time.clock()
for i in range(0,len(newp)):
    #s = time.clock()
    batmat[i,:] = getbatterstats(battergood[i],bats,pitches,btypebs,ovrallinds[i],s1,b1,ip1)
    #print time.clock() - s
    #print i
    if i == yrcount[0]:
        print 'year 1 done'
    elif i == np.sum(yrcount[0:2]):
        print 'year 2 done'
    elif i == np.sum(yrcount[0:3]):
        print 'year 3 done'
    elif i == np.sum(yrcount[0:4]):
        print 'year 4 done'
    elif i == np.sum(yrcount[0:5]):
        print 'year 5 done'
    elif i == np.sum(yrcount[0:6]):
        print 'year 6 done'
    elif i == np.sum(yrcount):
        print 'done with batter'
print time.clock() - start

start = time.clock()
pDataMatrix = np.column_stack((np.column_stack((np.asarray(Inninggood), np.asarray(outsgood), np.asarray(ordernumgood), np.asarray(abngood), np.asarray(spreadgood), np.asarray(timegood), np.asarray(stancegood), np.asarray(bheightgood), np.asarray(bcountgood), np.asarray(scountgood), np.asarray(on1good), np.asarray(on2good), np.asarray(on3good), np.asarray(bscoregood), np.asarray(pnumgood), np.asarray(eventgood), np.asarray(desgood), np.asarray(pr_pitch_typegood), np.asarray(pr_zonegood), np.asarray(prevspgood), np.asarray(nastygood), np.asarray(breakygood), np.asarray(breakanglegood), np.asarray(breaklengthgood))),gamepreturn(newp,strikes,gameindexes,batterindexes,battergood,bcountgood,scountgood),batmat)) #, np.asarray(nastygood), np.asarray(breakygood), np.asarray(breakanglegood), np.asarray(breaklengthgood)))
print time.clock() - start

pOutMatrix = np.column_stack((np.asarray(outpitchgood), np.asarray(outspdgood), np.asarray(cur_zonegood), np.asarray(res_desgood)))

print [np.shape(pDataMatrix), np.shape(pOutMatrix)]

#print pDataMatrix[1053,:]

np.savetxt(str(pID) + 'DataFast.txt',pDataMatrix,'%5.6f')
np.savetxt(str(pID) + 'OutputsFast.txt',pOutMatrix,'%5.2f')

print 'Saved!'

print time.clock() - mainstart