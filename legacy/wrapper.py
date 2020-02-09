from __future__ import division
import sys
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
import getpitchspecs as mainscript

part1Cache = None
if __name__ == '__main__':
    while True:
        if not part1Cache:
            (part1Cache,D2) = mainscript.loadindata()
        try:
            mainscript.trytosave(part1Cache,D2)
            print 'Press enter to re-run the script, CTRL-C to exit'
            sys.stdin.readline()
            reload(mainscript)
        except Exception as e:
            print e
            print 'Press enter to re-run the script, CTRL-C to exit'
            sys.stdin.readline()
            reload(mainscript)