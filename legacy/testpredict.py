from svmutil import *
import sklearn.ensemble
import sklearn.tree
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
    data = np.loadtxt('PitcherData/' + str(ID) + 'Data2014.txt')
    #data = np.loadtxt('PitcherFiles/' + str(ID) + 'normd.txt')
    return data

def getpitches(ID):
    pitches = np.loadtxt('PitcherData/' + str(ID) + 'Outputs2014.txt')
    #pitches = np.loadtxt('PitcherFiles/' + str(ID) + 'p.txt')
    return pitches

def randrange(list):
    a = min(list)
    b = max(list)
    r = random.uniform(a,b)
    return r

def getweights(num):
    w = np.loadtxt('PitcherFiles/weights.txt')
    weights = w[range(num*10,num*10 + 10)]
    return weights

def makesvm(p,d,w):
    param = svm_parameter('-q')
    param.C = w[0]
    param.gamma = w[1]
    prob = svm_problem(p,d)
    svmout = svm_train(prob,param)
    return svmout


def errormat(out,actual):
    error = np.zeros([6,6])
    for i in range(0,len(out)):
        for j in range(1,7):
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
                elif out[i] == 6:
                    error[j-1,5] += 1
    return error

def getcount(pitches):

    count = np.zeros([6,1])
    for i in range(0,6):
        count[i] = len(np.where(pitches == i+1)[0])

    if len(pitches) > 0:
        return np.ceil(10000*count.T/np.sum(count))/10000
    else:
        return count.T
#print sys.argv[1]

#predcount = np.zeros([11,110])
#errorMats = np.zeros([550,5])
#times = np.zeros([110,1])

#for num in range(0,110):
    
start = time.clock()

tp = np.zeros([13,1])

ID = int(sys.argv[1])

counts = np.loadtxt('PitcherData/YearCountStuff.txt')
#ID = np.loadtxt('PitcherFiles/IDs.txt',dtype='int')[num]
#ID = IDs[num]
data = getdata(ID)
pitches = getpitches(ID)[:,0].astype(int)
#weights = getweights(int(sys.argv[2]))
#cutoff = np.loadtxt('PitcherFiles/cutoffs.txt',dtype='int')[int(sys.argv[2])]
#cutoff2 = np.loadtxt('PitcherFiles/cutoff2.txt',dtype='int')[num]

#data = np.loadtxt('453562DataFast.txt')
#data = np.loadtxt('446372Data.txt')
#pitches = np.loadtxt('453562OutputsFast.txt')[:,0].astype(int)
#pitches = np.loadtxt('446372Outputs.txt')[:,0].astype(int)

print 'got data'

goodinds = np.where(np.invert(np.all(data == data[0,:], axis = 0)).nonzero())[0]

normdata = data[:,goodinds]
#normdata = normalize(data[:,goodinds])

print np.shape(normdata)

pVec = counts[np.where(counts[:,17] == ID)[0],:][0]

print pVec

cutoff = int(np.sum(pVec[4:6]) + np.ceil(.25*pVec[6]))

#normdata = normalize(data)
#lst = range(23,96,6)
#ind = list(set(range(0,96)) - set(lst) - set([7,19,20]))
#print ind
traindata = normdata[range(0,cutoff)]
trainpitch = pitches[range(0,cutoff)]
testdata = normdata[range(cutoff,len(pitches))]
testpitch = pitches[range(cutoff,len(pitches))]

print np.shape(traindata)

tp[0:6] = getcount(trainpitch).T
tp[6:12] = getcount(testpitch).T

#print ID

preds = np.zeros([len(testpitch),10])

print 'starting prediction'

for i in range(0,10):
    #clf = sklearn.ensemble.ExtraTreesClassifier(n_estimators=100)
    #clf = sklearn.ensemble.ExtraTreesClassifier(n_estimators=500)
    #clf = sklearn.ensemble.RandomForestClassifier(n_estimators=5)
    #clf = clf.fit(traindata.tolist(),trainpitch.tolist())
    clf = sklearn.tree.DecisionTreeClassifier()
    clf = clf.fit(traindata,trainpitch)
    preds[:,i] = clf.predict(testdata)#[0]
    print i

out = np.zeros([len(testpitch),1])

#clf2 = sklearn.ensemble.ExtraTreesClassifier(n_estimators=100)
clf2 = sklearn.ensemble.RandomForestClassifier(n_estimators=5)
clf2 = clf2.fit(traindata.tolist(),trainpitch.tolist())

print clf2.feature_importances_

for i in range(0,len(testpitch)):
    temp = preds[i]
    flag = 0
    count = 0
    t1 = Counter(temp).values()
    check = t1.count(max(t1))
    while(flag == 0):
        if (check > 1):
            #clf2 = sklearn.ensemble.ExtraTreesClassifier(n_estimators=100)
            #clf2 = sklearn.ensemble.ExtraTreesClassifier(n_estimators=500)
            #clf2 = sklearn.ensemble.RandomForestClassifier(n_estimators=500)
            #clf2 = clf2.fit(traindata.tolist(),trainpitch.tolist())
            p = clf2.predict([testdata[i].tolist(),testdata[i].tolist()])[0]

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

"""for i in range(0,10):
    param = svm_parameter('-q')
    param.C = weights[i][0]
    param.gamma = weights[i][1]
    prob = svm_problem(trainpitch.tolist(),traindata.tolist())
    svmout = svm_train(prob,param)
    preds[:,i] = svm_predict(testpitch.tolist(),testdata.tolist(),svmout)[0]

out = np.zeros([len(testpitch),1])
          
for i in range(0,len(testpitch)):
    temp = preds[i]
    flag = 0
    count = 0
    t1 = Counter(temp).values()
    check = t1.count(max(t1))
    while(flag == 0):
        if (check > 1):
            Crand = randrange(weights[:,0])
            grand = randrange(weights[:,1])
            svmout = makesvm(trainpitch.tolist(),traindata.tolist(),[Crand, grand])
            p = svm_predict([testpitch[i].tolist(),0],[testdata[i].tolist(),testdata[i].tolist()],svmout)[0]
            temp = list(temp)
            temp.append(p[0])
            t1 = Counter(temp).items()
            check = t1.count(max(t1))
            count += 1
            if(check == 1):
                flag = 1
        else:
            flag = 1
    out[i] = stats.mode(temp)[0]"""


for i in range(0,100):
    print [preds[i,:], out[i], testpitch[i]]

error = errormat(out,testpitch)

#errorMats[num*6:(num+1)*5,:] = error[:,:]

print error

corr = 0

for i in range(0,6):
    corr = corr + error[i,i]

percent = 100*(corr/len(out))

tp[12] = percent

#predcount[:,num] = tp[:,0]

print tp

#times[num] = time.clock() - start

print time.clock() - start


"""np.savetxt('DTpredcSmall.txt',predcount,'%5.6f')
np.savetxt('DTtimesSmall.txt',times)
np.savetxt('DTerrMatSmall.txt',errorMats,'%i')"""



