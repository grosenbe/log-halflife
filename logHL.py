#!/usr/bin/env python3
"""Log UDP messages from a Half-Life server."""
from datetime import datetime, timezone
import socket
import re
import os
import sys
import getpass
import psycopg2
from tabulate import tabulate

currentMap = 'crossfireXL'
conn = ''


class Player:
    """Player name, IP, and score."""
    def __init__(self, name: str, ip: str):
        self.name = name
        self.kills = 0
        self.deaths = 0
        self.address = ip


def PrintToConsole(dataStr: str):
    """Print to console for local logging."""
    global currentMap
    print("Current map: {0}".format(currentMap))
    with conn.cursor() as cursor:
        cursor.execute('SELECT * FROM scores')
        rows = cursor.fetchall()
        scores = []
        for row in rows:
            scores.append([row[1], row[2], row[3], row[0], row[4]])
            print(tabulate(scores, headers=["Player", "Kills", "Deaths",
                                            "Steam ID", "IP Address"]))
    sys.stdout.flush()


def UpdateLogFile(fileName: str, dataStr: str):
    """Update the log file."""
    playerName = GetPlayerNameAndId(dataStr)[0]
    with open(fileName, "w") as logfile:
        logfile.write("New player: {0}\n".format(playerName))
        logfile.write("Current map: {0}\n".format(currentMap))
        logfile.write("\n")
        logfile.write("Scoreboard\n")
        with conn.cursor() as cursor:
            cursor.execute('SELECT * from scores')
            rows = cursor.fetchall()
            scores = []
            for row in rows:
                scores.append([row[1], row[2], row[3], row[0], row[4]])
            logfile.write(tabulate(scores, headers=["Player", "Kills",
                                                    "Deaths", "Steam ID",
                                                    "IP Address"]))
            logfile.write("\n")


def GetPlayerConnectionInfo(dataStr: str):
    """Get player info from the connection message."""
    expr = re.compile('\"((?:\\w+\\s*)+)<[0-9]+><STEAM_[0-9]:[0-9]:([0-9]+)><.*>\".*\"((?:[0-9]+\.)+[0-9]+)')
    matches = expr.search(dataStr)
    playerNameIdIp = []
    if matches is not None:
        playerNameIdIp.append(matches.groups()[0])  # name
        playerNameIdIp.append(matches.groups()[1])  # steam ID
        playerNameIdIp.append(matches.groups()[2])  # IP Address
    return playerNameIdIp


def GetPlayerNameAndId(dataStr: str):
    """Get player name and ID."""
    expr = re.compile('\"((?:\\w+\\s*)+)<[0-9]+><STEAM_[0-9]:[0-9]:([0-9]+)')
    matches = expr.search(dataStr)
    playerNameAndId = []
    if matches is not None:
        playerNameAndId.append(matches.groups()[0])  # name
        playerNameAndId.append(matches.groups()[1])  # steam ID
    return playerNameAndId


def ResetScore():
    """Reset the score for all players and update high score if applicable."""
    with conn.cursor() as cursor:
        cursor.execute('SELECT steam_id, kills FROM scores')
        rows = cursor.fetchall()
        for row in rows:
            steamId = row[0]
            sessionKills = row[1]
            cursor.execute("SELECT max_kills FROM playerhistory WHERE steam_id = {0}".format(steamId))
            newRow = cursor.fetchone()
            maxKills = newRow[0]
            if sessionKills > maxKills:
                cursor.execute("UPDATE playerhistory SET max_kills = {0} WHERE steam_id = {1}".format(sessionKills, steamId))
                conn.commit()

        cursor.execute('UPDATE scores SET kills = 0')
        cursor.execute('UPDATE scores SET deaths = 0')
        conn.commit()


def AddPlayer(dataStr: str):
    """Add a new player."""
    playerInfo = GetPlayerConnectionInfo(dataStr)
    with conn.cursor() as cursor:
        cursor.execute('INSERT INTO scores (steam_id, name, kills, deaths, '
                       + 'ip_address) VALUES(%s, %s, %s, %s, %s)',
                       (playerInfo[1], playerInfo[0], '0', '0', playerInfo[2]))
        conn.commit()

        cursor.execute('SELECT * from playerhistory WHERE steam_id = '
                       + playerInfo[1])
        rows = cursor.fetchall()
        if rows:
            updateCommand = "UPDATE playerhistory SET last_login = '{0}', login_count = login_count + 1 WHERE steam_id = {1}".format(datetime.now(timezone.utc), playerInfo[1])
            cursor.execute(updateCommand)
        else:
            cursor.execute('INSERT INTO playerhistory (steam_id, first_login, last_login, kills, deaths, login_count, total_hours, max_kills) VALUES(%s, %s, %s, %s, %s, %s, %s, %s)', (playerInfo[1], datetime.now(timezone.utc), datetime.now(timezone.utc), 0, 0, 1, 0, 0))
        conn.commit()


def RemovePlayer(dataStr: str):
    """Remove a player from the scores table."""
    nameAndId = GetPlayerNameAndId(dataStr)
    with conn.cursor() as cursor:
        cursor.execute('SELECT last_login, max_kills FROM playerhistory WHERE steam_id = '
                       + nameAndId[1])
        row = cursor.fetchone()
        sessionStartTime = row[0]
        maxKills = row[1]
        cursor.execute('SELECT kills FROM scores WHERE steam_id = ' + nameAndId[1])
        row = cursor.fetchone()
        sessionKills = row[0]
        sessionHours = (datetime.now(timezone.utc) - sessionStartTime).seconds / 3600
        if sessionKills > maxKills:
            cursor.execute("UPDATE playerhistory SET total_hours = total_hours + {0}, max_kills = {1} WHERE steam_id = {2}".format(sessionHours, sessionKills, nameAndId[1]))
        else:
            cursor.execute("UPDATE playerhistory SET total_hours = total_hours + {0} WHERE steam_id = {1}".format(sessionHours, nameAndId[1]))
        conn.commit()
        cursor.execute('DELETE FROM scores WHERE steam_id = %s', (nameAndId[1],))
        conn.commit()


def UpdateScore(dataStr: str):
    """Update player scores when one player kills another."""
    expr = re.compile('\"(?:\\w+\\s*)+<[0-9]+><STEAM_[0-9]:[0-9]:([0-9]+)>.*\"(?:\\w+\\s*)+<[0-9]+><STEAM_[0-9]:[0-9]:([0-9]+)>')
    matches = expr.search(dataStr)
    if matches is not None:
        idKiller = matches.groups()[0]
        idKillee = matches.groups()[1]
        with conn.cursor() as cursor:
            cursor.execute('UPDATE scores SET kills = kills+1 WHERE steam_id ='
                           + ' %s', (idKiller,))
            cursor.execute('UPDATE scores SET deaths = deaths+1 WHERE steam_id'
                           + ' = %s', (idKillee,))
            cursor.execute('UPDATE playerhistory SET kills = kills+1 WHERE'
                           + ' steam_id = %s', (idKiller,))
            cursor.execute('UPDATE playerhistory SET deaths = deaths+1 WHERE '
                           + 'steam_id = %s', (idKillee,))
            conn.commit()


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

    with conn.cursor() as cursor:
        cursor.execute('UPDATE scores SET deaths = deaths + 1 WHERE steam_id ='
                       + ' %s', (id,))
        cursor.execute('UPDATE scores SET kills = kills + %s WHERE steam_id ='
                       + ' %s', (killPenalty, id,))
        cursor.execute('UPDATE playerhistory SET deaths = deaths + 1 WHERE '
                       + 'steam_id = %s', (id,))
        cursor.execute('UPDATE playerhistory SET kills = kills + %s WHERE '
                       + 'steam_id = %s', (killPenalty, id,))
        conn.commit()


def HandleNameChange(dataStr: str):
    """Update a player's name."""
    id = GetPlayerNameAndId(dataStr)[1]
    nameExpr = re.compile('.*changed name to \"((?:\\w+\\s*)+)\"')
    matches = nameExpr.search(dataStr)
    if matches is not None:
        newName = matches.groups()[0]
        with conn.cursor() as cursor:
            # TODO update the playerhistory.aliases_used list
            updateCommand = "UPDATE scores SET name = '{0}' WHERE steam_id = {1}".format(newName, id)
            cursor.execute(updateCommand)
            conn.commit()


def IsPlayersTableEmpty():
    """Check if there are any players in the scores relation."""
    with conn.cursor() as cursor:
        cursor.execute('SELECT * FROM scores')
        rows = cursor.fetchall()
        if rows:
            return False
        else:
            return True


def ProcessLogMessages(data: bytes):
    """Apply the appropriate regular expression to log messages and handle them."""
    dataStr = str(data)
    logFileName = "/home/geoffrosenberg/Documents/connections.txt"

    connectedExpr = re.compile('\\bconnected')
    if connectedExpr.search(dataStr) is not None:
        AddPlayer(dataStr)
        UpdateLogFile(logFileName, dataStr)

    disconnectedExpr = re.compile('\\bdisconnected')
    if disconnectedExpr.search(dataStr) is not None:
        RemovePlayer(dataStr)
        if IsPlayersTableEmpty() and os.path.exists(logFileName):
            os.remove(logFileName)

    killedExpr = re.compile('\\bkilled')
    if killedExpr.search(dataStr) is not None:
        UpdateScore(dataStr)

    suicideExpr = re.compile('\\bsuicide')
    if suicideExpr.search(dataStr) is not None:
        HandleSuicide(dataStr)

    nameChangeExpr = re.compile('\" changed name to \"')
    if nameChangeExpr.search(dataStr) is not None:
        HandleNameChange(dataStr)

    mapChangeExpr = re.compile('Started map')
    if mapChangeExpr.search(dataStr) is not None:
        HandleMapChange(dataStr)


if __name__ == "__main__":
    UDP_IP = "127.0.0.1"
    UDP_PORT = 11001

    sock = socket.socket(socket.AF_INET,
                         socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))
    password = getpass.getpass('Password for user halflife: ')
    conn = psycopg2.connect(database='halflife', user='halflife',
                            password=password, host='thebox', port=5432)

    # initialize scoreboard as empty
    with conn.cursor() as cursor:
        cursor.execute('DELETE FROM scores')
        conn.commit()

    while True:
        data, addr = sock.recvfrom(1024)
        ProcessLogMessages(data)
