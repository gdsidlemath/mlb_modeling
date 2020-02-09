from __future__ import division
from lxml import etree
from lxml import html
from bs4 import BeautifulSoup
from scipy import stats
import numpy as np
import requests
import re
import datetime
import cPickle as pickle
from definedataclass import GamePitchData
from definedataclass import PitchSpecs

def save_object(obj, filename):
    with open(filename, 'wb') as output:
        pickle.dump(obj, output, -1)

def getgameID(gid):
    teams = ['ana','nya','bal','cle','chn','was','det','cha','hou','tor','mia','col','mil','min','nyn','ari','oak','bos','pit','atl','sdn','cin','sfn','phi','sln','lan','tba','sea','tex','kca']
    teams.sort()
    myd = gid[4:8] + gid[9:11] + gid[12:14]
    ateam = gid[15:18]; hteam = gid[22:25]
    if 'flo' in ateam:
        ateam = 'mia'
    if 'flo' in hteam:
        hteam = 'mia'
    aspot = str([i for i,s in enumerate(teams) if ateam in s][0]+1)
    hspot = str([i for i,s in enumerate(teams) if hteam in s][0]+1)
    if len(aspot) < 2:
        aspot = '0' + aspot
    if len(hspot) < 2:
        hspot = '0' + hspot

    totstr = myd + aspot + hspot

    return int(totstr)

def getpitchspecs(url,gameID):
    page = requests.get(url)
    soup = BeautifulSoup(page.content,'lxml')
    table1 = soup.game.find_all('inning')

    nasty = []; breaky = []; breakangle = []; breaklength = []; gid = []; tfs = [];

    for inning in table1:
        table2 = inning.find_all('atbat')
        for atbat in table2:
            table3 = atbat.find_all('pitch')
            for pit in table3:
                
                try:
                    pitstr = str(pit)
                    tfsst = pitstr.index('tfs="') + len('tfs="'); tfsend = pitstr.index('"',tfsst)
                    tfstemp = pitstr[tfsst:tfsend]
                    stbkyt = pitstr.index('break_y="') + len('break_y="'); endbkyt = pitstr.index('"',stbkyt)
                    tempbky = pitstr[stbkyt:endbkyt]
                    stbkat = pitstr.index('break_angle="') + len('break_angle="'); endbkat = pitstr.index('"',stbkat)
                    tempbka = pitstr[stbkat:endbkat]
                    stbklt = pitstr.index('break_length="') + len('break_length="'); endbklt = pitstr.index('"',stbklt)
                    tempbkl = pitstr[stbklt:endbklt]
                    stnsty = pitstr.index('nasty="') + len('nasty="'); endnsty = pitstr.index('"',stnsty)
                    nstytemp = pitstr[stnsty:endnsty]

                    tfs.append(int(tfstemp))
                    breaky.append(float(tempbky))
                    breakangle.append(float(tempbka))
                    breaklength.append(float(tempbkl))
                    nasty.append(int(nstytemp))
                    gid.append(gameID)
                except ValueError:
                    continue

    allspecs = PitchSpecs(gid,tfs,nasty,breaky,breakangle,breaklength)

    return allspecs

def mergestruct(one,two):

    return PitchSpecs(one.gid + two.gid, one.tfs + two.tfs, one.nasty + two.nasty, one.breaky + two.breaky, one.breakangle + two.breakangle, one.breaklength + two.breaklength)

nasty = []; breaky = []; breakangle = []; breaklength = []; gid = []; tfs = [];

SpecData = PitchSpecs(gid,tfs,nasty,breaky,breakangle,breaklength)

now = datetime.datetime.now()

yrs = range(2010,now.year + 1)

"""for yr in yrs:
    if yr == 2011 or yr == 2013 or yr == 2014:
        months = range(3,11)
    elif yr == now.year:
        months = range(4,now.month)
    else:
        months = range(4,11)

    yr = str(yr)

    for month in months:
        if month == 3:
            days = [31]
        elif month == 4 and int(yr) == 2010:
            days = range(4,31)
        elif month == 4 and int(yr) == 2012:
            days = range(5,31)
        elif month == 4 and int(yr) == 2015:
            days = range(5,31)
        elif month == 4 and int(yr) == 2016:
            days = range(3,31)
        elif month == 6 or month == 9:
            days = range(1,31)
        elif month == now.month and int(yr) == now.year:
            days = range(1,now.day + 1)
        else:
            days = range(1,32)
        
        month = str(month)

        if len(month) < 2:
            month = '0' + month

        for day in days:

            day = str(day)

            if len(day) < 2:
                day = '0' + day

            url1 = 'http://gd2.mlb.com/components/game/mlb/year_' + yr + '/month_' + month + '/day_' + day + '/'

            url2 = 'inning/inning_all.xml'

            page = requests.get(url1)

            soup = BeautifulSoup(page.content,'lxml')

            table = soup.find_all('a',string=re.compile('gid'))

            lst = []

            for elem in table:
                elem = str(elem)
                start = elem.index('"') + len('"')
                end = elem.index('"',start)
                lst.append(elem[start:end])

            for game in lst:
                
                try:
                
                    #print game
                    
                    name = getgameID(game)

                    url = url1 + game + url2
                    
                    #temp = getpitchspecs(url,name)

                    SpecData = mergestruct(SpecData,getpitchspecs(url,name))

                    
                    #save_object(BaseballData,'MLBData2010throughNow.pkl')

                except (IndexError,AttributeError,ValueError):
                    continue


            print yr + ' ' + month + ' ' + day + ' done.'

        save_object(SpecData,'PitchSpecs2010throughNow.pkl')"""

def loadindata():

    with open('PitchSpecs2010throughNow.pkl','rb') as input:
        D1 = pickle.load(input)
    
    print 'specs loaded'

    print 'Specs: ' + str(len(D1.breaky))

    with open('MLBData2010throughJun2016.pkl','rb') as input:
    #with open('MLBDataAug2014throughApril2015.pkl','rb') as input:
        D2 = pickle.load(input)

    print 'other stuff loaded'

    print len(D2.gameID)

    return (D1,D2)

def trytosave(D1,D2):

    pgids = []

    for i in range(0,len(D1.breaky)):
        pgids.append(str(D1.gid[i]) + str(D1.tfs[i]))
    
    pgids = np.asarray(pgids)
    
    print len(pgids)

    ovrginds = []

    for i in range(0,len(D2.gameID)):
        ovrginds.append(str(D2.gameID[i]) + str(D2.tfs[i]))

    ovrginds = np.asarray(ovrginds)

    print len(ovrginds)

    print len(D2.breaky)

    print len(D2.outpitch)

    """x = np.asarray([1, 2, 3, 4, 5, 4, 6, 7, 8, 9, 2, 10])
    y = np.asarray([1, 2, 2, 3, 5, 4, 3, 7, 8, 9])
    
    print x
    print y
    
    print len(np.in1d(x,y).nonzero()[0])
    print len(np.in1d(y,x).nonzero()[0])
    
    print np.intersect1d(x,y)
    print np.intersect1d(y,x)
    
    nx, indx = np.unique(x, return_index=True)
    ny, indy = np.unique(y, return_index=True)
    
    print [nx,indx]
    print [ny,indy]"""

    #nsp,nspind = np.unique(np.asarray(pgids), return_index =True)
    """novr,noind = np.unique(ovrginds, return_index=True)
    
    #print len(np.asarray(np.in1d(np.asarray(ovrginds),np.asarray(pgids)).nonzero()[0]))
    
    #print len(np.asarray(np.in1d(nsp,novr).nonzero()[0]))

    print len(np.in1d(ovrginds,pgids).nonzero()[0])
    
    inds = np.in1d(pgids,ovrginds,invert=True).nonzero()[0]

    inds2 = np.in1d(pgids,inds,invert=True).nonzero()[0]

    print ovrginds[18:24]

    print pgids[18:24]

    print inds
    
    print len(inds)

    print len(inds2)

    #oginds = np.asarray(range(0,len(ovrginds)))
    #opinds = np.asarray(range(0,len(pgids)))
    #ovrinds = oginds[np.asarray(noind)]
    #pinds = opinds[np.asarray(nspind[np.asarray(np.in1d(nsp,novr).nonzero()[0])])]

    #print len(oginds)
    
    #print len(opinds)

    #print len(pinds)

    #print len(ovrinds)
    
    #print np.intersect1d(np.asarray(pgids),np.asarray(ovrginds)))
    
    #print np.where(np.char.find(ovrginds,ovrginds) > -1)[0][190:210]"""

    """gameID = []; Inning = []; at_bat_num = []; spread = []; outs = []; batter = []; stance = []; bheight = []; pitcher = []; pthrows = []; event = []; des = []; pnum = []; typebs = []; tfs = []; stspd = []; endspd = []; sztop = []; szbot = []; breaky = []; breakangle = []; breaklength = []; on1 = []; on2 = []; on3 = []; pr_pitch_type = []; pr_type_conf = []; nasty = []; outpitch = []; out_type_conf = []; outx = []; outy = []; outstspd = []; outenspd = []; pr_zones = []; cur_zones = []; res_event = []; res_des = []; res_typebs = [];

    k = 0
    while k < len(ovrginds):
        print 'k =' + str(k)
        #print np.where(np.char.find(pgids,ovrginds[k]) > -1)
        #int(np.where(np.char.find(ovrginds,k) > -1)[0][0])
        temp = len(np.where(np.char.find(ovrginds,ovrginds[k]) > -1)[0])
        print temp
        if temp > 1:
            print 'in 1'
            m = 0
            while m < temp:
                #print np.where(np.char.find(pgids,ovrginds[k]) > -1)[0]
                j = int(np.where(np.char.find(pgids,ovrginds[k]) > -1)[0][m])
                i = k
                gameID.append(D2.gameID[i]); Inning.append(D2.Inning[i]); at_bat_num.append(D2.at_bat_num[i]); spread.append(D2.spread[i]); outs.append(D2.outs[i]); batter.append(D2.batter[i]); stance.append(D2.stance[i]); bheight.append(D2.bheight[i]); pitcher.append(D2.pitcher[i]); pthrows.append(D2.pthrows[i]); event.append(D2.pr_event[i]); des.append(D2.pr_des[i]); pnum.append(D2.pnum[i]); typebs.append(D2.typebs[i]); tfs.append(D2.tfs[i]); stspd.append(D2.stspd[i]); endspd.append(D2.endspd[i]); sztop.append(D2.sztop[i]); szbot.append(D2.szbot[i]); breaky.append(D1.breaky[j]); breakangle.append(D1.breakangle[j]); breaklength.append(D1.breaklength[j]); on1.append(D2.on1[i]); on2.append(D2.on2[i]); on3.append(D2.on3[i]); pr_pitch_type.append(D2.pr_pitch_type[i]); pr_type_conf.append(D2.pr_type_conf[i]); nasty.append(D1.nasty[j]); outpitch.append(D2.outpitch[i]); out_type_conf.append(D2.outc[i]); outx.append(D2.outx[i]); outy.append(D2.outy[i]); outstspd.append(D2.outstspd[i]); outenspd.append(D2.outenspd[i]); pr_zones.append(D2.pr_zones[i]); cur_zones.append(D2.cur_zones[i]); res_event.append(D2.res_event[i]); res_des.append(D2.res_des[i]); res_typebs.append(D2.res_typebs[i]);
                if len(np.where(np.char.find(ovrginds,ovrginds[k+1]) > -1)[0]) == temp:
                    m+=1
                    k+= 1
                else:
                    m = temp + 1
                    k+= 1
                print 'm = ' + str(m)
                print 'k = ' + str(m)
            continue
        else:
            print 'in 2'
            #print np.where(np.char.find(pgids,ovrginds[k]) > -1)
            j = int(np.where(np.char.find(pgids,ovrginds[k]) > -1)[0])
            #print j
            i = k
            #print i
            gameID.append(D2.gameID[i]); Inning.append(D2.Inning[i]); at_bat_num.append(D2.at_bat_num[i]); spread.append(D2.spread[i]); outs.append(D2.outs[i]); batter.append(D2.batter[i]); stance.append(D2.stance[i]); bheight.append(D2.bheight[i]); pitcher.append(D2.pitcher[i]); pthrows.append(D2.pthrows[i]); event.append(D2.pr_event[i]); des.append(D2.pr_des[i]); pnum.append(D2.pnum[i]); typebs.append(D2.typebs[i]); tfs.append(D2.tfs[i]); stspd.append(D2.stspd[i]); endspd.append(D2.endspd[i]); sztop.append(D2.sztop[i]); szbot.append(D2.szbot[i]); breaky.append(D1.breaky[j]); breakangle.append(D1.breakangle[j]); breaklength.append(D1.breaklength[j]); on1.append(D2.on1[i]); on2.append(D2.on2[i]); on3.append(D2.on3[i]); pr_pitch_type.append(D2.pr_pitch_type[i]); pr_type_conf.append(D2.pr_type_conf[i]); nasty.append(D1.nasty[j]); outpitch.append(D2.outpitch[i]); out_type_conf.append(D2.outc[i]); outx.append(D2.outx[i]); outy.append(D2.outy[i]); outstspd.append(D2.outstspd[i]); outenspd.append(D2.outenspd[i]); pr_zones.append(D2.pr_zones[i]); cur_zones.append(D2.cur_zones[i]); res_event.append(D2.res_event[i]); res_des.append(D2.res_des[i]); res_typebs.append(D2.res_typebs[i]);
            k+=1
            print 'k = ' + str(k)"""
    
    """gameID = np.asarray(D2.gameID); Inning = np.asarray(D2.Inning); at_bat_num = np.asarray(D2.at_bat_num); spread = np.asarray(D2.spread); outs = np.asarray(D2.outs); batter = np.asarray(D2.batter); stance = np.asarray(D2.stance); bheight = np.asarray(D2.bheight); pitcher = np.asarray(D2.pitcher); pthrows = np.asarray(D2.pthrows); event = np.asarray(D2.pr_event); des = np.asarray(D2.pr_des); pnum = np.asarray(D2.pnum); typebs = np.asarray(D2.typebs); tfs = np.asarray(D2.tfs); stspd = np.asarray(D2.stspd); endspd = np.asarray(D2.endspd); sztop = np.asarray(D2.sztop); szbot = np.asarray(D2.szbot); breaky = np.asarray(np.asarray(D1.breaky)[inds]); breakangle = np.asarray(np.asarray(D1.breakangle)[inds]); breaklength = np.asarray(np.asarray(D1.breaklength)[inds]); on1 = np.asarray(D2.on1); on2 = np.asarray(D2.on2); on3 = np.asarray(D2.on3); pr_pitch_type = np.asarray(D2.pr_pitch_type); pr_type_conf = np.asarray(D2.pr_type_conf); nasty = np.asarray(np.asarray(D1.nasty)[inds]); outpitch = np.asarray(D2.outpitch); out_type_conf = np.asarray(D2.outc); outx = np.asarray(D2.outx); outy = np.asarray(D2.outy); outstspd = np.asarray(D2.outstspd); outenspd = np.asarray(D2.outenspd); pr_zones = np.asarray(D2.pr_zones); cur_zones = np.asarray(D2.cur_zones); res_event = np.asarray(D2.res_event); res_des = np.asarray(D2.res_des); res_typebs = np.asarray(D2.res_typebs);


    NewGameData = GamePitchData(gameID,Inning,at_bat_num,spread,outs,batter,bheight,stance,pitcher,pthrows,event,res_event,des,res_des,pnum,typebs,res_typebs,tfs,stspd,endspd,sztop,szbot,breaky,breakangle,breaklength,on1,on2,on3,pr_pitch_type,pr_type_conf,nasty,outpitch,out_type_conf,outx,outy,outstspd,outenspd,pr_zones,cur_zones)

    
    print NewGameData.Inning[0:300]
    print NewGame.pnum[0:300]

    print len(NewGameData.outpitch)

    save_object(NewGameData,'MLBPitchesOD2010thruJun2016Attempt.pkl')

    print 'Saved!'"""

#(D1,D2) = loadindata()

#trytosave(D1,D2)
