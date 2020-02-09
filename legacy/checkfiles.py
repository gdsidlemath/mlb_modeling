from __future__ import division
from scipy import stats
import numpy as np
import cPickle as pickle
from definedataclass import GamePitchData
import sys
import math

with open('MLBDataJuly2016.pkl','rb') as input:
    Data1 = pickle.load(input)

for i in range(0,100):
    print [Data1.Inning[i],Data1.outpitch[i],Data1.nasty[i],Data1.outenspd[i],Data1.res_des[i]]

