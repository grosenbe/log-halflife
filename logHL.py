#!/usr/bin/env python3
"""Log UDP messages from a Half-Life server."""
import socket
import re
import os
import sys
from tabulate import tabulate

players = {}
currentMap = 'crossfireXL'

class Player:
    def __init__(self, name: str, ip: str):
        self.name   = name
        self.kills  = 0
        self.deaths = 0
        self.address = ip


def PrintToConsole(dataStr: str):
    """Print to console for local logging."""
    global players
    global currentMap
    print("Current map: {0}".format(currentMap))
    scores=[]
    for steamId in players:
        scores.append([players[steamId].name, players[steamId].kills, players[steamId].deaths, steamId, players[steamId].address])
    print(tabulate(scores, headers=["Player","Kills","Deaths", "Steam ID", "IP Address"]))
    sys.stdout.flush()


def UpdateLogFile(fileName: str, dataStr: str):
    """Update the log file."""
    playerName = GetPlayerNameAndId(dataStr)[0]
    with open(fileName, "w") as logfile:
        logfile.write("New player: {0}\n".format(playerName))
        logfile.write("Current map: {0}\n".format(currentMap))
        logfile.write("\n")
        logfile.write("Scoreboard\n")
        scores=[]
        global players
        for steamId in players:
            scores.append([players[steamId].name, players[steamId].kills, players[steamId].deaths, steamId, players[steamId].address])
        logfile.write(tabulate(scores, headers=["Player","Kills","Deaths","Steam ID", "IP Address"]))
        logfile.write("\n")


def GetPlayerInfo(dataStr: str):
    """Get player info from the connection message."""
    expr = re.compile('\"((?:\\w+\\s*)+)<[0-9]+><STEAM_[0-9]:[0-9]:([0-9]+)><.*>\".*\"((?:[0-9]+\.)+[0-9]+)')
    matches = expr.search(dataStr)
    playerNameIdIp = []
    if matches is not None:
        playerNameIdIp.append(matches.groups()[0]) # name
        playerNameIdIp.append(matches.groups()[1]) # steam ID
        playerNameIdIp.append(matches.groups()[2]) # IP Address
    return playerNameIdIp

def GetPlayerNameAndId(dataStr: str):
    """Get player name and ID."""
    expr = re.compile('\"((?:\\w+\\s*)+)<[0-9]+><STEAM_[0-9]:[0-9]:([0-9]+)')
    matches = expr.search(dataStr)
    playerNameAndId = []
    if matches is not None:
        playerNameAndId.append(matches.groups()[0]) # name
        playerNameAndId.append(matches.groups()[1]) # steam ID
    return playerNameAndId


def ResetScore():
    """Reset the score for all players."""
    global players
    for player in players:
        players[player].kills = 0
        players[player].deaths = 0


def AddPlayer(dataStr: str):
    """Add a new player."""
    playerInfo = GetPlayerInfo(dataStr)
    global players
    players[playerInfo[1]] = Player(playerInfo[0], playerInfo[2])


def RemovePlayer(dataStr: str):
    """Remove a player from the dictionary."""
    nameAndId = GetPlayerNameAndId(dataStr)
    global players
    if nameAndId[1] in players:
        players.pop(nameAndId[1])


def UpdateScore(dataStr: str):
    """Update player scores when one player kills another."""
    expr = re.compile('\"(?:\\w+\\s*)+<[0-9]+><STEAM_[0-9]:[0-9]:([0-9]+)>.*\"(?:\\w+\\s*)+<[0-9]+><STEAM_[0-9]:[0-9]:([0-9]+)>')
    matches = expr.search(dataStr)
    if matches is not None:
        idKiller = matches.groups()[0]
        idKillee = matches.groups()[1]
        global players
        if idKiller in players and idKillee in players:
            players[idKiller].kills  += 1
            players[idKillee].deaths += 1


def HandleMapChange(dataStr: str):
    """Update current map and reset player scores."""
    mapExpr = re.compile('Started map \\"(\\w+)\\"')
    matches = mapExpr.search(dataStr)
    if matches is not None:
        global currentMap
        currentMap = matches.groups()[0]
    ResetScore()


def HandleSuicide(dataStr: str):
    """Adjust a player's score after a self-kill."""
    id = GetPlayerNameAndId(dataStr)[1]
    killPenalty = -1
    worldExpr = re.compile('world')
    matches = worldExpr.search(dataStr)
    if matches is not None:
        killPenalty = 0

    global players
    if id in players:
        players[id].kills  += killPenalty
        players[id].deaths += 1


def HandleNameChange(dataStr: str):
    """Update a player's name."""
    id = GetPlayerNameAndId(dataStr)[1]
    nameExpr = re.compile('.*changed name to \"((?:\\w+\\s*)+)\"')
    matches = nameExpr.search(dataStr)
    if matches is not None:
        newName = matches.groups()[0]
        global players
        if id in players:
            players[id].name = newName


def ProcessLogMessages(data: bytes):
    """Apply the appropriate regular expression to log messages and handle them."""
    dataStr = str(data)
    logFileName = "/home/geoffrosenberg/Documents/connections.txt"
    processedMessage = False

    connectedExpr = re.compile('\\bconnected')
    if connectedExpr.search(dataStr) is not None:
        AddPlayer(dataStr)
        UpdateLogFile(logFileName, dataStr)
        processedMessage = True

    disconnectedExpr = re.compile('\\bdisconnected')
    if disconnectedExpr.search(dataStr) is not None:
        RemovePlayer(dataStr)
        global players
        if players == {} and os.path.exists(logFileName):
            os.remove(logFileName)
        processedMessage = True

    killedExpr = re.compile('\\bkilled')
    if killedExpr.search(dataStr) is not None:
        UpdateScore(dataStr)
        processedMessage = True

    suicideExpr = re.compile('\\bsuicide')
    if suicideExpr.search(dataStr) is not None:
        HandleSuicide(dataStr)
        processedMessage = True

    nameChangeExpr = re.compile('\" changed name to \"')
    if nameChangeExpr.search(dataStr) is not None:
        HandleNameChange(dataStr)
        processedMessage = True

    mapChangeExpr = re.compile('Started map')
    if mapChangeExpr.search(dataStr) is not None:
        HandleMapChange(dataStr)
        processedMessage = True

    if processedMessage == True:
        PrintToConsole(dataStr)


if __name__ == "__main__":
    UDP_IP = "127.0.0.1"
    UDP_PORT = 11001

    sock = socket.socket(socket.AF_INET,
                         socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))

    while True:
        data, addr = sock.recvfrom(1024)
        ProcessLogMessages(data)
