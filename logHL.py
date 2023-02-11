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

pendingPlayers = {}
currentMap = 'crossfireXL'
conn = ''


class PlayerConnectionInfo:
    """Player name, IP."""
    def __init__(self, name: str, ip: str):
        self.name = name
        self.address = ip


def PrintScoresToConsole(dataStr: str):
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
                                            "WON ID", "IP Address"]))
    sys.stdout.flush()


def PrintDataStrToConsole(dataStr: str):
    print("Log Message: {0}".format(dataStr))
    sys.stdout.flush()


def PrintScoresToLogFile(fileName: str, dataStr: str):
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
                                                    "Deaths", "WON ID",
                                                    "IP Address"]))
            logfile.write("\n")


def InsertPlayerIntoPendingPlayers(dataStr: str):
    """Get player info from the connection message."""
    expr = re.compile('\"((?:\\w+\\s*)+)<[0-9]+><STEAM_[0-9]:[0-9]:([0-9]+)><.*>\".*\"((?:[0-9]+\.)+[0-9]+)')
    matches = expr.search(dataStr)
    global pendingPlayers
    if matches is not None:
        connectionInfo = PlayerConnectionInfo(matches.groups()[0], matches.groups()[2])
        pendingPlayers[matches.groups()[1]] = connectionInfo


def GetPlayerNameAndId(dataStr: str):
    """Get player name and ID."""
    expr = re.compile('\"((?:\\w+\\s*)+)<[0-9]+><STEAM_[0-9]:[0-9]:([0-9]+)')
    matches = expr.search(dataStr)
    playerNameAndId = []
    if matches is not None:
        playerNameAndId.append(matches.groups()[0])  # name
        playerNameAndId.append(matches.groups()[1])  # WON ID
    return playerNameAndId


def ResetScore():
    """Reset the score for all players and update high score if applicable."""
    with conn.cursor() as cursor:
        cursor.execute('SELECT won_id, kills FROM scores')
        rows = cursor.fetchall()
        for row in rows:
            wonId = row[0]
            sessionKills = row[1]
            cursor.execute("SELECT max_kills FROM playerhistory WHERE won_id = {0}".format(wonId))
            row = cursor.fetchone()
            if row:
                maxKills = row[0]
                if sessionKills > maxKills:
                    cursor.execute("UPDATE playerhistory SET max_kills = {0} WHERE won_id = {1}".format(sessionKills, wonId))

        cursor.execute('UPDATE scores SET kills = 0')
        cursor.execute('UPDATE scores SET deaths = 0')


def AddPlayer(dataStr: str):
    """Add a new player."""
    playerNameAndId = GetPlayerNameAndId(dataStr)
    global pendingPlayers
    if playerNameAndId[1] not in pendingPlayers:
        print("""Warning: cannot add player {0} (ID {1}) to the scores table because we never received a
        connection message""".format(playerNameAndId[0], playerNameAndId[1]))
        return

    playerId = playerNameAndId[1]
    playerConnectionInfo = pendingPlayers.pop(playerId)
    playerName = playerConnectionInfo.name
    playerIp = playerConnectionInfo.address

    with conn.cursor() as cursor:
        if not IsWonIdInScoresTable(playerId):
            cursor.execute('INSERT INTO scores (won_id, name, kills, deaths, '
                           + 'ip_address) VALUES(%s, %s, %s, %s, %s)',
                           (playerId, playerName, '0', '0', playerIp))

        cursor.execute('SELECT * from playerhistory WHERE won_id = '
                       + playerId)
        rows = cursor.fetchall()
        if rows:
            updateCommand = "UPDATE playerhistory SET last_login = '{0}', login_count = login_count + 1, most_recent_alias = '{1}' WHERE won_id = {2}".format(datetime.now(timezone.utc), playerName, playerId)
            cursor.execute(updateCommand)
        else:
            cursor.execute('INSERT INTO playerhistory (won_id, first_login, last_login, kills, deaths, login_count, total_hours, max_kills, most_recent_alias) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s)', (playerId, datetime.now(timezone.utc), datetime.now(timezone.utc), 0, 0, 1, 0, 0, playerName))

        try:
            cursor.execute('INSERT INTO playeraliases (won_id, alias) VALUES(%s, %s)', (playerId, playerName))
        except psycopg2.errors.UniqueViolation as e:
            print("AddPlayer: error while inserting into playeraliaes table", file=sys.stderr)
            print(e, file=sys.stderr)


def RemovePlayer(dataStr: str):
    """Remove a player from the scores table."""
    nameAndId = GetPlayerNameAndId(dataStr)
    if not IsWonIdInScoresTable(nameAndId[1]):
        return

    with conn.cursor() as cursor:
        cursor.execute('SELECT last_login, max_kills FROM playerhistory WHERE won_id = '
                       + nameAndId[1])
        row = cursor.fetchone()
        sessionStartTime = row[0]
        maxKills = row[1]
        cursor.execute('SELECT kills FROM scores WHERE won_id = ' + nameAndId[1])
        row = cursor.fetchone()
        if row:
            sessionKills = row[0]
            sessionHours = (datetime.now(timezone.utc) - sessionStartTime).seconds / 3600
            if sessionKills > maxKills:
                cursor.execute("UPDATE playerhistory SET total_hours = total_hours + {0}, max_kills = {1} WHERE won_id = {2}".format(sessionHours, sessionKills, nameAndId[1]))
            else:
                cursor.execute("UPDATE playerhistory SET total_hours = total_hours + {0} WHERE won_id = {1}".format(sessionHours, nameAndId[1]))

            cursor.execute('DELETE FROM scores WHERE won_id = %s', (nameAndId[1],))


def UpdateScore(dataStr: str):
    """Update player scores when one player kills another."""
    expr = re.compile('\"(\\w+\\s*)+<[0-9]+><STEAM_[0-9]:[0-9]:([0-9]+)>.*\"(\\w+\\s*)+<[0-9]+><STEAM_[0-9]:[0-9]:([0-9]+)>.*with\\s\"(.*)\"')
    matches = expr.search(dataStr)
    if matches is not None:
        nameKiller = matches.groups()[0]
        idKiller = matches.groups()[1]
        nameKillee = matches.groups()[2]
        idKillee = matches.groups()[3]
        weapon = matches.groups()[4]
        with conn.cursor() as cursor:
            if IsWonIdInScoresTable(idKiller):
                cursor.execute('UPDATE scores SET kills = kills+1 WHERE won_id ='
                               + ' %s', (idKiller,))
            else:
                cursor.execute('INSERT INTO scores (won_id, name, kills, deaths, ip_address) VALUES(%s, %s, %s, %s, %s)',
                       (idKiller, nameKiller, 1, 0, "0.0.0.0"))
                cursor.execute("UPDATE playerhistory SET last_login = '{0}', login_count = login_count + 1, most_recent_alias = '{1}' WHERE won_id = {2}".format(datetime.now(timezone.utc), nameKiller, idKiller))

                try:
                    cursor.execute('INSERT INTO playeraliases (won_id, alias) VALUES(%s, %s)', (idKiller, nameKiller))
                except psycopg2.errors.UniqueViolation as e:
                    print(e, file=sys.stderr)

            if IsWonIdInScoresTable(idKillee):
                cursor.execute('UPDATE scores SET deaths = deaths+1 WHERE won_id'
                               + ' = %s', (idKillee,))
            else:
                cursor.execute('INSERT INTO scores (won_id, name, kills, deaths, ip_address) VALUES(%s, %s, %s, %s, %s)',
                       (idKillee, nameKillee, 0, 1, "0.0.0.0"))
                cursor.execute("UPDATE playerhistory SET last_login = '{0}', login_count = login_count + 1, most_recent_alias = '{1}' WHERE won_id = {2}".format(datetime.now(timezone.utc), nameKillee, idKillee))

                try:
                    cursor.execute('INSERT INTO playeraliases (won_id, alias) VALUES(%s, %s)', (idKillee, nameKillee))
                except psycopg2.errors.UniqueViolation as e:
                    print("Error while inserting into playeraliases:", file=sys.stderr)
                    print(e, file=sys.stderr)

            cursor.execute('UPDATE playerhistory SET kills = kills+1 WHERE'
                           + ' won_id = %s', (idKiller,))
            cursor.execute('UPDATE playerhistory SET deaths = deaths+1 WHERE'
                           + ' won_id = %s', (idKillee,))
            cursor.execute("SELECT * FROM playerweapons WHERE won_id = {0}".format(idKiller))
            rows = cursor.fetchone()
            if not rows:
                cursor.execute('INSERT INTO playerweapons (won_id) VALUES(%s)', idKiller)

            if weapon == "357":
                cursor.execute("UPDATE playerweapons SET magnum = magnum + 1 WHERE won_id = {0}".format(idKiller))
            elif weapon == "9mmAR":
                cursor.execute("UPDATE playerweapons SET mp5 = mp5 + 1 WHERE won_id = {0}".format(idKiller))
            else:
                cursor.execute("UPDATE playerweapons SET {0} = {0} + 1 WHERE won_id = {1}".format(weapon, idKiller))


def IsWonIdInScoresTable(Id: str) -> bool:
    with conn.cursor() as cursor:
        cursor.execute('SELECT * FROM scores WHERE won_id = {0}'.format(Id))
        row = cursor.fetchone()
        if row:
            return True
        else:
            return False


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
    nameAndId = GetPlayerNameAndId(dataStr)
    killPenalty = -1
    worldExpr = re.compile('world')
    matches = worldExpr.search(dataStr)
    if matches is not None:
        killPenalty = 0

    with conn.cursor() as cursor:
        if IsWonIdInScoresTable(nameAndId[1]):
            cursor.execute('UPDATE scores SET deaths = deaths + 1 WHERE won_id ='
                           + ' %s', (nameAndId[1],))
            cursor.execute('UPDATE scores SET kills = kills + %s WHERE won_id ='
                           + ' %s', (killPenalty, nameAndId[1],))
        else:
            cursor.execute('INSERT INTO scores (won_id, name, kills, deaths, ip_address) VALUES(%s, %s, %s, %s, %s)',
                       (nameAndId[1], nameAndId[0], killPenalty, 1, "0.0.0.0"))
            cursor.execute("UPDATE playerhistory SET last_login = '{0}', login_count = login_count + 1, most_recent_alias = '{1}' WHERE won_id = {2}".format(datetime.now(timezone.utc), nameAndId[0], nameAndId[1]))

        cursor.execute('UPDATE playerhistory SET deaths = deaths + 1 WHERE '
                       + 'won_id = %s', (nameAndId[1],))
        cursor.execute('UPDATE playerhistory SET kills = kills + %s WHERE '
                       + 'won_id = %s', (killPenalty, nameAndId[1],))


def HandleNameChange(dataStr: str):
    """Update a player's name."""
    id = GetPlayerNameAndId(dataStr)[1]
    nameExpr = re.compile('.*changed name to \"((?:\\w+\\s*)+)\"')
    matches = nameExpr.search(dataStr)
    if matches:
        newName = matches.groups()[0]
        with conn.cursor() as cursor:
            updateCommand = "UPDATE scores SET name = '{0}' WHERE won_id = {1}".format(newName, id)
            cursor.execute(updateCommand)
            cursor.execute("UPDATE playerhistory SET most_recent_alias = '{0}' WHERE won_id = {1}".format(newName, id))
            try:
                cursor.execute('INSERT INTO playeraliases (won_id, alias) VALUES(%s, %s)', (id, newName))
            except psycopg2.errors.UniqueViolation as e:
                print(e, file=sys.stderr)


def IsScoresTableEmpty() -> bool:
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
    PrintDataStrToConsole(dataStr)
    logFileName = "/home/geoffrosenberg/Documents/connections.txt"

    connectedExpr = re.compile('\\bconnected')
    if connectedExpr.search(dataStr) is not None:
        InsertPlayerIntoPendingPlayers(dataStr)

    enteredExpr = re.compile('\\bentered the game')
    if enteredExpr.search(dataStr) is not None:
        AddPlayer(dataStr)
        PrintScoresToLogFile(logFileName, dataStr)

    disconnectedExpr = re.compile('\\bdisconnected')
    if disconnectedExpr.search(dataStr) is not None:
        RemovePlayer(dataStr)
        if IsScoresTableEmpty() and os.path.exists(logFileName):
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
    conn.autocommit = True

    # initialize scoreboard as empty
    with conn.cursor() as cursor:
        cursor.execute('DELETE FROM scores')

    while True:
        data, addr = sock.recvfrom(1024)
        ProcessLogMessages(data)
