#!/usr/bin/env python3
"""Log UDP messages from halflife server."""
import socket
import re
import os

players = {}
currentMap = 'crossfire'

class Player:
    def __init__(self, name: str):
        self.name   = name
        self.kills  = 0
        self.deaths = 0


def GetPlayerNameAndId(dataStr: str):
    """Get player name from the beginning of the log string."""
    expr = re.compile('\"((\\w+\\s*)+)<[0-9]+><STEAM_[0-9]:[0-9]:([0-9]+)>')
    matches = expr.search(dataStr)
    playerNameAndId = []
    if matches is not None:
        playerName = matches.groups()[1]
        playerId = matches.groups()[2]
        playerNameAndId.append(playerName)
        playerNameAndId.append(playerId)
    return playerNameAndId


def UpdateLogFile(fileName: str):
    """Update the log file."""
    with open(fileName, "w") as logfile:
        logfile.write("Current map: {0}\n".format(currentMap))
        logfile.write("Player\tKills\tDeaths\n")
        for player in players:
            logfile.write("{0}\t{1}\t{2}\n".format(players[player].name, players[player].kills, players[player].deaths))
        logfile.write("\n")


def ResetScore():
    """Reset the score for all players."""
    for player in players:
        players[player].kills = 0
        players[player].deaths = 0


def AddPlayer(dataStr: str):
    """Add a new player."""
    nameAndId = GetPlayerNameAndId(dataStr)
    players[nameAndId[1]] = Player(nameAndId[0])


def RemovePlayer(dataStr: str):
    """Remove a plyer from the map."""
    nameAndId = GetPlayerNameAndId(dataStr)
    players.pop(nameAndId[1])


def UpdateScore(dataStr: str):
    """Update player scores when one player kills another."""
    expr = re.compile('\"((\\w+\\s*)+)<[0-9]+><STEAM_[0-9]:[0-9]:([0-9]+)>.*\"((\\w+\\s*)+)<[0-9]+><STEAM_[0-9]:[0-9]:([0-9]+)>')
    matches = expr.search(dataStr)
    if matches is not None:
        idKiller = matches.groups()[2]
        idKillee = matches.groups()[5]
        players[idKiller].kills  += 1
        players[idKillee].deaths += 1


def HandleMapChange(dataStr: str):
    """Update current map and reset player scores."""
    mapExpr = re.compile('Started map \\"(w+)\\"')
    matches = mapExpr.search(dataStr)
    if matches is not None:
        currentMap = matches.groups()[1]
    ResetScore()


def HandleSuicide(dataStr: str):
    """Adjust a player's score after a self-kill."""
    id = GetPlayerNameAndId(dataStr)[1]
    killPenalty = -1
    worldExpr = re.compile('world')
    matches = worldExpr.search(dataStr)
    if matches is not None:
        killPenalty = 0
    players[id].kills  += killPenalty
    players[id].deaths += 1


def HandleNameChange(dataStr: str):
    """Update a player's name."""
    id = GetPlayerNameAndId(dataStr)[1]
    nameExpr = re.compile('.*changed name to \"((\\w+\\s*)+)\"')
    matches = nameExpr.search(dataStr)
    if matches is not None:
        newName = matches.groups()[1]
        players[id].name = newName


def ProcessLogMessages(data: bytes):
    """Apply the appropriate regular expression to log messages and handle them."""
    dataStr = str(data)
    print(dataStr)

    logFileName = "/home/geoffrosenberg/Documents/connections.txt"

    connectedExpr = re.compile('\\bconnected')
    if connectedExpr.search(dataStr) is not None:
        AddPlayer(dataStr)
        UpdateLogFile(logFileName)
        return

    disconnectedExpr = re.compile('\\bdisconnected')
    if disconnectedExpr.search(dataStr) is not None:
        RemovePlayer(dataStr)
        if players == {} and os.path.exists(logFileName):
            os.remove(logFileName)
        return

    killedExpr = re.compile('\\bkilled')
    if killedExpr.search(dataStr) is not None:
        UpdateScore(dataStr)
        return

    suicideExpr = re.compile('\\bsuicide')
    if suicideExpr.search(dataStr) is not None:
        HandleSuicide(dataStr)
        return

    nameChangeExpr = re.compile('\" changed name to \"')
    if nameChangeExpr.search(dataStr) is not None:
        HandleNameChange(dataStr)
        return

    mapChangeExpr = re.compile('Started map')
    if mapChangeExpr.search(dataStr) is not None:
        HandleMapChange(dataStr)
        return


if __name__ == "__main__":
    hostname = socket.gethostname()
    UDP_IP = "127.0.0.1"
    UDP_PORT = 11001

    sock = socket.socket(socket.AF_INET,
                         socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))

    while True:
        data, addr = sock.recvfrom(1024)
        ProcessLogMessages(data)
