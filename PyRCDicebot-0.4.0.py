#!/usr/bin/env python
#-*- coding:utf-8 -*-
"""
PyRC Diceroller v0.4.0
Connects to an IRC server and monitors selected channels for commands, rolling
dice when requested.
"""
"""
The MIT License

Copyright (c) 2010 David Ross - dross@uoregon.edu

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, and/or distribute
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""
"""
Usage:
!roll:
    XdY
    XdY+Z
    XdY-Z
    Z*XdY
   sXdY     - Sort (Low to High) (implies verbose)
   vXdY     - Verbose (Describe each roll)
   aXdY     - Array (skip printing grand total)
    XdYeZ   - Explode (Reroll Z or higher)
    XdYbZ   - Brutal  (Reroll Z or lower)
    XdYtZ   - Target Z or higher
    XdYfZ   - Fail on Z or lower
    XdYkZ   - Keep Z highest
    XdY+AdB - Multiple Dice
!nwod:
    X         - X d10s, rerolling 10s
    XeY     - X d10s, rerolling Y dice. 0 to reroll none.
    vX(eY)  - Verbose mode
    sX(eY)  - Sort mode (implies verbose)
!owod:
    XtY     - X d10s, with a target threshold of Y, subtracting ones and highlighting botches.
!xia:
    X       - X d10s, grouped together and sorted by width.
!tp:
    XpYmZ   - X+Y+Z d6s, separated into X panic dice, Y min-2 dice, & Z normal dice, sorted internally
"""

import sys
import os
import random
import re

from twisted.words.protocols import irc
from twisted.internet import reactor, protocol

def base_roll(s):
    """General dice rolling"""
    sort = False
    verbose = False
    array = False
    sFlags = re.match(r'[a-z]+',s,re.I)
    if sFlags:
        sFlags = sFlags.group()
        if 's' in sFlags:
            sort = True
            verbose = True
            s = s.replace('s','',1)
        if 'v' in sFlags:
            verbose = True
            s = s.replace('v','',1)
        if 'a' in sFlags:
            array = True
            s = s.replace('a','',1)

    sComment = ''
    sComStart = re.search(r'\d ',s)
    if sComStart:
        sComment = s[sComStart.end():]
        s = s[:sComStart.end()-1]

    modifier = re.search(r'[\+|-]\d+$',s) # Dice modifier. +-Z
    if modifier:
        modifier = modifier.group()
        if modifier[0] == '-':
            modifier = int(modifier[1:])*-1
        else:
            modifier = int(modifier[1:])
    else: modifier = 0

    explode = re.search(r'e\d+',s) # e prefacing
    if explode:
        explode = explode.group()
        explode = int(explode[1:])
        if explode == 1:
            return "Error: Don't make every die explode."

    brutal = re.search(r'b\d+',s) # b prefacing
    if brutal:
        brutal = brutal.group()
        brutal = int(brutal[1:])

    target = re.search(r't\d+',s) # t prefacing
    if target:
        target = target.group()
        target = int(target[1:])

    failure = re.search(r'f\d+',s) # f prefacing
    if failure:
        failure = failure.group()
        failure = int(failure[1:])

    keep = re.search(r'k\d+',s) # k prefacing
    if keep:
        keep = keep.group()
        keep = int(keep[1:])

    multiRe = re.search(r'(\d+)\*(\d*d\d+)',s) # W*XdY
    if multiRe:
        multimod = multiRe.group(1)
        multimod = int(multimod)
        tempS = s
        tempS = tempS[:multiRe.start()] + tempS[multiRe.end():]
        insS = ''
        for n in range(0,multimod):
            insS = insS + multiRe.group(2) + '+'
        insS = insS[:-1]
        tempS = insS + tempS
        s = tempS

    dicepairs = re.findall(r'(\d*)d(\d+)',s) # Basic dice pairs: XdY
    if not dicepairs: return "an error."

    printqueue = []
    dicetotal = modifier
    successes = fails = expcount = brucount = 0
    if len(dicepairs) == 1:
        array = True
    for n in range(0,len(dicepairs)):
        if n < 0:
            return "Error: Roll at least one die."
        sortqueue = []
        subtotal = 0
        if dicepairs[n][0] == "": dicepairs[n] = ('1',dicepairs[n][1])
        i = int(dicepairs[n][0])
        while (i > 0): #primary dicerolling
            i += -1
            if n < 0:
                return "Error: Roll at least a one-sided die."
            die = random.randint(1,int(dicepairs[n][1]))
            if explode:
                if die >= explode:
                    i += 1
                    expcount += 1
            if brutal:
                if brutal == dicepairs[n][1]:
                    pass
                elif die <= brutal:
                    die = random.randint(1,int(dicepairs[n][1]))
                    brucount += 1
            if target:
                if die >= target:
                    successes += 1
            if failure:
                if die <= failure:
                    fails += 1
            dicetotal += die
            subtotal  += die
            sortqueue.append(die)
        if sort:
            sortqueue.sort()
        if keep:
            keeptemp = len(sortqueue) - keep
            for i in range(0,keeptemp):
                temp = sortqueue.pop(min(sortqueue))
                subtotal = subtotal - temp
                dicetotal = dicetotal - temp
        printqueue.append(str(dicepairs[n][0])+"d"+str(dicepairs[n][1])+":")
        if verbose:
            for n in range(0,len(sortqueue)):
                printqueue.append(str(sortqueue[n]))
        printqueue.append("= "+str(subtotal))
    if not array:
        printqueue.append("Grand total: " + str(dicetotal) + ".")
    if explode:
        printqueue.append(str(expcount) + " exploded, hitting a "+ str(explode) + " or higher. ")
    if brutal:
        printqueue.append(str(brucount) + " hit a " + str(brutal) + " or under, and were rerolled. ")
    if target:
        printqueue.append(str(successes) + " succeeded on a " + str(target) + " or higher.")
    if failure:
        printqueue.append(str(fails) + " failed on a " + str(failure) + " or lower.")
    printqueue.append(sComment)
    return ' '.join(printqueue)
#------------------------------------------------------------------------------
def owod_roll(s):
    """Old World of Darkness dice rolling. XtY - X d10s, with a target threshold of Y, subtracting ones and highlighting botches."""
    sCom = ''
    sComStart = re.search(r'\d ',s)
    if sComStart:
        sCom = s[sComStart.end():]
        s = s[:sComStart.end()-1]
    target = re.search(r't\d+',s)
    target = target.group()
    target = int(target[1:])
    dice =  re.match(r'\d+',s)
    dice = int(dice.group())
    successes = ones = 0
    for i in range(1,dice):
        die = random.randint(1,10)
        if die >= target:
            successes += 1
        elif die == 1:
            ones += -1
    if not successes:
        if ones:
            botch = " Botch."
    successes = successes + ones
    return str(successes) + " successes on a threshold of " + str(target) + " or higher." + botch + sCom
#------------------------------------------------------------------------------
def titpan_roll(s):
    """Titanium Panoply dice rolling. XpYmZ - X+Y+Z d6s, separated into X panic dice, Y min-2 dice, & Z normal dice, sorted internally"""
    panicqueue = []
    min2queue = []
    normqueue = []
    sCom = '' #Find and strip comment
    sComStart = re.search(r'\d ',s)
    if sComStart:
        sCom = s[sComStart.end():]
        s = s[:sComStart.end()-1]
    if re.match(r'\d+p\d+m\d+',s): # If all three, XpYmZ
        panic = re.search(r'\d+p',s)
        panic = panic.group()
        panic = int(panic[:1])
        if panic != 0:
            for i in range(0,panic):
                die = random.randint(1,6)
                panicqueue.append(die)
            panicqueue.sort()
        min2  = re.search(r'\d+m',s)
        min2  = min2.group()
        min2  = int(min2[:1])
        if min2 != 0:
            for i in range(0,min2):
                die = random.randint(2,6)
                min2queue.append(die)
            min2queue.sort()
        norm  = re.search(r'm\d+',s)
        norm  = norm.group()
        norm  = int(norm[1:])
        if norm != 0:
            for i in range(0,norm):
                die = random.randint(1,6)
                normqueue.append(die)
            normqueue.sort()
    elif re.match(r'\d+p',s): # No min2 dice: XpY, Xp
        panic = re.search(r'\d+p',s)
        panic = panic.group()
        panic = int(panic[:1])
        if panic != 0:
            for i in range(0,panic):
                die = random.randint(1,6)
                panicqueue.append(die)
            panicqueue.sort()
        norm  = re.search(r'p\d+',s)
        if norm:
            norm  = norm.group()
            norm  = int(norm[1:])
            if norm != 0:
                for i in range(0,norm):
                    die = random.randint(1,6)
                    normqueue.append(die)
                normqueue.sort()
    elif re.match(r'\d+m',s): # No panic dice: XmY, Xm
        min2  = re.search(r'\d+m',s)
        min2  = min2.group()
        min2  = int(min2[:1])
        if min2 != 0:
            for i in range(0,min2):
                die = random.randint(2,6)
                min2queue.append(die)
            min2queue.sort()
        norm  = re.search(r'm\d+',s)
        if norm:
            norm  = norm.group()
            norm  = int(norm[1:])
            if norm != 0:
                for i in range(0,norm):
                    die = random.randint(1,6)
                    normqueue.append(die)
                normqueue.sort()
    elif re.match(r'\d+',s): # No panic or min2 dice: X
        norm = re.search(r'\d+',s)
        norm  = norm.group()
        norm  = int(norm[:])
        if norm != 0:
            for i in range(0,norm):
                die = random.randint(1,6)
                normqueue.append(die)
            normqueue.sort()
    return str(panicqueue) + " panic; " + str(min2queue) + " min-2; " + str(normqueue) + " normal. " + sCom
#------------------------------------------------------------------------------
def nwod_roll(s):
    """New World of Darkness dice rolling."""
    sort = False
    verbose = False
    sortqueue = []
    printqueue = []
    sFlags = re.match(r'[a-z]+',s,re.I)
    if sFlags:
        sFlags = sFlags.group()
        if 's' in sFlags:
            sort = True
            verbose = True
            s = s.replace('s','',1)
        if 'v' in sFlags:
            verbose = True
            s = s.replace('v','',1)
    sCom = ''
    sComStart = re.search(r'\d ',s) # comment
    if sComStart: # comment strip
        sCom = s[sComStart.end():]
        s = s[:sComStart.end()-1]
    explode = re.search(r'e\d+',s) # search for 'eX'
    if explode:
        explode = explode.group()
        explode = int(explode[1:])
        if explode <= 0:
            explode = 10
    else:
        explode = 10
    dice =  re.match(r'\d+',s) # number of dice to roll
    dice = int(dice.group())
    successes = ones = explodecount = 0
    i = dice
    while (i>0):
        i += -1
        die = random.randint(1,10)
        sortqueue.append(die)
        if die >= 8:
            successes += 1
        elif die == 1:
            ones += 1
        if die >= explode:
            i += 1
            explodecount += 1
    expComment = ", & " + str(explodecount) + " exploding on a " + str(explode) + " or higher. "
    if sort:
        sortqueue.sort()
    if verbose:
        return str(dice) + " dice, with " + str(successes) + " successes, " + str(ones) + " ones" + expComment + str(sortqueue) + sCom
    else:
        return str(dice) + " dice, with " + str(successes) + " successes, " + str(ones) + " ones" + expComment + sCom
#------------------------------------------------------------------------------
def wuxia_roll(s):
    """Legends of the Wulin dice rolling. X - X d10s, grouped together and sorted by width."""
    sComment = ''
    sComStart = re.search(r'\d ',s)
    printstack = ['']
    if sComStart:
        sComment = s[sComStart.end():]
        s = s[:sComStart.end()-1]

    dice =  re.match(r'\d+',s)
    dice = int(dice.group())
    dicestack = {}
    for i in range(0,dice):
        die = random.randint(1,10)
        if die not in dicestack:
            dicestack[die] = 1
        else:
            dicestack[die] += 1
    for n in sorted(dicestack, key=dicestack.get, reverse = True):
        printstack.append(str(dicestack[n])+"x"+str(n)+', ')
    printstack.append(sComment)
    return ''.join(printstack)
#------------------------------------------------------------------------------
class PyRCBot(irc.IRCClient):
    def _get_nickname(self):
        return self.factory.nickname
    nickname = property(_get_nickname)
    
    def signedOn(self):
        self.join(self.factory.channel)
        print "Signed on as %s." % (self.nickname,)
    
    def joined(self, channel):
        print "Joined %s." % (channel,)
    
    def privmsg(self, user, channel, msg):
        if not user:
            return
        if not msg.startswith('!'): # not a trigger command
            return # do nothing
        if msg.startswith("!roll"):
            msg = msg[6:]
            user = "%s: " % (user.split('!', 1)[0], )
            roll = base_roll(msg)
            self.msg(self.factory.channel, user + roll)
        elif msg.startswith("!owod"):
            msg = msg[6:]
            user = "%s: " % (user.split('!', 1)[0], )
            roll = owod_roll(msg)
            self.msg(self.factory.channel, user + roll)
        elif msg.startswith("!tp"):
            msg = msg[4:]
            user = "%s: " % (user.split('!', 1)[0], )
            roll = titpan_roll(msg)
            self.msg(self.factory.channel, user + roll)
        elif msg.startswith("!nwod"):
            msg = msg[6:]
            user = "%s: " % (user.split('!', 1)[0], )
            roll = nwod_roll(msg)
            self.msg(self.factory.channel, user + roll)
        elif msg.startswith("!xia"):
            msg = msg[5:]
            user = "%s: " % (user.split('!', 1)[0], )
            roll = wuxia_roll(msg)
            self.msg(self.factory.channel, user + roll)
        elif msg.startswith("!begin"):
            msg = msg[7:]
            self.msg(self.factory.channel, "**********Begin Session**********")
        elif msg.startswith("!pause"):
            msg = msg[7:]
            self.msg(self.factory.channel, "**********Pause Session**********")
        elif msg.startswith("!end"):
            msg = msg[5:]
            self.msg(self.factory.channel, "**********End Session**********")

class PyRCBotFactory(protocol.ClientFactory):
    protocol = PyRCBot
    
    def __init__(self, channel, nickname='PyRCDicebot'):
        self.channel = channel
        self.nickname = nickname
    
    def clientConnectionLost(self, connector, reason):
        print "Lost connection (%s), reconnecting." % (reason,)
        connector.connect()
    
    def clientConnectionFailed(self, connector, reason):
        print "Could not connect: %s" % (reason,)

if __name__ == "__main__":
    if sys.argv[1]:
        if sys.argv[1] is '-h':
            print sys.argv[0] + " [server] [name] [channel 1] ..."
            sys.exit()
    try:
        server = sys.argv[1]
    except IndexError:
        print "Please specify a server. [server] [name] [channel 1] ..."
    try:
        name = sys.argv[2]
    except IndexError:
        print "Please specify a bot name. [server] [name] [channel 1] ..."
    try:
        chanlist = sys.argv[3:]
    except IndexError:
        print "Please specify a channel name. [server] [name] [channel 1] ..."
    for channel in chanlist:
        reactor.connectTCP(server, 6667, PyRCBotFactory('#' + channel, name))
    reactor.run()