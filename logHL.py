#!/usr/bin/env python3
"""Log UDP messages frm halflife server."""
import socket
import re
import os


def GetPlayerName(dataStr: str) -> str:
    """Get player name from log string."""
    expr = re.compile('\"((\\w+\\s*)+)<[0-9]*>')
    matches = expr.search(dataStr)
    playerName = ''
    if matches is not None:
        playerName = matches.group(1)
    return playerName


def UpdateLogFile(fileName: str):
    """Update the log file."""
    if players == set():
        os.remove(fileName)

    with open(fileName, "w") as logfile:
        logfile.write("Current players:\n")
        for player in players:
            logfile.write("{0}\n".format(player))
        logfile.write("\n")


def ProcessLogMessages(data: bytes):
    """Apply the regular expression."""
    dataStr = str(data)
    print(dataStr)
    playerName = GetPlayerName(dataStr)
    logFileName = "/home/geoffrosenberg/Documents/connections.txt"

    connectedExpr = re.compile('\\bconnected')
    if connectedExpr.search(dataStr) is not None:
        players.add(playerName)
        UpdateLogFile(logFileName)

    disconnectedExpr = re.compile('\\bdisconnected')
    if disconnectedExpr.search(dataStr) is not None:
        players.remove(playerName)
        if players == set():
            os.remove(logFileName)


if __name__ == "__main__":
    hostname = socket.gethostname()
    UDP_IP = socket.gethostbyname(hostname)
    UDP_PORT = 11001

    sock = socket.socket(socket.AF_INET,
                         socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))

    players = set()

    while True:
        data, addr = sock.recvfrom(1024)
        ProcessLogMessages(data)
