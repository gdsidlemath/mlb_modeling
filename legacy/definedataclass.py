class GamePitchData(object):

    def __init__(self,gameID,Inning,at_bat_num,spread,outs,batter,bheight,stance,pitcher,pthrows,pr_event,res_event,pr_des,res_des,pnum,typebs,res_typebs,tfs,sztop,szbot,breaky,breakangle,breaklength,on1,on2,on3,nasty,outpitch,outc,outx,outy,outstspd,outenspd,cur_zones):
        
        self.Inning = Inning; self.at_bat_num = at_bat_num; self.spread = spread; self.outs = outs; self.batter = batter; self.bheight = bheight; self.stance = stance; self.pitcher = pitcher; self.pthrows = pthrows; self.pr_event = pr_event; self.pr_des = pr_des; self.typebs = typebs; self.res_typebs = res_typebs; self.tfs = tfs; self.sztop = sztop; self.szbot = szbot; self.breaky = breaky; self.breakangle = breakangle; self.breaklength = breaklength; self.on1 = on1; self.on2 = on2; self.on3 = on3; self.nasty = nasty; self.outpitch = outpitch; self.outc = outc; self.pnum = pnum; self.outx = outx; self.outy = outy; self.outstspd = outstspd; self.outenspd = outenspd; self.cur_zones = cur_zones; self.gameID = gameID; self.res_event = res_event; self.res_des = res_des;

class PitchSpecs(object):

    def __init__(self,gid,tfs,nasty,breaky,breakangle,breaklength):
        self.gid = gid; self.tfs = tfs; self.nasty = nasty; self.breaky = breaky; self.breakangle = breakangle; self.breaklength = breaklength