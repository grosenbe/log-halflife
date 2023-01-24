#!/usr/bin/env python3
"""Log UDP messages frm halflife server."""
import socket
import re
import os

players = {}

class Player:
    def __init__(self, name: str):
        self.name   = name
        self.kills  = 0
        self.deaths = 0


def GetPlayerNameAndId(dataStr: str):
    """Get player name from the beginning of the log string."""
    expr = re.compile('\"((\\w+\\s*)+)<[0-9]+><STEAM_[0-9]:[0-9]:([0-9]+)>')
    matches = expr.search(dataStr)
    playerName = ''
    if matches is not None:
        playerName = matches.groups()[1]
        playerId = matches.groups()[2]
        playerNameAndId = []
        playerNameAndId.append(playerName)
        playerNameAndId.append(playerId)
    return playerNameAndId


def UpdateLogFile(fileName: str):
    """Update the log file."""
    with open(fileName, "w") as logfile:
        logfile.write("Player\tKills\tDeaths\n")
        for player in players:
            logfile.write("{0}\t{1}\t{2}\n".format(players[player].name, players[player].kills, players[player].deaths))
        logfile.write("\n")


def AddPlayer(dataStr: str):
    nameAndId = GetPlayerNameAndId(dataStr)
    players[nameAndId[1]] = Player(nameAndId[0])


def RemovePlayer(dataStr: str):
    nameAndId = GetPlayerNameAndId(dataStr)
    players.pop(nameAndId[1])


def UpdateScore(dataStr: str):
    expr = re.compile('\"((\\w+\\s*)+)<[0-9]+><STEAM_[0-9]:[0-9]:([0-9]+)>.*\"((\\w+\\s*)+)<[0-9]+><STEAM_[0-9]:[0-9]:([0-9]+)>')
    matches = expr.search(dataStr)
    if matches is not None:
        idKiller = matches.groups()[2]
        idKillee = matches.groups()[5]
        players[idKiller].kills  += 1
        players[idKillee].deaths += 1


def HandleSuicide(dataStr: str):
    id = GetPlayerNameAndId(dataStr)[1]
    players[id].kills  -= 1
    players[id].deaths += 1


def HandleNameChange(dataStr: str):
    id = GetPlayerNameAndId(dataStr)[1]
    nameExpr = re.compile('.*changed name to \"((\\w+\\s*)+)\"')
    matches = nameExpr.search(dataStr)
    if matches is not None:
        newName = matches.groups()[1]
        players[id].name = newName

def ProcessLogMessages(data: bytes):
    """Apply the regular expression."""
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
