#from svmutil import *
import sklearn.ensemble
import numpy as np
import scipy as sp
import random
from scipy import stats
from collections import Counter
import sys
import time

np.set_printoptions(precision=4)

def normalize(mat):
    m = np.shape(mat)[0]
    n = np.shape(mat)[1]
    normed = mat
    for i in range(0,n):
        mint = min(mat[:,i])
        maxt = max(mat[:,i])
        for j in range(0,m):
            normed[j][i] = (mat[j][i] - mint)/(maxt - mint);
    return normed

def getdata(ID):
    data = np.loadtxt('PitcherFiles/' + str(ID) + 'normd.txt')
    return data

def getpitches(ID):
    pitches = np.loadtxt('PitcherFiles/' + str(ID) + 'p.txt',dtype='int')
    return pitches

"""def getweights(num):
    w = np.loadtxt('PitcherFiles/weights.txt')
    weights = w[range(num*10,num*10 + 10)]
    return weights

def makesvm(p,d,w):
    param = svm_parameter('-q')
    param.C = w[0]
    param.gamma = w[1]
    prob = svm_problem(p,d)
    svmout = svm_train(prob,param)
    return svmout"""

def randrange(list):
    a = min(list)
    b = max(list)
    r = random.uniform(a,b)
    return r

def errormat(out,actual):
    error = np.zeros([5,5])
    for i in range(0,len(out)):
        for j in range(1,6):
            if actual[i] == j:
                if out[i] == 1:
                    error[j-1,0] += 1
                elif out[i] == 2:
                    error[j-1,1] += 1
                elif out[i] == 3:
                    error[j-1,2] += 1
                elif out[i] == 4:
                    error[j-1,3] += 1
                elif out[i] == 5:
                    error[j-1,4] += 1
    return error

def getcount(pitches):

    count = np.zeros([5,1])

    for i in range(0,len(pitches)):
        if pitches[i] == 1:
            count[0] += 1
        elif pitches[i] == 2:
            count[1] += 1
        elif pitches[i] == 3:
            count[2] += 1
        elif pitches[i] == 4:
            count[3] += 1
        elif pitches[i] == 5:
            count[4] += 1

    count = count/len(pitches)

    return count

#print sys.argv[1]

predcount = np.zeros([11,110])
errorMats = np.zeros([550,5])
times = np.zeros([110,1])

for num in range(0,110):
    
    start = time.clock()
    
    tp = np.zeros([11,1])

    #num = int(sys.argv[1])

    ID = np.loadtxt('PitcherFiles/IDs.txt',dtype='int')[num]
    #ID = IDs[num]
    normdata = getdata(ID)
    pitches = getpitches(ID)
    #weights = getweights(num)
    cutoff = np.loadtxt('PitcherFiles/cutoffs.txt',dtype='int')[num]
    cutoff2 = np.loadtxt('PitcherFiles/cutoff2.txt',dtype='int')[num]

    #normdata = normalize(data)
    traindata = normdata[range(0,cutoff)]
    trainpitch = pitches[range(0,cutoff)]
    testdata = normdata[range(cutoff,len(pitches))]
    testpitch = pitches[range(cutoff,len(pitches))]

    tp[0:5] = getcount(trainpitch)
    tp[5:10] = getcount(testpitch)

    print ID

    preds = np.zeros([len(testpitch),10])

    for i in range(0,10):
        clf = sklearn.ensemble.ExtraTreesClassifier(n_estimators=100)
        #clf = sklearn.ensemble.ExtraTreesClassifier(n_estimators=500)
        #clf = sklearn.ensemble.RandomForestClassifier(n_estimators=500)
        clf = clf.fit(traindata.tolist(),trainpitch.tolist())
        preds[:,i] = clf.predict(testdata.tolist())#[0]

    out = np.zeros([len(testpitch),1])

    for i in range(0,len(testpitch)):
        temp = preds[i]
        flag = 0
        count = 0
        t1 = Counter(temp).values()
        check = t1.count(max(t1))
        while(flag == 0):
            if (check > 1):
                clf2 = sklearn.ensemble.ExtraTreesClassifier(n_estimators=100)
                #clf2 = sklearn.ensemble.ExtraTreesClassifier(n_estimators=500)
                #clf2 = sklearn.ensemble.RandomForestClassifier(n_estimators=500)
                clf2 = clf2.fit(traindata.tolist(),trainpitch.tolist())
                p = clf.predict([testdata[i].tolist(),testdata[i].tolist()])[0]

                temp = list(temp)
                temp.append(p)
                t1 = Counter(temp).items()
                check = t1.count(max(t1))
                count += 1
                if(check == 1):
                    #print "tie broken with %d extras" % count
                    flag = 1
            else:
                flag = 1

        out[i] = stats.mode(temp)[0]

    error = errormat(out,testpitch)

    errorMats[num*5:(num+1)*5,:] = error[:,:]

    print error

    corr = 0

    for i in range(0,5):
        corr = corr + error[i,i]

    percent = 100*(corr/len(out))
    
    tp[10] = percent
    
    predcount[:,num] = tp[:,0]

    print tp
    
    times[num] = time.clock() - start

    print time.clock() - start


    np.savetxt('DTpredcSmall.txt',predcount,'%5.6f')
    np.savetxt('DTtimesSmall.txt',times)
    np.savetxt('DTerrMatSmall.txt',errorMats,'%i')



